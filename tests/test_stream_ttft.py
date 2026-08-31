"""The streaming path's own instrument: first-chunk latency and per-round usage.

WHY THESE EXIST
===============
`use_brain` hands the streaming caller a raw callable and returns before its own
recording (`raw_call=True`), so until `_record_stream_round` a whole `chat_stream`
turn contributed NOTHING to any census — every token and latency figure the
framework has published came from the non-streaming path alone. That matters right
now for one specific reason: the prompt-cache fix is a measured cost win whose
LATENCY effect is unmeasured, because `CallRecord.seconds` is whole-call wall time
and output length swamps it. Prefill happens before the first token, so
`first_token_seconds` is where the effect is or nowhere.

An instrument nobody can check is worse than none, and every failure here is
silent — a wrong number still prints. So these tests pin the four ways it could
lie: recording the consumer's time as the provider's, missing the round that
usually is the only round, reading usage before it exists, and reporting a
confident cache share from the wrong token convention.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Optional

import pytest
from mirascope.llm import (TextChunk, ThoughtChunk, ToolCallEndChunk,
                          ToolCallStartChunk)
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import (ResponseComplete,
                                                       TextDelta)
from dialectical_framework.utils.call_census import CallCensus, call_census


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override autouse fixture — these tests never touch the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override autouse fixture — these tests never touch the DB."""
    yield


class _Reply(BaseModel):
    message: str = Field(description="Response message")


class _Usage:
    """Mirascope's `Usage`, as the streaming decoder fills it in: cache tokens are
    NOT folded into `input_tokens` on this path (`decode.py:286`)."""

    def __init__(self, input_tokens=0, cache_read_tokens=0, cache_write_tokens=0):
        self.input_tokens = input_tokens
        self.output_tokens = 40
        self.cache_read_tokens = cache_read_tokens
        self.cache_write_tokens = cache_write_tokens


class _ToolCall:
    def __init__(self, name: str, args: Optional[dict] = None):
        self.name = name
        self.args = json.dumps(args) if args else ""


class _Stream:
    """A stream whose timing is controllable and whose usage appears only once it
    has been drained, exactly as Mirascope's does.

    `usage` starting at None and filling during iteration is not decoration: it is
    the reason `_record_stream_round` is called after the chunk loop rather than
    around it, and a mock that pre-populated it would let a wrong implementation
    pass.
    """

    def __init__(
        self,
        *,
        chunks: list,
        tool_calls: Optional[list] = None,
        tool_outputs: Optional[list] = None,
        usage: Optional[_Usage] = None,
        open_delay: float = 0.0,
        next_round: Optional["_Stream"] = None,
    ):
        self._chunks = chunks
        self.tool_calls = tool_calls or []
        self._tool_outputs = tool_outputs or []
        self._final_usage = usage
        self._open_delay = open_delay
        self._next_round = next_round
        self.usage = None
        self.messages = [{"role": "assistant", "content": "x"}]

    async def chunk_stream(self):
        # The provider's think time: no HTTP request is issued until the first
        # `__anext__`, so this is where a real stream's first-token wait happens.
        if self._open_delay:
            await asyncio.sleep(self._open_delay)
        for chunk in self._chunks:
            yield chunk
        self.usage = self._final_usage

    async def execute_tools(self):
        return self._tool_outputs

    async def resume(self, outputs):
        assert self._next_round is not None, "resumed a stream with no next round"
        return self._next_round


class _Call:
    def __init__(self, stream: _Stream):
        self._stream = stream

    async def stream(self) -> _Stream:
        return self._stream


def _facilitator(stream: _Stream, reply: str = "done") -> ConversationFacilitator:
    facilitator = ConversationFacilitator(tools=[lambda: None])

    async def _get_tools_call():
        return _Call(stream)

    async def _call_with_response_model(_model):
        return _Reply(message=reply)

    facilitator._get_tools_call = _get_tools_call  # type: ignore[method-assign]
    facilitator._call_with_response_model = _call_with_response_model  # type: ignore[method-assign]
    return facilitator


