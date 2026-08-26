"""Retry waste is attributable — including from the gathered tasks where it happens.

r26 measured `anchor` at a 282.8s median and 812.5s max and wrote that up, twice,
as the cost of the tool. Four of its ten `anchor` rounds landed at 807.9 / 808.2 /
812.3 / 812.5s — a four-way tie inside 5 seconds is a ceiling, not a workload, and
the ceiling is `use_brain`'s ParseError ladder: 10s doubling to a 120s cap over 10
attempts is exactly 750s of `asyncio.sleep`, on top of the ~40s the same round's
fast calls took. Every one of them reported `ok`, and the whole 2.5-hour run
logged zero warnings, because ParseError was the one retry branch that logged
nothing.

So these tests guard two things:

1. That a retry lands on the account at all — including when it happens inside an
   `asyncio.gather`'d child, which is where MOST framework retries happen
   (`execute_tools` gathers a round; `ExploreTransformations` and
   `AnalysisPipeline` fan out further inside one tool). A task inherits a COPY of
   the context, so this is precisely the case a plain counter would lose.
2. That `ToolRound.retry_seconds` is populated from the round it belongs to, so
   the archive can subtract sleep from wall clock instead of quoting the blend.

No LLM and no graph here: the accountant is a contextvar and some arithmetic, and
the facilitator seam is exercised with a fake response so the ladder does not have
to actually sleep 750 seconds to be tested.
"""

from __future__ import annotations

import asyncio

import pytest
from mirascope.llm.content import ToolCall

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.turn_timing import ToolRound, TurnTiming
from dialectical_framework.utils.retry_accounting import (
    RetryAccount, current_retry_account, record_retry, retry_account)


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class TestAccountBasics:
    def test_unobserved_retry_is_a_no_op(self):
        """Most `use_brain` callers are pipelines nobody is timing.

        Costing nothing when no account is installed is what lets `record_retry`
        sit on the hot path without a caller having to opt out.
        """
        record_retry("parse", sleep_s=10.0, attempt_s=1.0)  # must not raise

        assert current_retry_account() is None

    def test_sleep_and_failed_attempt_are_kept_apart(self):
        """They have different fixes, so summing them at the source loses that.

        `sleep_s` is a policy number (our backoff curve). `failed_attempt_s` is
        provider work we paid for and discarded.
        """
        with retry_account() as account:
            record_retry("parse", sleep_s=10.0, attempt_s=4.0)
            record_retry("parse", sleep_s=20.0, attempt_s=6.0)

        assert account.sleep_s == 30.0
        assert account.failed_attempt_s == 10.0
        assert account.wasted_s == 40.0
        assert account.count == 2
        assert account.kinds == {"parse": 2}

    def test_kinds_separate_a_ladder_from_an_outage(self):
        """"Slept 60s" means different things per branch: a ParseError ladder is
        a schema problem, throttling is a concurrency problem, a 5xx is theirs."""
        with retry_account() as account:
            record_retry("parse", sleep_s=10.0, attempt_s=0.0)
            record_retry("rate_limit", sleep_s=10.0, attempt_s=0.0)
            record_retry("rate_limit", sleep_s=20.0, attempt_s=0.0)

        assert account.kinds["parse"] == 1
        assert account.kinds["rate_limit"] == 2

    def test_a_clean_call_records_nothing(self):
        """Zero must mean zero: `retry_count == 0` is the archive's only signal
        that a slow tool was slow because it worked, not because it failed."""
        with retry_account() as account:
            pass

        assert account.wasted_s == 0.0
        assert account.count == 0

    def test_the_stack_unwinds(self):
        """A leaked account would attribute the NEXT turn's retries to this one."""
        with retry_account():
            assert current_retry_account() is not None

        assert current_retry_account() is None

    def test_a_raising_block_still_unwinds(self):
        """The expensive turns are the ones that fail — if those leak the account,
        the accounting breaks exactly when it matters."""
        with pytest.raises(RuntimeError):
            with retry_account():
                raise RuntimeError("boom")

        assert current_retry_account() is None


