"""A turn records where its seconds went, split at the person's reply.

Born from a measurement that could not be made. `tests/e2e/probe_reply_path_latency.py`
had to ESTIMATE the reply-path share by regressing 187 archived runs' cell-level
`duration_s` onto their tool-call histograms, because nothing recorded a per-turn
duration: `RunRecord.duration_s` covers a whole multi-session cell. The estimate
(81% strong / 88% weak of wall clock spent between the person's message and their
reply existing) was good enough to act on and impossible to check.

What these tests pin is the part a regression cannot recover on its own:

1. **The reply-path / off-path boundary is real.** `Advisor` has always claimed it
   in a comment — "so the person's reply is never delayed by the repair" — and a
   claim in a comment is what this archive keeps learning not to trust.
2. **Concurrent rounds stay unattributable.** `execute_tools()` gathers a round
   and runs it concurrently, so a 3-call round took as long as its SLOWEST call.
   Recording those seconds under one tool's name would invent a number, and the
   `+`-joined name is what makes that impossible to do by accident.
3. **A turn that RAISED still reports its seconds.** The expensive failures are
   the ones worth seeing, and a duration recorded only on the happy path hides
   exactly them.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import ResponseComplete
from dialectical_framework.agents.turn_timing import ToolRound, TurnTiming
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.retry_accounting import RetryAccount


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _Reply(BaseModel):
    message: str = "ok"


class TestTurnTimingArithmetic:
    """Pure logic — no provider, no graph."""

    def test_generation_is_reply_path_minus_tool_rounds(self):
        timing = TurnTiming(
            reply_path_s=250.0,
            off_path_s=8.0,
            tool_rounds=(
                ToolRound(names=("anchor",), seconds=210.0),
                ToolRound(names=("explore",), seconds=30.0),
            ),
        )
        assert timing.tool_seconds == pytest.approx(240.0)
        assert timing.generation_s == pytest.approx(10.0)
        assert timing.total_s == pytest.approx(258.0)

    def test_generation_never_goes_negative(self):
        """Two clocks around nested awaits can in principle disagree.

        A negative duration in a saved record is worse than a zero, because it
        looks like data rather than like a clock artefact.
        """
        timing = TurnTiming(
            reply_path_s=5.0,
            off_path_s=0.0,
            tool_rounds=(ToolRound(names=("anchor",), seconds=9.0),),
        )
        assert timing.generation_s == 0.0

    def test_concurrent_round_is_not_attributable_to_one_tool(self):
        """The `+` is the whole safeguard — see this module's docstring."""
        solo = ToolRound(names=("anchor",), seconds=210.0)
        together = ToolRound(names=("anchor", "record_decision"), seconds=33.0)

        assert solo.is_attributable
        assert not together.is_attributable

        timing = TurnTiming(
            reply_path_s=300.0, off_path_s=0.0, tool_rounds=(solo, together)
        )
        assert timing.format_rounds() == [
            "anchor:210.0s",
            "anchor+record_decision:33.0s",
        ]

    def test_a_turn_with_no_tools_is_all_generation(self):
        timing = TurnTiming(reply_path_s=16.0, off_path_s=0.0)
        assert timing.tool_seconds == 0.0
        assert timing.generation_s == pytest.approx(16.0)
        assert timing.format_rounds() == []


