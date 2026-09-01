"""A streamed round survives the failures the awaited path already survived.

WHY THIS EXISTS
===============
`await call.stream()` issues no HTTP request. Anthropic's `AsyncMessages.stream`
builds an un-awaited request and returns a manager that sends on `__aenter__`,
which Mirascope defers to the stream's first `__anext__` — and on Bedrock not even
SigV4 signing has happened before that. So the facilitator's old
`_open_stream_with_retry` wrapped local encoding and nothing else, while its
docstring claimed to retry connections: a 429 or a 503 surfaced inside the chunk
loop and took the whole turn down. The SAME failure, on the same model, was
retried up to ten times if the turn happened to go through `submit()` instead.
(The streaming budget is deliberately shorter than that ten — see
`_RATE_LIMIT_RETRY_MAX` — because on this path a person is watching.)

The fix pairs the open with the first chunk as one retryable unit, which is the
largest unit that can still be re-asked — past it, re-asking would duplicate text
already on the person's screen. These tests pin what can go wrong with that: not
retrying what should be, retrying what should not be, retrying forever, putting the
wrong failure on the wrong curve, re-running a turn's tools for a network event, and
letting the ladder's seconds contaminate the prefill measurement the caching and
prompt-size arms are read from.

`TestTheBudgetExitOpensNoFurtherRound` is here rather than in
`test_conversation_tool_budget.py` because it exists for THIS change: once opening a
round costs a request, a loop that ends with one unconsumed is no longer merely
untidy.
"""

from __future__ import annotations

import asyncio
import time
from typing import Optional

import pytest
from mirascope.llm import TextChunk
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import ResponseComplete, TextDelta
from dialectical_framework.utils.call_census import CallCensus, call_census


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override autouse fixture — these tests never touch the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override autouse fixture — these tests never touch the DB."""
    yield


@pytest.fixture(autouse=True)
def no_backoff_sleep(monkeypatch):
    """Run the ladder's curve without paying for it, and record what it asked for.

    The throttle curve starts at 10s, so an unpatched test of two retries would
    sit for 30 seconds. Patched globally rather than on `use_brain`'s import
    because `asyncio.sleep` is looked up on the module at call time; the original
    is captured first so the replacement can still yield to the loop.
    """
    real_sleep = asyncio.sleep
    slept: list[float] = []

    async def _fake(seconds, *args, **kwargs):
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", _fake)
    return slept


#: Captured at import, before `no_backoff_sleep` replaces the module attribute, so
#: a mock that means to take real time still can. Without it the fixture makes the
#: provider's think time free too, and the one test that needs the ladder and the
#: attempt to be distinguishable by clock has nothing to distinguish.
_REAL_SLEEP = asyncio.sleep


class _Reply(BaseModel):
    message: str = Field(description="Response message")


class _Throttled(Exception):
    """Bedrock's throttle as it actually arrives: a message, not a status code.

    `_is_rate_limit_error` matches `"ThrottlingException"` in the text, which is
    the form Mirascope surfaces — so a fake that carried `status_code=429` would
    be testing the branch this provider never takes.
    """

    def __init__(self) -> None:
        super().__init__("ThrottlingException: Too many requests, please throttle")


class _Usage:
    """Mirascope's streaming convention: cache tokens NOT folded into input."""

    def __init__(self, input_tokens: int = 1_000) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = 20
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0


class _ToolCall:
    def __init__(self, name: str, id: str = "tc-1") -> None:
        self.name = name
        self.args = ""
        # `_close_dangling_tool_calls` builds a `ToolOutput` from this, so the id
        # is not decoration: the budget-overrun test below reaches that code.
        self.id = id