class TestNesting:
    """Nested accounts BOTH see a retry — the property the design turns on.

    `ConversationFacilitator` installs one account per turn and one per tool
    round inside it. Under replacement semantics the turn account would go blind
    for the duration of every tool round, so a turn would report LESS waste the
    more of its work was instrumented.
    """

    def test_inner_retry_reaches_the_outer_account(self):
        with retry_account() as turn:
            with retry_account() as round_one:
                record_retry("parse", sleep_s=10.0, attempt_s=2.0)

        assert round_one.wasted_s == 12.0
        assert turn.wasted_s == 12.0
        assert turn.count == 1

    def test_the_outer_total_is_the_sum_of_its_rounds_plus_its_own(self):
        """This subtraction is how generation retries become visible at all."""
        with retry_account() as turn:
            with retry_account() as round_one:
                record_retry("parse", sleep_s=10.0, attempt_s=0.0)
            # Between rounds — i.e. during the model's own generation.
            record_retry("rate_limit", sleep_s=30.0, attempt_s=0.0)
            with retry_account() as round_two:
                record_retry("server", sleep_s=5.0, attempt_s=0.0)

        in_rounds = round_one.wasted_s + round_two.wasted_s
        assert in_rounds == 15.0
        assert turn.wasted_s == 45.0
        assert turn.wasted_s - in_rounds == 30.0

    def test_sibling_rounds_do_not_see_each_other(self):
        """Otherwise the per-tool table credits every tool with every sleep."""
        with retry_account():
            with retry_account() as first:
                record_retry("parse", sleep_s=10.0, attempt_s=0.0)
            with retry_account() as second:
                pass

        assert first.wasted_s == 10.0
        assert second.wasted_s == 0.0

    def test_reusing_one_account_across_separate_blocks_accumulates(self):
        """How the streaming path totals a turn: it cannot hold the account open
        across a `yield` (the set would install itself in the consumer's context
        and never reset), so it re-enters with the same object per await."""
        turn = RetryAccount()
        with retry_account(turn):
            record_retry("parse", sleep_s=10.0, attempt_s=0.0)
        with retry_account(turn):
            record_retry("parse", sleep_s=20.0, attempt_s=0.0)

        assert turn.sleep_s == 30.0
        assert turn.count == 2


class TestConcurrency:
    """The case a float counter loses: retries inside gathered children.

    An `asyncio` task inherits a COPY of the creating context, so a child's
    `ContextVar.set()` is invisible to its parent. Almost every retry in this
    framework happens in a gathered child — `execute_tools()` gathers a round,
    and `ExploreTransformations` / `AnalysisPipeline` fan out again inside a
    single tool — so "lost in children" would mean "lost".
    """

    @pytest.mark.asyncio
    async def test_a_gathered_child_reaches_the_parents_account(self):
        async def child(sleep_s: float) -> None:
            await asyncio.sleep(0)  # a real suspension, so this is a real task
            record_retry("parse", sleep_s=sleep_s, attempt_s=1.0)

        with retry_account() as account:
            await asyncio.gather(child(10.0), child(20.0), child(40.0))

        assert account.sleep_s == 70.0
        assert account.failed_attempt_s == 3.0
        assert account.count == 3

    @pytest.mark.asyncio
    async def test_a_grandchild_reaches_it_too(self):
        """`AnalysisPipeline` gathers inside a tool that was itself gathered."""

        async def grandchild() -> None:
            record_retry("parse", sleep_s=10.0, attempt_s=0.0)

        async def child() -> None:
            await asyncio.gather(grandchild(), grandchild())

        with retry_account() as account:
            await asyncio.gather(child(), child())

        assert account.count == 4
        assert account.sleep_s == 40.0

    @pytest.mark.asyncio
    async def test_concurrent_turns_do_not_pollute_each_other(self):
        """`isolate()` exists so pipelines can run facilitators in parallel; two
        of them must not share a bill."""

        async def turn(kind: str, sleep_s: float) -> RetryAccount:
            with retry_account() as account:
                await asyncio.sleep(0)
                record_retry(kind, sleep_s=sleep_s, attempt_s=0.0)
                await asyncio.sleep(0)
            return account

        first, second = await asyncio.gather(
            turn("parse", 10.0), turn("rate_limit", 30.0)
        )

        assert (first.sleep_s, first.kinds["parse"]) == (10.0, 1)
        assert (second.sleep_s, second.kinds["rate_limit"]) == (30.0, 1)
        assert first.count == second.count == 1