@pytest.mark.llm
class TestFacilitatorRecordsItsOwnSeconds:
    """The facilitator owns the tool loop, so it owns the tool-round clock."""

    async def test_submit_records_wall_clock_without_tools(self):
        facilitator = ConversationFacilitator()
        facilitator.set_system_prompt("You are terse.")

        await facilitator.submit(_Reply, "hello")

        assert facilitator.last_submit_seconds > 0.0
        # No tools wired: nothing to time inside the loop, and no loop to run.
        assert facilitator.last_tool_rounds == []

    async def test_a_raising_submit_still_reports_its_seconds(self):
        """`finally`, not a happy-path assignment.

        A turn that spent four minutes in tools and then died cost the person
        those four minutes. Recording zero for it would make the most expensive
        turns in a run the invisible ones — the same shape of blind spot as a
        tool that RAISED being filed as a read-only call (`TurnRecord.tool_outcomes`).
        """
        facilitator = ConversationFacilitator()
        facilitator.set_system_prompt("You are terse.")

        async def _boom(*_args, **_kwargs):
            await asyncio.sleep(0.01)
            raise RuntimeError("provider down")

        facilitator._call_with_response_model = _boom  # type: ignore[assignment]

        with pytest.raises(RuntimeError, match="provider down"):
            await facilitator.submit(_Reply, "hello")

        assert facilitator.last_submit_seconds > 0.0

    async def test_tool_round_names_and_seconds_are_recorded_per_round(self):
        """The loop's own clock, exercised through the loop.

        Stubbed at `_call_with_tools`/`resume` rather than at the provider so the
        real `submit` body runs — the round timer sits between two awaits in that
        body, and a test that replaced the body could not see it at all.
        """
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.set_system_prompt("You are terse.")

        class _Call:
            def __init__(self, name: str) -> None:
                self.name = name
                self.args = "{}"

        class _Resp:
            def __init__(self, calls: list[str]) -> None:
                self.tool_calls = [_Call(n) for n in calls]
                self.messages: list = []

            async def execute_tools(self):
                await asyncio.sleep(0.02)
                return []

            async def resume(self, _outputs):
                return _Resp([])

        async def _first(*_args, **_kwargs):
            return _Resp(["anchor", "explore"])

        facilitator._call_with_tools = _first  # type: ignore[assignment]

        async def _final(*_args, **_kwargs):
            return _Reply()

        facilitator._call_with_response_model = _final  # type: ignore[assignment]

        await facilitator.submit(_Reply, "hello")

        assert len(facilitator.last_tool_rounds) == 1
        round_ = facilitator.last_tool_rounds[0]
        # Both names on ONE round: they were gathered and run concurrently, so
        # the seconds belong to neither alone.
        assert round_.names == ("anchor", "explore")
        assert not round_.is_attributable
        assert round_.seconds >= 0.02

    async def test_timing_resets_between_turns(self):
        """Same reset discipline as `last_tool_results`.

        Without it a turn inherits the previous turn's seconds, which is how a
        cheap turn ends up wearing an expensive one's cost — and the archive
        already paid for that class of bug once, when unreset tool results
        attributed a crash to a healthy turn.
        """
        facilitator = ConversationFacilitator()
        facilitator.set_system_prompt("You are terse.")

        await facilitator.submit(_Reply, "first")
        facilitator.last_tool_rounds.append(
            ToolRound(names=("anchor",), seconds=999.0)
        )

        await facilitator.submit(_Reply, "second")

        assert facilitator.last_tool_rounds == []
        assert facilitator.last_submit_seconds < 999.0


#: How long the fake repair sleeps. Long enough to clear timer noise, short
#: enough that the suite does not notice.
_REPAIR_SLEEP = 0.05

#: What the fake facilitator reports for the reply path. Deliberately LARGER than
#: `_REPAIR_SLEEP` and deliberately a copied constant rather than a measured
#: interval: `reply_path_s` is read off the facilitator, so it can be asserted
#: exactly, and the repair's own seconds must not be able to leak into it.
_REPLY_PATH_S = 7.5