async def _drain(facilitator, *, consumer_delay: float = 0.0) -> list:
    events = []
    async for event in facilitator.submit_stream(_Reply, "hello"):
        if consumer_delay and isinstance(event, TextDelta):
            await asyncio.sleep(consumer_delay)
        events.append(event)
    return events


@pytest.mark.asyncio
class TestTheStreamingRoundReachesTheCensus:
    async def test_a_tool_free_turn_records_its_one_round(self):
        """The round that breaks out of the loop is usually the ONLY round, so a
        record written after the `break` would miss every ordinary turn."""
        stream = _Stream(
            chunks=[TextChunk(delta="hi "), TextChunk(delta="there")],
            usage=_Usage(input_tokens=1_024, cache_read_tokens=18_075),
        )
        census = CallCensus()
        with call_census(census):
            await _drain(_facilitator(stream))

        assert census.count == 1
        record = census.calls[0]
        assert record.caller == "ConversationFacilitator.submit_stream"
        assert record.format_name is None
        assert record.cache_read_tokens == 18_075
        assert record.uncached_input_tokens == 1_024
        assert record.prefill_tokens == 19_099

    async def test_the_streaming_token_convention_is_declared_not_guessed(self):
        """A big uncached dump against a smaller cache read: the arithmetic
        fallback would subtract the read back out and report a 0.72 cache share
        instead of 0.42. The caller knows which decoder produced these numbers, so
        it says so."""
        stream = _Stream(
            chunks=[TextChunk(delta="x")],
            usage=_Usage(input_tokens=25_000, cache_read_tokens=18_075),
        )
        census = CallCensus()
        with call_census(census):
            await _drain(_facilitator(stream))

        assert census.calls[0].uncached_input_tokens == 25_000
        assert census.cache_read_share == pytest.approx(18_075 / 43_075)

    async def test_a_round_the_provider_gave_no_prefill_for_is_unmeasured(self):
        """Mirascope reads streaming usage only from `message_delta`, whose token
        fields are optional. Output tokens alone must not be recorded as "zero
        prefill, so caching did nothing"."""
        stream = _Stream(chunks=[TextChunk(delta="x")], usage=_Usage())
        census = CallCensus()
        with call_census(census):
            await _drain(_facilitator(stream))

        assert census.count == 1
        assert census.calls_with_usage == 0
        assert census.calls[0].prefill_tokens is None

    async def test_each_tool_round_is_its_own_record(self):
        """One record per provider round-trip, each carrying its OWN prefill.

        The no-accumulation half is checked against Mirascope's source, not here:
        `base_provider.py:1253-1284` rebuilds the messages and calls `stream_async`,
        so `resume()` yields a response whose `usage` starts at `None`. This mock's
        `resume` returns a pre-built stream and therefore cannot accumulate even if
        the real one did — what it pins is the recording site making one record per
        round and attributing each round's figures to that round.
        """
        second = _Stream(
            chunks=[TextChunk(delta="the answer")],
            usage=_Usage(input_tokens=2_000, cache_read_tokens=18_075),
        )
        first = _Stream(
            chunks=[TextChunk(delta="let me look")],
            tool_calls=[_ToolCall("anchor", {"intent": "trust"})],
            tool_outputs=["{}"],
            usage=_Usage(input_tokens=1_024, cache_read_tokens=18_075),
            next_round=second,
        )
        census = CallCensus()
        with call_census(census):
            await _drain(_facilitator(first))

        assert census.count == 2
        assert [c.uncached_input_tokens for c in census.calls] == [1_024, 2_000]
        # The arm comparison a caching probe needs is the FIRST round, which is why
        # `mean_first_token_s` is documented as a summary and not the statistic.
        assert min(census.calls, key=lambda c: c.started).uncached_input_tokens == 1_024