class TestTurnTimingArithmetic:
    """Retry seconds are a component of a component, never a new addend.

    `TurnRecord.duration_s == reply_path_s + off_path_s` held to 0% unexplained
    overhead across all 16 turns of `timing-check-building`. A new reply-path
    field that reads as a third addend silently turns that check into a report of
    harness overhead.
    """

    def test_working_seconds_strips_the_sleep(self):
        round_ = ToolRound(names=("anchor",), seconds=812.5, retry_seconds=750.0)

        assert round_.working_seconds == pytest.approx(62.5)
        assert round_.seconds == 812.5  # the person still waited all of it

    def test_working_seconds_never_goes_negative(self):
        """Two clocks, one around the round and one summed from inside nested
        calls: a negative duration in a record looks like data."""
        round_ = ToolRound(names=("anchor",), seconds=10.0, retry_seconds=12.0)

        assert round_.working_seconds == 0.0

    def test_the_split_between_tool_and_generation_retries(self):
        timing = TurnTiming(
            reply_path_s=900.0,
            off_path_s=1.0,
            tool_rounds=(
                ToolRound(names=("anchor",), seconds=810.0, retry_seconds=750.0),
            ),
            retry_seconds=780.0,
            retry_count=11,
        )

        assert timing.tool_retry_seconds == 750.0
        assert timing.generation_retry_seconds == 30.0
        # Still inside the reply path, not beside it.
        assert timing.total_s == 901.0

    def test_a_toolless_turn_attributes_all_its_waste_to_generation(self):
        """r26's shape: 644.1s of residual with zero tool calls, which nothing at
        the time could tell apart from a slow reply."""
        timing = TurnTiming(
            reply_path_s=644.1, off_path_s=0.4, retry_seconds=600.0, retry_count=6
        )

        assert timing.tool_retry_seconds == 0.0
        assert timing.generation_retry_seconds == 600.0

    def test_retry_rounds_are_parallel_to_tool_rounds(self):
        """Index i of one is the waste inside index i of the other — readers
        parse both by splitting on the last colon, so the formats must match."""
        timing = TurnTiming(
            reply_path_s=1.0,
            off_path_s=0.0,
            tool_rounds=(
                ToolRound(names=("anchor",), seconds=810.0, retry_seconds=750.0),
                ToolRound(names=("sync", "explore"), seconds=42.0),
            ),
        )

        assert timing.format_rounds() == ["anchor:810.0s", "sync+explore:42.0s"]
        assert timing.format_retry_rounds() == ["anchor:750.0s", "sync+explore:0.0s"]


# --- the seam: a retry inside a tool lands on that tool's round -------------


class _FakeToolOutput:
    """What `execute_tools()` hands back — only `value`/`error` are read."""

    def __init__(self, value: str = "{}") -> None:
        self.value = value
        self.error = None


class _FakeRound:
    """One turn of the agentic loop, standing in for Mirascope's AsyncResponse.

    `retries` is what the tool "spends" while executing: the account is installed
    by `submit` around `execute_tools()`, so calling `record_retry` from inside is
    exactly what a nested `use_brain` ParseError does.
    """

    def __init__(self, tool_calls: list[ToolCall], retries: list[float]) -> None:
        self.tool_calls = tool_calls
        self.messages: list = []
        self._retries = retries

    async def execute_tools(self) -> list[_FakeToolOutput]:
        for sleep_s in self._retries:
            record_retry("parse", sleep_s=sleep_s, attempt_s=0.0)
        return [_FakeToolOutput() for _ in self.tool_calls]

    async def resume(self, tool_outputs) -> _FakeRound:
        return _FakeRound([], [])


