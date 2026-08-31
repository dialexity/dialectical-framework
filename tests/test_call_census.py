"""A slow tool is slow for one of two reasons, and the census must tell them apart.

With the parse curve flat, "was that wait work or sleep?" is answered — it is work.
The next question decides what to do about it: **many calls, or a long chain?**
Fan-out latency shrinks by asking for less; chain latency shrinks by restructuring
the chain, and adding workers to a chain does nothing at all. r26 measured
`explore` at a 196.0s median with no way to tell which it had.

So the load-bearing assertions here are not the totals — they are the two ways
this measurement could lie:

1. **A gathered call must land on the census.** Fan-out IS the subject, and an
   `asyncio` task inherits a COPY of the context, so a plain `set()` in a child
   would be invisible to the parent. Losing gathered calls would make every
   fanned-out pipeline read as perfectly sequential — manufacturing the exact
   conclusion the module exists to test. `TestGatheredCallsAreNotLost` is that.
2. **Concurrent calls must not be summed into wall clock.** `busy_s` is a UNION.
   Summing two overlapping 40s calls into 80s of "busy" would report more wall
   clock than the clock allows and inflate every parallelism figure derived from
   it. `TestBusyIsAUnionNotASum` is that.

No LLM and no graph: intervals and arithmetic, with one integration test at the
`use_brain` seam using a fake provider.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from dialectical_framework.utils import use_brain as use_brain_module
from dialectical_framework.utils.call_census import (CallCensus, CallRecord,
                                                     call_census,
                                                     current_call_census,
                                                     record_call)


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


def _census_of(*intervals: tuple[float, float], caller: str = "Concern.resolve") -> CallCensus:
    """A census built from explicit (start, end) pairs, so overlap is the input."""
    census = CallCensus()
    census.calls = [
        CallRecord(caller=caller, seconds=end - start, started=start, ended=end)
        for start, end in intervals
    ]
    return census


class TestNoCensusInstalledCostsNothing:
    """Most `use_brain` callers are pipelines nobody is measuring."""

    def test_recording_without_a_census_is_a_no_op(self):
        record_call("Whatever.resolve", seconds=1.0, started=0.0)  # must not raise

    def test_current_census_is_none_when_uninstalled(self):
        assert current_call_census() is None


class TestBusyIsAUnionNotASum:
    """`busy_s` is wall time with a call in flight, and overlap is the whole point."""

    def test_two_fully_overlapping_calls_cost_one_call_of_wall_clock(self):
        census = _census_of((0.0, 40.0), (0.0, 40.0))

        assert census.provider_s == pytest.approx(80.0)
        assert census.busy_s == pytest.approx(40.0)
        assert census.parallelism == pytest.approx(2.0)

    def test_sequential_calls_report_parallelism_of_one(self):
        """The signature of a chain: the wall clock IS the provider time."""
        census = _census_of((0.0, 10.0), (10.0, 20.0), (20.0, 30.0))

        assert census.provider_s == pytest.approx(30.0)
        assert census.busy_s == pytest.approx(30.0)
        assert census.parallelism == pytest.approx(1.0)

    def test_partial_overlap_merges_rather_than_adds(self):
        census = _census_of((0.0, 10.0), (5.0, 20.0))

        assert census.provider_s == pytest.approx(25.0)
        assert census.busy_s == pytest.approx(20.0)

    def test_a_gap_between_calls_is_not_busy(self):
        """The gap is orchestration (or a semaphore queue) and must stay visible.

        If gaps were swallowed, graph writes and queueing would be billed to the
        provider and every latency post-mortem would start in the wrong place.
        """
        census = _census_of((0.0, 10.0), (100.0, 110.0))

        assert census.busy_s == pytest.approx(20.0)

    def test_nested_intervals_do_not_shorten_the_union(self):
        """A short call wholly inside a long one must not truncate it.

        The merge tracks the running MAX end, not the latest end — sorting by
        start alone would let `(0,100)` be followed by `(1,2)` and close the
        window at 2.
        """
        census = _census_of((0.0, 100.0), (1.0, 2.0))

        assert census.busy_s == pytest.approx(100.0)

    def test_an_empty_census_reports_zeroes_not_a_division_error(self):
        census = CallCensus()

        assert (census.count, census.provider_s, census.busy_s) == (0, 0.0, 0.0)
        assert census.parallelism == 0.0
        assert census.depth == 0.0
        assert census.mean_call_s == 0.0


class TestDepthReadsAsSequentialStages:
    """An estimate, and labelled as one — it cannot see dependencies."""

    def test_a_four_deep_chain_of_equal_calls_reads_as_four(self):
        census = _census_of((0.0, 10.0), (10.0, 20.0), (20.0, 30.0), (30.0, 40.0))

        assert census.depth == pytest.approx(4.0)

    def test_a_wide_fan_out_reads_as_one_stage_deep(self):
        """Twelve concurrent calls are one stage, however much time they buy."""
        census = _census_of(*[(0.0, 10.0)] * 12)

        assert census.count == 12
        assert census.provider_s == pytest.approx(120.0)
        assert census.depth == pytest.approx(1.0)
        assert census.parallelism == pytest.approx(12.0)


class TestTheLabelSurvivesTheOneSeam:
    """Grouping by `caller` alone is useless, and a real run proved it.

    All 33 structured DTOs reach the provider through ONE `@use_brain` site inside
    `ConversationFacilitator`, so `__qualname__` is a constant for every one of
    them. `probe_explore_cost.py`'s first real run put 49 of its 50 calls in a
    single `_call_with_response_model.<locals>._llm_call` row — a table naming the
    wrapper, with nothing in it anybody could act on.
    """

    def test_the_dto_distinguishes_calls_that_share_a_caller(self):
        seam = "ConversationFacilitator._call_with_response_model.<locals>._llm_call"
        census = CallCensus()
        census.calls = [
            CallRecord(caller=seam, seconds=30.0, started=0.0, ended=30.0, format_name="TetradDto"),
            CallRecord(caller=seam, seconds=5.0, started=0.0, ended=5.0, format_name="GroundingDto"),
        ]

        rows = census.by_caller()

        assert len(rows) == 2, "one seam, two DTOs — the table must show two rows"
        assert rows[0][0].startswith("TetradDto")
        assert rows[1][0].startswith("GroundingDto")

    def test_the_decorator_artifact_is_stripped_from_the_label(self):
        """`.<locals>._llm_call` is how `use_brain` wraps the method, never a caller."""
        record = CallRecord(
            caller="BuildWheels._resolve_auto_preset.<locals>._resolve",
            seconds=1.0,
            started=0.0,
            ended=1.0,
        )

        assert record.label == "BuildWheels._resolve_auto_preset"

    def test_a_formatless_call_is_still_identified_by_its_caller(self):
        """Raw/tool calls have no DTO, and must not all become "None"."""
        record = CallRecord(caller="Advisor.chat", seconds=1.0, started=0.0, ended=1.0)

        assert record.label == "Advisor.chat"

    def test_the_same_dto_from_two_paths_stays_distinguishable(self):
        """Two code paths can request one DTO, so the caller is kept alongside it."""
        a = CallRecord(caller="X.one", seconds=1.0, started=0.0, ended=1.0, format_name="Dto")
        b = CallRecord(caller="Y.two", seconds=1.0, started=0.0, ended=1.0, format_name="Dto")

        assert a.label != b.label


class TestByCallerPointsAtTheConcernToGoLookAt:
    def test_rows_are_ordered_by_time_not_by_count(self):
        """One 90s call outranks thirty 1s ones for "where do I look first"."""
        census = CallCensus()
        census.calls = [
            CallRecord(caller="Slow.resolve", seconds=90.0, started=0.0, ended=90.0),
            *[
                CallRecord(caller="Chatty.resolve", seconds=1.0, started=float(i), ended=i + 1.0)
                for i in range(30)
            ],
        ]

        rows = census.by_caller()

        assert rows[0] == ("Slow.resolve", 1, pytest.approx(90.0))
        assert rows[1] == ("Chatty.resolve", 30, pytest.approx(30.0))


class TestGatheredCallsAreNotLost:
    """The property the whole module depends on — see this file's docstring.

    `ExplorationPipeline` runs wheels concurrently and `ExploreTransformations`
    fans out further inside one tool, so MOST calls the census exists to count
    happen inside a gathered child.
    """

    @pytest.mark.asyncio
    async def test_calls_from_gathered_children_reach_the_parent(self):
        async def child(caller: str) -> None:
            await asyncio.sleep(0)  # a real suspension, so this is a real task
            record_call(caller, seconds=5.0, started=0.0)

        with call_census() as census:
            await asyncio.gather(child("A.resolve"), child("B.resolve"), child("C.resolve"))

        assert census.count == 3
        assert census.provider_s == pytest.approx(15.0)
        assert {caller for caller, _, _ in census.by_caller()} == {
            "A.resolve",
            "B.resolve",
            "C.resolve",
        }

    @pytest.mark.asyncio
    async def test_a_grandchild_two_tasks_deep_still_reaches_it(self):
        """The real shape: a gathered tool round fans out again inside itself."""

        async def grandchild() -> None:
            await asyncio.sleep(0)
            record_call("Inner.resolve", seconds=2.0, started=0.0)

        async def child() -> None:
            await asyncio.sleep(0)
            await asyncio.gather(grandchild(), grandchild())

        with call_census() as census:
            await asyncio.gather(child(), child())

        assert census.count == 4


class TestNestingKeepsBothLevelsInformed:
    def test_an_inner_census_does_not_blind_the_outer_one(self):
        """Otherwise measuring a tool would erase it from the turn's total."""
        with call_census() as turn:
            record_call("Before.resolve", seconds=1.0, started=0.0)
            with call_census() as tool:
                record_call("Inside.resolve", seconds=2.0, started=1.0)
            record_call("After.resolve", seconds=3.0, started=3.0)

        assert tool.count == 1
        assert tool.provider_s == pytest.approx(2.0)
        assert turn.count == 3
        assert turn.provider_s == pytest.approx(6.0)

    def test_an_existing_census_can_accumulate_across_separate_blocks(self):
        census = CallCensus()

        with call_census(census):
            record_call("One.resolve", seconds=1.0, started=0.0)
        with call_census(census):
            record_call("Two.resolve", seconds=1.0, started=1.0)

        assert census.count == 2

    def test_the_innermost_census_is_the_one_returned(self):
        with call_census() as outer:
            assert current_call_census() is outer
            with call_census() as inner:
                assert current_call_census() is inner
            assert current_call_census() is outer