class _StubAdvisor:
    """`Advisor.chat` in isolation, at the boundary this module is about.

    Same idiom as `_StubAdvisor` in `test_decision_confirmation_repair.py`, and
    for the same reason: `Advisor.__init__` validates a nexus and renders a system
    prompt, both of which want a DB and a live DI container. `chat` itself only
    needs a conversation, the two seams around it, and a scope — and `scope` /
    `agent_scope` are pure contextvars, so the real method body runs here with no
    graph at all.

    Binding the REAL `chat` matters. The reply-path / off-path split is decided by
    where two `time.monotonic()` calls sit relative to the repair await, so a test
    that reimplemented the method would be checking its own copy of the thing
    under test.
    """

    AGENT_NAME = Advisor.AGENT_NAME

    def __init__(self, tool_rounds: tuple[ToolRound, ...] = ()) -> None:
        self.last_turn_timing = None
        self.repaired = False

        class _Conv:
            last_submit_seconds = _REPLY_PATH_S
            last_tool_rounds = list(tool_rounds)
            # A clean turn, so the retry accounting stays out of the way of the
            # boundary this module is about. Its own arithmetic — and that a
            # retry inside a tool round is attributed to that round rather than
            # to generation — is pinned in `test_retry_accounting.py`.
            last_submit_retries = RetryAccount()

            async def submit(self, _model, _message):
                return _Reply(message="counsel")

        self._conversation = _Conv()

    async def _refresh_context(self) -> float:
        # Zero, so this module's assertions stay exactly about the repair
        # boundary. The refresh's own contribution to `reply_path_s` is pinned
        # in `test_advisor_context_render.py`.
        return 0.0

    async def _repair_unrecorded_decision(self, _user, _assistant) -> None:
        await asyncio.sleep(_REPAIR_SLEEP)
        self.repaired = True

    chat = Advisor.chat
    _record_turn_timing = Advisor._record_turn_timing


@pytest.mark.llm
class TestTheReplyPathBoundaryIsWhereTheAdvisorSaysItIs:
    """The repair's seconds are off-path — measured, not asserted in a comment.

    `Advisor.chat_stream` has always carried the claim ("After the stream, so the
    person's reply is never delayed by the repair"), and this archive's whole
    method is that a rule stated in prose and not enforced by the assembly is a
    rule that eventually is not true. `_ensure_pathways_before_closing` runs
    inside that repair, which is why the archive's off-path share came out at 2%
    of wall clock — a number worth being able to re-check rather than re-derive.
    """

    async def test_repair_seconds_land_off_path_not_on_it(self):
        advisor = _StubAdvisor()

        with scope("sid-test"):
            reply = await advisor.chat("I think I have decided.")

        assert reply == "counsel"
        assert advisor.repaired  # the repair really ran inside the timed region
        timing = advisor.last_turn_timing
        assert timing is not None
        # Exact: copied from the facilitator, never re-measured here.
        assert timing.reply_path_s == _REPLY_PATH_S
        # Measured around the repair, so a lower bound is the honest assertion.
        assert timing.off_path_s >= _REPAIR_SLEEP
        # The point of the whole split: the repair's seconds did NOT inflate the
        # interval the person waited.
        assert timing.off_path_s < timing.reply_path_s

    async def test_tool_rounds_come_from_the_conversation(self):
        """Rounds are read off the facilitator, never re-timed by the Advisor.

        Two clocks around the same awaits could only disagree, and the loop's
        owner is the one that can see round boundaries.
        """
        rounds = (
            ToolRound(names=("anchor",), seconds=4.0),
            ToolRound(names=("inspect_node",), seconds=0.5),
        )
        advisor = _StubAdvisor(tool_rounds=rounds)

        with scope("sid-test"):
            await advisor.chat("here is my situation")

        timing = advisor.last_turn_timing
        assert timing.tool_rounds == rounds
        assert timing.tool_seconds == pytest.approx(4.5)
        # 7.5s reply path, 4.5s of it inside tools → 3.0s of generation.
        assert timing.generation_s == pytest.approx(3.0)

    async def test_an_unscoped_turn_still_refuses_to_run(self):
        """Timing must not have loosened the scope guard.

        `require_current_sid()` is the first line of `chat` for a reason —
        unscoped turns save nodes with `sid=None` and silently drop all work. A
        new `try`/`finally` or a moved await is exactly the kind of edit that
        could swallow it.
        """
        advisor = _StubAdvisor()

        with pytest.raises(Exception):
            await advisor.chat("no scope set")

        assert advisor.last_turn_timing is None