class _Stream:
    """A round that either answers or fails, and can be told when to do which.

    `fail_after` is a count of chunks, not a flag, because the retry boundary is
    positional: failing at 0 is retryable (nothing has reached the host) and
    failing at 1 is not (a delta already has). One mock covering both sides keeps
    the two cases honest about being the same code path.
    """

    def __init__(
        self,
        *,
        chunks: Optional[list] = None,
        error: Optional[Exception] = None,
        fail_after: int = 0,
        attempt_delay: float = 0.0,
        tool_calls: Optional[list] = None,
        tool_outputs: Optional[list] = None,
        resumes: Optional[list] = None,
    ) -> None:
        self._chunks = chunks or []
        self._error = error
        self._fail_after = fail_after
        self._attempt_delay = attempt_delay
        #: Empty until the round is DRAINED, exactly as mirascope's is: a
        #: `BaseStreamResponse` starts with empty `tool_calls`/`texts`/`content` and
        #: fills them while its chunks are consumed. Not a detail — that emptiness
        #: is what made `_close_dangling_tool_calls` and `_reuse_written_reply`'s
        #: overrun guard silently no-op on an unconsumed round, so a mock that
        #: pre-populated this could not express the bug the budget exit fixes and
        #: would pass against the broken loop shape.
        self.tool_calls: list = []
        self._pending_tool_calls = tool_calls or []
        self._tool_outputs = tool_outputs or []
        self._resumes = resumes or []
        self.resume_calls = 0
        self.execute_calls = 0
        self.usage = None
        self.messages = [{"role": "assistant", "content": "x"}]

    async def chunk_stream(self):
        if self._attempt_delay:
            await _REAL_SLEEP(self._attempt_delay)
        for index, chunk in enumerate(self._chunks):
            if self._error is not None and index == self._fail_after:
                raise self._error
            yield chunk
        if self._error is not None and self._fail_after >= len(self._chunks):
            raise self._error
        self.tool_calls = list(self._pending_tool_calls)
        self.usage = _Usage()

    async def execute_tools(self):
        self.execute_calls += 1
        return self._tool_outputs

    async def resume(self, _outputs):
        self.resume_calls += 1
        assert self._resumes, "resumed a stream with no next round"
        return self._resumes.pop(0)


def _facilitator(*streams: _Stream) -> ConversationFacilitator:
    """A facilitator whose opener hands out `streams` in order, one per attempt.

    Patched at `_open_tools_stream` and not at `_start_stream_round`: the retry
    ladder and the first-chunk pull are the code under test, so they have to stay
    live. A fresh stream per attempt is not convenience either — Mirascope caches
    consumed chunks on the response and drives a single underlying iterator, so a
    real retry could never reuse the object that just raised.
    """
    facilitator = ConversationFacilitator(tools=[lambda: None])
    remaining = list(streams)
    facilitator.opened = 0  # type: ignore[attr-defined]

    async def _open_tools_stream():
        facilitator.opened += 1  # type: ignore[attr-defined]
        assert remaining, "opened more streams than the test provided"
        return remaining.pop(0)

    async def _call_with_response_model(_model):
        return _Reply(message="extracted")

    facilitator._open_tools_stream = _open_tools_stream  # type: ignore[method-assign]
    facilitator._call_with_response_model = _call_with_response_model  # type: ignore[method-assign]
    return facilitator


async def _drain(facilitator) -> list:
    return [event async for event in facilitator.submit_stream(_Reply, "hello")]