@pytest.mark.llm
class TestTheUseBrainSeam:
    """One integration test, with a fake provider: the census must see real calls."""

    @pytest.fixture(autouse=True)
    def mock_llm(self):
        """Opt out of the autouse mock brain: it replaces the decorator under test."""
        yield

    def _install(self, monkeypatch, delay: float, responses: list) -> None:
        monkeypatch.setattr(use_brain_module, "_trace_generation", lambda **_: None)
        # The retry delay is zeroed at the CONSTANT, not by patching
        # `asyncio.sleep`. `use_brain_module.asyncio` is the global module, so
        # patching its `sleep` also neuters the `await asyncio.sleep(delay)` in
        # the fake provider below — which is this file's own measurement. It cost
        # two failures to notice, and the failure mode is quiet: every call
        # returns in ~2 microseconds and the census reports a perfectly
        # sequential fan-out, i.e. exactly the wrong conclusion, convincingly.
        monkeypatch.setattr(use_brain_module, "_PARSE_RETRY_DELAY_S", 0.0)

        def _fake_llm_call(_model, **_params):
            def _decorator(_fn):
                async def _inner():
                    # A REAL await, so `started`/`ended` are real intervals and
                    # the union arithmetic is exercised rather than simulated.
                    await asyncio.sleep(delay)
                    return responses.pop(0)

                return _inner

            return _decorator

        monkeypatch.setattr(use_brain_module.llm, "call", _fake_llm_call)

    @pytest.mark.asyncio
    async def test_a_successful_call_is_recorded_under_its_qualname(self, monkeypatch):
        self._install(monkeypatch, delay=0.02, responses=[object()])

        @use_brain_module.use_brain(ai_model="anthropic/claude-x")
        async def _method():
            return None

        with call_census() as census:
            await _method()

        assert census.count == 1
        # `__qualname__`, so a caller is identifiable down to its method — the
        # same name `use_brain` gives the Langfuse span.
        assert census.calls[0].caller.endswith("_method")
        assert census.calls[0].seconds >= 0.02

    @pytest.mark.asyncio
    async def test_concurrent_callers_report_parallelism_above_one(self, monkeypatch):
        """The end-to-end version of the claim: real overlap, real union.

        Asserted as a range, not a point — this is wall-clock arithmetic on a
        loaded machine, and pinning 4.0 exactly would make the suite flaky in
        exchange for no extra confidence.
        """
        self._install(monkeypatch, delay=0.05, responses=[object() for _ in range(4)])

        @use_brain_module.use_brain(ai_model="anthropic/claude-x")
        async def _method():
            return None

        started = time.monotonic()
        with call_census() as census:
            await asyncio.gather(*(_method() for _ in range(4)))
        wall = time.monotonic() - started

        assert census.count == 4
        assert census.parallelism > 1.5, (
            "four concurrent calls reported as a chain — either gathered calls "
            "are being lost or `busy_s` is summing instead of merging"
        )
        # Sanity on the other side: the union cannot exceed the wall clock.
        assert census.busy_s <= wall + 0.05

    @pytest.mark.asyncio
    async def test_a_retried_attempt_is_counted_as_provider_time(self, monkeypatch):
        """A round-trip that then failed to parse was still bought and paid for.

        Deliberately overlapping `RetryAccount.failed_attempt_s`, which calls the
        same seconds wasted. Two questions — what did we buy, what did we throw
        away — and a census that skipped failures would understate provider load
        exactly when the framework is misbehaving.
        """
        from mirascope.llm.exceptions import ParseError
        from pydantic import BaseModel

        class _Needs(BaseModel):
            particulars: str

        class _Bad:
            def text(self, sep: str = "\n") -> str:
                return "not json"

            def parse(self):
                raise ParseError("nope", original_exception=ValueError("nope"))

        self._install(monkeypatch, delay=0.01, responses=[_Bad() for _ in range(3)])

        @use_brain_module.use_brain(
            ai_model="anthropic/claude-x", format=_Needs, retry_max=3
        )
        async def _method():
            return None

        with call_census() as census, pytest.raises(ParseError):
            await _method()

        assert census.count == 3, "all three round-trips were provider time"