class _Reply:
    message: str = "done"


class TestFacilitatorRecordsRetriesPerRound:
    @pytest.mark.asyncio
    async def test_a_tools_retry_lands_on_its_own_round(self, monkeypatch):
        """The number r26 needed and did not have: of `anchor`'s 810 seconds,
        how many were sleep."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        first = _FakeRound([ToolCall(id="t1", name="anchor", args="{}")], [10.0, 20.0])

        async def _tools_call():
            return first

        async def _structured(model):
            return _Reply()

        monkeypatch.setattr(facilitator, "_call_with_tools", _tools_call)
        monkeypatch.setattr(facilitator, "_call_with_response_model", _structured)

        await facilitator.submit(_Reply, "hello")

        assert len(facilitator.last_tool_rounds) == 1
        recorded = facilitator.last_tool_rounds[0]
        assert recorded.names == ("anchor",)
        assert recorded.retry_seconds == 30.0
        assert recorded.retry_count == 2
        assert facilitator.last_submit_retries.wasted_s == 30.0
        assert facilitator.last_submit_retries.count == 2

    @pytest.mark.asyncio
    async def test_a_clean_round_records_zero(self, monkeypatch):
        facilitator = ConversationFacilitator(tools=[lambda: None])
        first = _FakeRound([ToolCall(id="t1", name="sync", args="{}")], [])

        async def _tools_call():
            return first

        async def _structured(model):
            return _Reply()

        monkeypatch.setattr(facilitator, "_call_with_tools", _tools_call)
        monkeypatch.setattr(facilitator, "_call_with_response_model", _structured)

        await facilitator.submit(_Reply, "hello")

        assert facilitator.last_tool_rounds[0].retry_count == 0
        assert facilitator.last_submit_retries.wasted_s == 0.0

    @pytest.mark.asyncio
    async def test_a_retry_outside_any_tool_round_is_the_turns_but_no_rounds(
        self, monkeypatch
    ):
        """A generation-time retry: on the turn's bill, on no tool's bill.

        This is the case that would otherwise read as the model thinking slowly.
        """
        facilitator = ConversationFacilitator(tools=[lambda: None])
        first = _FakeRound([ToolCall(id="t1", name="anchor", args="{}")], [])

        async def _tools_call():
            return first

        async def _structured(model):
            record_retry("parse", sleep_s=40.0, attempt_s=5.0)
            return _Reply()

        monkeypatch.setattr(facilitator, "_call_with_tools", _tools_call)
        monkeypatch.setattr(facilitator, "_call_with_response_model", _structured)

        await facilitator.submit(_Reply, "hello")

        assert facilitator.last_tool_rounds[0].retry_seconds == 0.0
        assert facilitator.last_submit_retries.wasted_s == 45.0

    @pytest.mark.asyncio
    async def test_the_account_is_reset_between_turns(self, monkeypatch):
        """Otherwise turn two inherits turn one's 12 minutes."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        async def _structured(model):
            return _Reply()

        monkeypatch.setattr(facilitator, "_call_with_response_model", _structured)

        async def _expensive():
            return _FakeRound([ToolCall(id="t1", name="anchor", args="{}")], [750.0])

        monkeypatch.setattr(facilitator, "_call_with_tools", _expensive)
        await facilitator.submit(_Reply, "first")
        assert facilitator.last_submit_retries.wasted_s == 750.0

        async def _clean():
            return _FakeRound([ToolCall(id="t2", name="sync", args="{}")], [])

        monkeypatch.setattr(facilitator, "_call_with_tools", _clean)
        await facilitator.submit(_Reply, "second")

        assert facilitator.last_submit_retries.wasted_s == 0.0
        assert facilitator.last_tool_rounds[0].retry_count == 0