@pytest.mark.asyncio
class TestTheOpenIsRetriedWhereItActuallyFails:
    async def test_a_throttle_on_the_first_chunk_no_longer_ends_the_turn(
        self, no_backoff_sleep
    ):
        """The failure the old ladder could not see, because it arrives one
        `__anext__` after the call it was wrapping."""
        facilitator = _facilitator(
            _Stream(error=_Throttled()),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        events = await _drain(facilitator)

        assert facilitator.opened == 2
        assert isinstance(events[-1], ResponseComplete)
        assert [e.text for e in events if isinstance(e, TextDelta)] == ["hi"]
        assert no_backoff_sleep == [10.0], "the throttle curve, not the connect one"

    async def test_the_retry_is_accounted_to_the_turn(self, no_backoff_sleep):
        """A retry nobody records is how r26 reported 750s of sleep as the price
        of a tool. This one lands on the turn's account under the same kind the
        awaited path uses, so `RetryAccount.kinds` stays readable across paths."""
        facilitator = _facilitator(
            _Stream(error=_Throttled()),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        await _drain(facilitator)

        account = facilitator.last_submit_retries
        assert account.count == 1
        assert account.kinds["rate_limit"] == 1
        assert account.sleep_s == 10.0

    async def test_a_defect_of_ours_is_not_retried(self, no_backoff_sleep):
        """Waiting does not change a deterministic answer. The old ladder caught
        bare `Exception` and slept 15s over three attempts on a malformed request
        before surfacing it — the same argument that flattened the parse curve."""
        facilitator = _facilitator(_Stream(error=ValueError("bad request shape")))

        with pytest.raises(ValueError):
            await _drain(facilitator)

        assert facilitator.opened == 1
        assert no_backoff_sleep == []
        assert facilitator.last_submit_retries.count == 0

    async def test_a_persistent_throttle_surfaces_instead_of_looping(
        self, no_backoff_sleep
    ):
        """Bounded per kind: a service that keeps saying no is an outage, and a
        ladder with no ceiling would hold a person's turn open indefinitely."""
        facilitator = _facilitator(*[_Stream(error=_Throttled()) for _ in range(5)])

        with pytest.raises(_Throttled):
            await _drain(facilitator)

        # Budget 3 means two retries and then the third failure propagates.
        assert facilitator.opened == 3
        assert no_backoff_sleep == [10.0, 20.0], "and the curve doubled"

    async def test_a_failure_after_the_first_chunk_is_not_retried(
        self, no_backoff_sleep
    ):
        """Past the first chunk the host has text on screen, so re-asking would
        duplicate it. The line has to be drawn somewhere and this is where."""
        facilitator = _facilitator(
            _Stream(
                chunks=[TextChunk(delta="half an "), TextChunk(delta="answer")],
                error=_Throttled(),
                fail_after=1,
            ),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        with pytest.raises(_Throttled):
            await _drain(facilitator)

        assert facilitator.opened == 1
        assert no_backoff_sleep == []


def _server_error() -> Exception:
    """A Bedrock 503 in the shape it actually arrives: the status is in the TEXT.

    `_is_transient_server_error` reads `status_code` first, but Mirascope surfaces
    the code inside the message string far more often, so a fake carrying the
    attribute would test the branch this provider rarely takes.
    """
    return Exception(
        "Error code: 503 - {'message': 'Bedrock is unable to process your request'}"
    )


@pytest.mark.asyncio
class TestEachKindGetsItsOwnCurve:
    """Throttles are not the only thing that arrives on the first `__anext__`.

    The three curves differ by more than taste — a connect blip clears in seconds
    or never, a 5xx is an outage or a hiccup, a throttle is the service telling us
    to wait — and the ladder tunes them separately. If only the throttle path were
    exercised, a `_transient_kind` that silently returned "rate_limit" for all
    three would pass the suite and make every connect blip cost 30s.
    """

    async def test_a_connect_blip_gets_the_connect_curve(self, no_backoff_sleep):
        facilitator = _facilitator(
            # Named, not subclassed: `_is_connection_error` matches on the class
            # NAME, since Mirascope re-raises provider faults as its own classes.
            _Stream(error=ConnectionError("connection reset by peer")),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        await _drain(facilitator)

        assert facilitator.opened == 2
        assert no_backoff_sleep == [2.0], "the connect base, not the throttle's 10s"
        assert facilitator.last_submit_retries.kinds["connection"] == 1

    async def test_a_provider_503_gets_the_server_curve(self, no_backoff_sleep):
        facilitator = _facilitator(
            _Stream(error=_server_error()),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        await _drain(facilitator)

        assert facilitator.opened == 2
        assert no_backoff_sleep == [5.0]
        assert facilitator.last_submit_retries.kinds["server"] == 1

    async def test_the_budgets_are_counted_per_kind_not_shared(
        self, no_backoff_sleep
    ):
        """Four failures survive because they are two of each, and a shared
        counter would have surfaced the third one.

        This is the ladder's own arrangement (`_CONNECT_RETRY_MAX` and
        `_SERVER_RETRY_MAX` are separate from `retry_max`) and it matters on a real
        turn: a link glitch on the way up must not spend the budget a throttle
        later needs, or the turn dies to a condition that was going to clear.
        """
        facilitator = _facilitator(
            _Stream(error=ConnectionError("reset")),
            _Stream(error=ConnectionError("reset")),
            _Stream(error=_Throttled()),
            _Stream(error=_Throttled()),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        events = await _drain(facilitator)

        assert facilitator.opened == 5
        assert isinstance(events[-1], ResponseComplete)
        # Each curve doubled from its OWN base, independently.
        assert no_backoff_sleep == [2.0, 4.0, 10.0, 20.0]
        assert facilitator.last_submit_retries.kinds == {
            "connection": 2,
            "rate_limit": 2,
        }


@pytest.mark.asyncio
class TestTheResumeLegToo:
    async def test_a_throttle_between_tool_rounds_is_retried(self, no_backoff_sleep):
        """The gap this closes was the more likely one of the two in practice: by
        the time a tool round has finished, the turn has already spent minutes of
        provider quota, so a throttle is MORE likely there than at the open — and
        losing it there throws away the tool work as well as the turn."""
        answer = _Stream(chunks=[TextChunk(delta="the answer")])
        first = _Stream(
            chunks=[TextChunk(delta="looking")],
            tool_calls=[_ToolCall("anchor")],
            tool_outputs=["{}"],
            resumes=[_Stream(error=_Throttled()), answer],
        )
        facilitator = _facilitator(first)
        events = await _drain(facilitator)

        assert first.resume_calls == 2, "the same round re-asked, not a new open"
        assert facilitator.opened == 1
        assert isinstance(events[-1], ResponseComplete)
        assert [e.text for e in events if isinstance(e, TextDelta)] == [
            "looking",
            "the answer",
        ]
        assert facilitator.last_submit_retries.kinds["rate_limit"] == 1

    async def test_a_retried_resume_does_not_re_execute_the_tools(
        self, no_backoff_sleep
    ):
        """`operation` must be safe to call again, and on the resume leg the thing
        that must NOT be inside it is the tool work.

        The outputs are already in hand when the resume is attempted, so a retry
        re-sends them rather than re-deriving them. This is the assertion that
        would catch someone "simplifying" the retry unit to include
        `execute_tools()`: a throttle would then re-run `anchor` or `explore`,
        which is minutes of concern calls and a second write of whatever they
        persist — the expensive half of the turn, repeated for a network event.
        """
        answer = _Stream(chunks=[TextChunk(delta="the answer")])
        first = _Stream(
            chunks=[TextChunk(delta="looking")],
            tool_calls=[_ToolCall("anchor")],
            tool_outputs=["{}"],
            resumes=[_Stream(error=_Throttled()), answer],
        )
        await _drain(_facilitator(first))

        assert first.resume_calls == 2, "the round was re-asked"
        assert first.execute_calls == 1, "but the tools ran once"


@pytest.mark.asyncio
class TestTheBudgetExitOpensNoFurtherRound:
    """The last round is consumed and streamed like any other; what the budget exit
    refuses is to run its tools and open a round to report them to.

    Opening a round used to be free, and the loop relied on that without saying so:
    it ended with an unconsumed `resume()` dangling, which cost nothing because no
    HTTP happens until the first `__anext__`. Pairing the open with the first chunk
    removed that safety — the same shape now buys a round-trip whose answer nobody
    reads, and the ladder wraps it, so a throttle there would sleep and then raise
    out of `submit_stream` AFTER the reply had already been streamed: no
    `ResponseComplete`, and the turn recorded as a failure it wasn't.

    The dangling round was never harmless, though, which is the more important half.
    An unconsumed mirascope stream reports no tool calls and empty content, and
    everything below the loop ran against it — so the overrun exit returned the
    previous round's narration as the reply, left an empty assistant message as the
    last history entry, and could not close the unanswered calls. See the loop's own
    comment in `submit_stream`.
    """

    async def test_the_overrun_exit_opens_no_further_round(self, no_backoff_sleep):
        overrunning = _Stream(
            chunks=[TextChunk(delta="still working")],
            tool_calls=[_ToolCall("explore", id="tc-2")],
            tool_outputs=["{}"],
        )
        first = _Stream(
            chunks=[TextChunk(delta="looking")],
            tool_calls=[_ToolCall("anchor")],
            tool_outputs=["{}"],
            resumes=[overrunning],
        )
        facilitator = _facilitator(first)
        census = CallCensus()
        with call_census(census):
            events = [
                e
                async for e in facilitator.submit_stream(
                    _Reply, "hello", max_tool_rounds=1
                )
            ]

        # One tool round, two generations — the same arithmetic as `submit`, which
        # is one call plus up to `max_tool_rounds` resumes.
        assert first.execute_calls == 1
        assert first.resume_calls == 1
        assert overrunning.resume_calls == 0, "the round nobody would read"
        assert overrunning.execute_calls == 0, "and its tools, which had nowhere to go"
        # Two streamed rounds, two records. On a real turn there is a THIRD record —
        # the structured extraction, which `@use_brain` records itself; it is absent
        # here only because `_facilitator` stubs `_call_with_response_model`. This
        # assertion is what catches a regression to the old loop shape, where the
        # second round was opened but never consumed and so never recorded.
        assert census.count == 2
        assert isinstance(events[-1], ResponseComplete)

    async def test_the_unanswered_calls_are_closed_so_history_stays_valid(
        self, no_backoff_sleep
    ):
        """Not executing the overrun round's tools means leaving its `tool_use`
        blocks unanswered — which is exactly the state `_close_dangling_tool_calls`
        exists for, and the reason this exit is safe.

        Without it the persisted history ends on an unanswered `tool_use` and every
        later turn 400s citing the same stale id: one overrun bricks the session.
        """
        overrunning = _Stream(
            chunks=[TextChunk(delta="still working")],
            tool_calls=[_ToolCall("explore", id="tc-2")],
            tool_outputs=["{}"],
        )
        first = _Stream(
            tool_calls=[_ToolCall("anchor")],
            tool_outputs=["{}"],
            resumes=[overrunning],
        )
        facilitator = _facilitator(first)
        async for _ in facilitator.submit_stream(_Reply, "hello", max_tool_rounds=1):
            pass

        closing = facilitator._messages[-1]
        outputs = [
            block
            for block in getattr(closing, "content", [])
            if getattr(block, "id", None) == "tc-2"
        ]
        assert len(outputs) == 1, facilitator._messages
        assert ConversationFacilitator._BUDGET_STOP_NOTICE in outputs[0].result


@pytest.mark.asyncio
class TestTheLadderDoesNotContaminateThePrefillReading:
    async def test_first_token_excludes_the_failed_attempt(self, no_backoff_sleep):
        """`first_token_seconds` is the only latency figure a prefill cache can
        move, and `probe_stream_ttft.py` reads it per round to compare arms. A
        retried round that folded its dead attempt into that figure would report a
        10-second prefill and quietly decide the comparison.

        Both quantities are checked here because they are supposed to DISAGREE:
        the person waited through the failed attempt, so `seconds` covers it.
        """
        facilitator = _facilitator(
            _Stream(error=_Throttled(), attempt_delay=0.12),
            _Stream(chunks=[TextChunk(delta="hi")]),
        )
        census = CallCensus()
        started = time.monotonic()
        with call_census(census):
            await _drain(facilitator)
        wall = time.monotonic() - started

        assert wall >= 0.12, wall
        record = census.calls[0]
        assert record.first_token_seconds is not None
        assert record.first_token_seconds < 0.05, record.first_token_seconds
        # The dead attempt is the person's wait, so it stays inside `seconds`.
        assert record.seconds >= 0.12, record.seconds