class TestThePrefillBreakdown:
    """Cache accounting has a third state, and collapsing it is the failure mode.

    `None` means the round-trip reported no usage — which is EVERY streaming call,
    since `use_brain` returns before the retry loop for `raw_call=True`, and every
    tool-loop continuation. `0` means the provider reported it and there was none.
    A reader that treats them alike turns "we did not look" into "caching is off",
    which is the wrong conclusion in the more alarming direction — and in this
    framework `0` is the CORRECT and expected value nearly everywhere, because only
    the Advisor engine clears the 4,096-token minimum cacheable prefix.
    """

    def _record(self, **tokens) -> CallRecord:
        return CallRecord(
            caller="c", seconds=1.0, started=0.0, ended=1.0, **tokens
        )

    def test_unreported_usage_stays_none_not_zero(self):
        assert self._record().prefill_tokens is None

    def test_a_genuine_zero_is_not_unreported(self):
        record = self._record(
            uncached_input_tokens=500, cache_read_tokens=0, cache_write_tokens=0
        )
        assert record.prefill_tokens == 500

    def test_prefill_is_the_sum_however_it_was_billed(self):
        record = self._record(
            uncached_input_tokens=1_000,
            cache_read_tokens=18_000,
            cache_write_tokens=0,
        )
        assert record.prefill_tokens == 19_000

    def test_calls_with_usage_is_the_gate_on_every_token_total(self):
        """A turn can make five provider calls and contribute usage for one, so a
        token sum is only as complete as this count."""
        census = CallCensus()
        census.calls.append(self._record())  # a streamed call: reported nothing
        census.calls.append(
            self._record(
                uncached_input_tokens=1_000,
                cache_read_tokens=18_000,
                cache_write_tokens=0,
            )
        )
        assert census.count == 2
        assert census.calls_with_usage == 1
        assert census.cache_read_tokens == 18_000
        assert census.cache_read_share == pytest.approx(18_000 / 19_000)

    def test_cache_read_share_is_zero_when_nothing_was_measured(self):
        """Same 0.0 as "caching is off", which is why `calls_with_usage` has to be
        read first rather than being an optional extra."""
        census = CallCensus()
        census.calls.append(self._record())
        assert census.cache_read_share == 0.0
        assert census.calls_with_usage == 0