@pytest.mark.asyncio
class TestWhatTheSecondsMayNotInclude:
    async def test_the_consumers_time_is_not_recorded_as_the_providers(self):
        """The yields are INSIDE the chunk loop, so without subtracting the
        suspended intervals a slowly-rendering host would read as a slowly-
        responding model — and `parallelism` would blame the model for the
        terminal."""
        stream = _Stream(
            chunks=[TextChunk(delta="a"), TextChunk(delta="b"), TextChunk(delta="c")],
            usage=_Usage(input_tokens=100),
        )
        census = CallCensus()
        wall_started = asyncio.get_running_loop().time()
        with call_census(census):
            await _drain(_facilitator(stream), consumer_delay=0.05)
        wall = asyncio.get_running_loop().time() - wall_started

        # Three deltas at 50ms each is 150ms the host spent, and none of it is
        # ours. Bounded generously; the point is that it is not ~0.15s.
        assert wall >= 0.15, wall
        assert census.calls[0].seconds < 0.10, census.calls[0].seconds

    async def test_the_recorded_interval_is_the_duration_not_the_wall_span(self):
        """`ended` is `started + seconds`, so subtracting the consumer's time from
        `seconds` also shortens the INTERVAL — deliberately. `busy_s` is a union of
        these intervals, and consumer time is not an LLM call, so it belongs in the
        `wall - busy_s` remainder rather than inside it.

        The derivation assertion is tautological by construction (`record_call` sets
        `ended = started + seconds`), and is kept as a pin on that derivation because
        it is what makes the second assertion the real one: the interval closes
        BEFORE the wall clock does, and by roughly the consumer's share.
        """
        stream = _Stream(
            chunks=[TextChunk(delta="a"), TextChunk(delta="b")],
            usage=_Usage(input_tokens=100),
        )
        census = CallCensus()
        # `time.monotonic()` and not the loop clock: these are compared against the
        # record's own absolute stamps, which `record_call` takes from `monotonic`.
        wall_started = time.monotonic()
        with call_census(census):
            await _drain(_facilitator(stream), consumer_delay=0.05)
        wall_ended = time.monotonic()

        record = census.calls[0]
        assert record.ended - record.started == pytest.approx(record.seconds)
        # Two deltas at 50ms: the interval must fall short of the wall span by
        # about that much, which is the thing the tautology alone cannot show.
        assert record.ended < wall_ended - 0.08, (record.ended, wall_ended)
        assert wall_started <= record.started

    async def test_first_chunk_latency_covers_the_wait_before_anything_arrived(self):
        stream = _Stream(
            chunks=[TextChunk(delta="a"), TextChunk(delta="b")],
            usage=_Usage(input_tokens=100),
            open_delay=0.08,
        )
        census = CallCensus()
        with call_census(census):
            await _drain(_facilitator(stream), consumer_delay=0.05)

        record = census.calls[0]
        assert record.first_token_seconds is not None
        assert record.first_token_seconds >= 0.08
        # Immune to the consumer, unlike `seconds`: nothing is yielded before the
        # first chunk arrives, so there is no suspension to subtract.
        assert record.first_token_seconds < 0.13, record.first_token_seconds
        assert census.calls_with_first_token == 1
        assert census.mean_first_token_s == pytest.approx(
            record.first_token_seconds
        )