class TestTheTwoTokenConventions:
    """`_prefill_tokens` must survive both of Mirascope's definitions of
    `input_tokens`: the non-streaming decoder pre-adds cache reads and writes
    (`anthropic/_utils/decode.py:99`), the streaming one does not (`:286`)."""

    class _Usage:
        def __init__(self, input_tokens, cache_read_tokens, cache_write_tokens):
            self.input_tokens = input_tokens
            self.cache_read_tokens = cache_read_tokens
            self.cache_write_tokens = cache_write_tokens

    class _Response:
        def __init__(self, usage):
            self.usage = usage

    def _breakdown(self, input_tokens, read, write):
        return use_brain_module._prefill_tokens(
            self._Response(self._Usage(input_tokens, read, write))
        )

    def test_the_pre_adding_convention_is_subtracted_back_out(self):
        assert self._breakdown(19_101, 18_075, 0) == {
            "uncached_input_tokens": 1_026,
            "cache_read_tokens": 18_075,
            "cache_write_tokens": 0,
        }

    def test_the_non_pre_adding_convention_is_taken_as_is(self):
        """A negative difference is PROOF of the streaming convention, since the
        pre-adding one guarantees `input >= read + write`. Clamping to 0 instead
        would report `cache_read_share` of 1.0 — perfect caching announced exactly
        when the instrument has lost track."""
        assert self._breakdown(1_026, 18_075, 0) == {
            "uncached_input_tokens": 1_026,
            "cache_read_tokens": 18_075,
            "cache_write_tokens": 0,
        }

    def test_no_usage_reports_all_three_as_unmeasured(self):
        class _Bare:
            usage = None

        assert use_brain_module._prefill_tokens(_Bare()) == {
            "uncached_input_tokens": None,
            "cache_read_tokens": None,
            "cache_write_tokens": None,
        }

    def test_provider_nones_do_not_become_a_crash_or_a_negative(self):
        assert self._breakdown(500, None, None) == {
            "uncached_input_tokens": 500,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