@pytest.mark.asyncio
class TestTheTurnLevelFigure:
    async def test_it_measures_from_the_turns_start_not_the_rounds(self):
        stream = _Stream(
            chunks=[TextChunk(delta="hi")], usage=_Usage(input_tokens=100)
        )
        facilitator = _facilitator(stream)
        await _drain(facilitator)

        assert facilitator.last_submit_first_delta_s is not None
        assert facilitator.last_submit_first_delta_s <= facilitator.last_submit_seconds

    async def test_a_silent_first_round_puts_it_after_the_tool(self):
        """The Advisor is contracted to call tools without narrating first, so this
        is the COMMON shape, and it is why the field is not called `ttft`: what it
        reports here is a tool round, not a prefill.

        "Silent" means silent to the HOST, not empty on the wire — a tool-only round
        still emits `ToolCallStartChunk`/`ToolCallEndChunk`, which the delta filter
        skips. That distinction is the whole point of keeping `first_chunk_at` and
        `first_delta_at` apart: round 1 has a first-token reading (the provider did
        answer, promptly) and yet nothing reached the screen, and an instrument that
        conflated them would report this turn's wait as sub-second.
        """
        second = _Stream(
            chunks=[TextChunk(delta="the answer")], usage=_Usage(input_tokens=200)
        )
        first = _Stream(
            chunks=[
                ToolCallStartChunk(id="tc1", name="anchor"),
                ToolCallEndChunk(id="tc1"),
            ],
            tool_calls=[_ToolCall("anchor")],
            tool_outputs=["{}"],
            usage=_Usage(input_tokens=100),
            next_round=second,
        )
        facilitator = _facilitator(first)
        census = CallCensus()
        with call_census(census):
            events = await _drain(facilitator)

        # Nothing renderable was yielded by round 1 — the tool chunks are not deltas.
        assert not any(isinstance(e, TextDelta) for e in events[:1])
        # Both rounds answered promptly; the census says so for each separately.
        assert census.calls[0].first_token_seconds is not None
        assert census.calls[1].first_token_seconds is not None
        # And the person's wait is the LATER one, because round 1 showed them
        # nothing. This is the assertion that would fail if the two were conflated.
        assert facilitator.last_submit_first_delta_s is not None
        assert (
            facilitator.last_submit_first_delta_s
            > census.calls[0].first_token_seconds
        )

    async def test_a_thought_counts_as_something_on_screen(self):
        """`ThinkingDelta` is yielded to the host, so the wait on a blank screen
        ended whether or not the host chose to render it."""
        stream = _Stream(
            chunks=[ThoughtChunk(delta="hmm"), TextChunk(delta="hi")],
            usage=_Usage(input_tokens=100),
        )
        facilitator = _facilitator(stream)
        await _drain(facilitator)
        assert facilitator.last_submit_first_delta_s is not None

    async def test_the_non_streaming_path_leaves_it_unset(self):
        """`None`, not 0.0: a turn that streamed nothing has no answer to give, and
        a zero would read as instant."""
        facilitator = ConversationFacilitator(tools=[])

        async def _call_with_response_model(_model):
            return _Reply(message="done")

        facilitator._call_with_response_model = _call_with_response_model  # type: ignore[method-assign]
        events = await _drain(facilitator)

        assert isinstance(events[-1], ResponseComplete)
        assert facilitator.last_submit_first_delta_s is None

    async def test_a_streamed_turn_does_not_leak_into_the_next_submit(self):
        """The facilitator is reused across turns, so the reset has to happen on
        both paths — otherwise a non-streaming turn reports the previous streamed
        turn's figure as its own."""
        stream = _Stream(
            chunks=[TextChunk(delta="hi")], usage=_Usage(input_tokens=100)
        )
        facilitator = _facilitator(stream)
        await _drain(facilitator)
        assert facilitator.last_submit_first_delta_s is not None

        await facilitator.submit(_Reply, "again")
        assert facilitator.last_submit_first_delta_s is None


@pytest.mark.asyncio
class TestTheInstrumentCannotBreakTheTurn:
    async def test_a_census_failure_does_not_interrupt_the_stream(self):
        """Observability runs after the person has already read half their answer.
        A raising recorder would take the turn down at the worst possible moment."""
        stream = _Stream(
            chunks=[TextChunk(delta="hi")], usage=_Usage(input_tokens=100)
        )
        facilitator = _facilitator(stream)
        events = await _drain(facilitator)  # sanity: the happy path works
        assert isinstance(events[-1], ResponseComplete)

        import dialectical_framework.agents.conversation_facilitator as module

        original = module.prefill_token_kwargs
        module.prefill_token_kwargs = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("boom")
        )
        try:
            events = await _drain(
                _facilitator(
                    _Stream(
                        chunks=[TextChunk(delta="hi")], usage=_Usage(input_tokens=100)
                    )
                )
            )
        finally:
            module.prefill_token_kwargs = original

        assert isinstance(events[-1], ResponseComplete)
