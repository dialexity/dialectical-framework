"""What a streamed turn owes even when it does not finish.

WHY THIS EXISTS
===============
`submit_stream` used to assign `last_submit_seconds` after its tool loop, on the
way to the final yield. Every exit that skipped that line left the field at the
`0.0` the reset had put there — and `0.0` is not a gap, it is a claim. It reads as
"instant", it drags down any mean it enters, and the turns it hides are precisely
the expensive ones: the crash after four minutes of tool work, the person who gave
up and closed the tab.

The crash half is not hypothetical. Mirascope raises `NotImplementedError` from
inside the chunk loop on a `redacted_thinking` block, so any turn with
`DIALEXITY_THINKING_LEVEL` set can take that path today.

The abandonment half brings a second obligation with it. An abandoned turn is
suspended inside mirascope's decoder, which holds the HTTP response open in an
`async with`; unwinding an `async for` does not close what it iterates, so without
an explicit close nothing releases the connection until the collector gets round to
the whole response object.

And it brings a THIRD thing, which is not the framework's to guarantee: none of this
runs until the host closes the outermost generator, because `chat_stream` is an async
generator wrapping `submit_stream` and cleanup unwinds from the outside in. The last
class here pins both sides of that — a close propagating all the way down, and what a
bare `break` actually costs — since the obligation can only be documented, never
enforced from inside.

And the fix cannot be "write it in a `finally`" alone, because an async generator's
`finally` runs at CLOSE, not when the consumer walks away — which can be after a
newer turn has started on the same facilitator. Hence the epoch guard, and hence
`TestAStaleTurnCannotOverwriteALiveOne`, which is the one that would fail if the
guard were dropped as belt-and-braces.

WHAT THE MOCK MODELS, AND WHY IT HAS THREE LAYERS
=================================================
A one-layer fake stream would make the connection test unfailable, because the bug
IS the layering: `chunk_stream()` iterates the response's `_chunk_iterator`, which
iterates the provider's `decode_async_stream`, and only that last one holds the
response inside an `async with`. Closing the outermost releases none of it — and
`_chunk_iterator` is an ATTRIBUTE of the response object, which outlives the round,
so nothing downstream even becomes collectable. So `_Stream` below is built in the
same three layers, with the "connection" at the bottom where the real one is.

One thing these tests do NOT cover: an abandoned round is never recorded to the call
census, because `_record_stream_round` sits after the chunk loop. So
`last_submit_seconds > 0` with no matching `CallRecord` is a reachable and correct
state, and a reader comparing the two should expect it.
"""

from __future__ import annotations

import asyncio
from contextlib import aclosing
from typing import Any, AsyncGenerator, Optional

import pytest
from mirascope.llm import TextChunk
from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import (ResponseComplete,
                                                       TextDelta)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override autouse fixture — these tests never touch the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override autouse fixture — these tests never touch the DB."""
    yield


#: Long enough to be unambiguous against a clock, short enough that the suite does
#: not notice. Every assertion below is a comparison against this, never against
#: zero: `> 0` would pass on a figure taken at the wrong moment, and the bug being
#: pinned is a figure taken at the wrong moment.
_PROVIDER_DELAY = 0.06


class _Reply(BaseModel):
    message: str = Field(description="Response message")


class _Usage:
    def __init__(self) -> None:
        self.input_tokens = 1_000
        self.output_tokens = 20
        self.cache_read_tokens = 0
        self.cache_write_tokens = 0


class _Connection:
    """Stands in for the SSE response an `async with` holds open.

    Held by the TEST, never by the stream, so that asserting on it says something
    about the provider's resources rather than about the mock's bookkeeping.
    """

    def __init__(self) -> None:
        self.released = False


async def _decoder(
    connection: _Connection,
    *,
    chunks: list,
    delay: float,
    chunk_delay: float,
    error: Optional[Exception],
    fail_after: int,
) -> AsyncGenerator[Any, None]:
    """The bottom layer: `anthropic/_utils/decode.py::decode_async_stream`.

    Its `try`/`finally` is the `async with anthropic_stream_manager` of the real
    one — the only place in the chain where letting go actually means anything, and
    the reason a close has to reach this far down.

    The cleanup AWAITS before it releases, and that is not decoration. The real one
    unwinds an `async with`, so its `__aexit__` is a coroutine: cleanup here can
    suspend. Putting the await first means an interrupted cleanup leaves `released`
    False, so any test asserting on it is also asserting that a close which yields
    to the loop still completes — including one running inside an already-cancelled
    task, which is the shape `submit_stream`'s `finally` is in.
    """
    try:
        # Before the first chunk, where a real stream's think time is: no HTTP
        # request is issued until this generator's first `__anext__`.
        if delay:
            await asyncio.sleep(delay)
        for index, chunk in enumerate(chunks):
            if error is not None and index == fail_after:
                raise error
            yield chunk
            # AFTER the yield, so it is time spent mid-stream rather than
            # pre-first-chunk. The distinction decides which `try` a failure or a
            # cancellation lands in: the round's open (`_start_stream_round`, which
            # pulls the first chunk) or the chunk loop (`_release_round`'s).
            if chunk_delay:
                await asyncio.sleep(chunk_delay)
        if error is not None and fail_after >= len(chunks):
            raise error
    finally:
        await asyncio.sleep(0)
        connection.released = True


async def _relay(iterator: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
    """The middle layer: mirascope's `_wrap_async_iterator_errors`.

    Deliberately holding nothing, like the real one — which is not quite "no
    cleanup": it wraps the relay in a synchronous `with self._wrap_errors()` that
    does run on unwind, but catches `Exception` only, so `GeneratorExit` passes
    straight through. Either way there is nothing here to release. What this layer
    contributes is its FRAME, which is the only thing holding the decoder, so closing
    it is what makes the decoder collectable — insufficient alone, sufficient in
    combination.
    """
    async for chunk in iterator:
        yield chunk


class _Stream:
    """A round that can be slow, can fail, and reports how it was disposed of.

    The top layer, `AsyncStreamResponse.chunk_stream()`. `_chunk_iterator` is an
    instance attribute for the same reason mirascope makes it one, and that detail
    is the defect: the response object outlives the round, so anything reachable
    through it is not collectable when the round is abandoned.

    `exhausted` is what keeps the release assertions honest — the decoder's
    `finally` also runs when it simply runs out, so "released" only means something
    alongside "and it had not finished".
    """

    def __init__(
        self,
        connection: Optional[_Connection] = None,
        *,
        chunks: Optional[list] = None,
        delay: float = 0.0,
        chunk_delay: float = 0.0,
        error: Optional[Exception] = None,
        fail_after: int = 0,
    ) -> None:
        self.tool_calls: list = []
        self.usage = None
        self.messages = [{"role": "assistant", "content": "x"}]
        self.exhausted = False
        self._chunk_iterator = _relay(
            _decoder(
                connection or _Connection(),
                chunks=chunks or [],
                delay=delay,
                chunk_delay=chunk_delay,
                error=error,
                fail_after=fail_after,
            )
        )

    async def chunk_stream(self):
        async for chunk in self._chunk_iterator:
            yield chunk
        self.usage = _Usage()
        self.exhausted = True

    async def execute_tools(self):  # pragma: no cover - no tool rounds here
        return []


def _facilitator(*streams: _Stream, reply: str = "done") -> ConversationFacilitator:
    facilitator = ConversationFacilitator(tools=[lambda: None])
    remaining = list(streams)

    async def _open_tools_stream():
        assert remaining, "opened more streams than the test provided"
        return remaining.pop(0)

    async def _call_with_response_model(_model):
        return _Reply(message=reply)

    facilitator._open_tools_stream = _open_tools_stream  # type: ignore[method-assign]
    facilitator._call_with_response_model = _call_with_response_model  # type: ignore[method-assign]
    return facilitator


@pytest.mark.llm
@pytest.mark.asyncio
class TestATurnThatCrashedStillReportsItsWait:
    async def test_a_failure_past_the_first_chunk_reports_the_seconds_it_cost(self):
        """The unretryable failure — the host already has text on screen, so the
        turn is lost — and the one the field used to report as 0.0."""
        facilitator = _facilitator(
            _Stream(
                chunks=[TextChunk(delta="half an answer")],
                delay=_PROVIDER_DELAY,
                error=RuntimeError("redacted_thinking"),
                fail_after=1,
            )
        )
        with pytest.raises(RuntimeError):
            async for _ in facilitator.submit_stream(_Reply, "hello"):
                pass

        assert facilitator.last_submit_seconds >= _PROVIDER_DELAY

    async def test_the_tool_free_path_reports_its_seconds_too(self):
        """No stream on this path, so it fails in a different place — and the
        clock lives in the caller precisely so both places are covered by one
        `finally` rather than by an assignment per exit."""
        facilitator = ConversationFacilitator(tools=[])

        async def _call_with_response_model(_model):
            await asyncio.sleep(_PROVIDER_DELAY)
            raise RuntimeError("no")

        facilitator._call_with_response_model = _call_with_response_model  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            async for _ in facilitator.submit_stream(_Reply, "hello"):
                pass

        assert facilitator.last_submit_seconds >= _PROVIDER_DELAY


@pytest.mark.llm
@pytest.mark.asyncio
class TestATurnTheConsumerWalkedAwayFrom:
    async def test_an_abandoned_turn_reports_the_seconds_it_cost(self):
        """The person who gave up still spent the model's tokens and their own
        patience. `0.0` here would hide the turns worth knowing about."""
        stream = _Stream(
            chunks=[TextChunk(delta="a"), TextChunk(delta="b"), TextChunk(delta="c")],
            delay=_PROVIDER_DELAY,
        )
        facilitator = _facilitator(stream)

        rounds = facilitator.submit_stream(_Reply, "hello")
        async for event in rounds:
            if isinstance(event, TextDelta):
                break
        # What a host does on disconnect, whether by `aclosing` or by dropping the
        # reference and letting the loop finalise it. Explicit here because the
        # collector's timing is not something a test should depend on.
        await rounds.aclose()

        assert not stream.exhausted, "the test would be vacuous if it had finished"
        assert facilitator.last_submit_seconds >= _PROVIDER_DELAY

    async def test_the_connection_is_let_go_of_and_not_left_to_the_collector(self):
        """The connection, not the number.

        Three layers down (see this module's docstring) sits the `async with` that
        owns the HTTP response, and closing only the outermost generator releases
        none of it — that is the whole reason `_release_round` closes two. The last
        hop is genuinely the interpreter's: closing the response's `_chunk_iterator`
        makes the decoder unreachable, and the loop's async-generator finaliser hook
        runs its `finally` a turn or two later. Hence the sleep, which is not
        padding: without the second close there is nothing for the collector to find
        in the first place, because `_chunk_iterator` hangs off the response object
        and the response outlives the round.
        """
        connection = _Connection()
        stream = _Stream(
            connection, chunks=[TextChunk(delta="a"), TextChunk(delta="b")]
        )
        facilitator = _facilitator(stream)

        async with aclosing(facilitator.submit_stream(_Reply, "hello")) as rounds:
            async for event in rounds:
                if isinstance(event, TextDelta):
                    break

        assert not stream.exhausted, "the test would be vacuous if it had finished"
        await asyncio.sleep(_PROVIDER_DELAY)  # the finaliser hook's turn
        assert connection.released

    async def test_a_turn_cancelled_before_its_first_chunk_reports_its_seconds(self):
        """Cancellation is the third exit, and the one a web host actually uses.

        This one lands in the round's OPEN — `_start_stream_round` pulls the first
        chunk, so a delay before that chunk is time spent outside the chunk loop
        entirely. Which makes it the case that reaches `submit_stream`'s `finally`
        without `_release_round` ever having run; the sibling test below is the
        other half.
        """
        facilitator = _facilitator(
            _Stream(chunks=[TextChunk(delta="a")], delay=_PROVIDER_DELAY * 4)
        )

        async def _turn():
            async with aclosing(facilitator.submit_stream(_Reply, "hello")) as rounds:
                async for _ in rounds:
                    pass

        task = asyncio.create_task(_turn())
        # Twice the figure asserted below, because the turn's clock starts a hair
        # AFTER this sleep does — the task does not run until we suspend.
        await asyncio.sleep(_PROVIDER_DELAY * 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert facilitator.last_submit_seconds >= _PROVIDER_DELAY

    async def test_a_turn_cancelled_mid_stream_still_reports_and_still_releases(self):
        """Cancelled with chunks already delivered, which is where the cleanup runs.

        The one exit that reaches BOTH cleanups while the task is already cancelled:
        `_release_round` inside the chunk loop's `finally`, then `submit_stream`'s
        write and `rounds.aclose()`. Every `await` on that path — including the
        decoder's own awaiting cleanup — runs on borrowed time, and this test says the
        figure and the connection both survive it anyway.

        A first chunk therefore has to be DELIVERED here: `chunk_delay` sits after
        the yield, so the cancellation lands inside the chunk loop rather than in the
        round's open, which is the sibling test above.

        What it does NOT pin is the ORDER of the write and the close in that
        `finally`. The write goes first because `aclose()` can itself be cancelled and
        the figure is the part that cannot be recovered afterwards — but only a second
        cancellation delivered during the close would tell the two orders apart, so
        treat that ordering as deliberate defence rather than as tested behaviour.
        """
        connection = _Connection()
        facilitator = _facilitator(
            _Stream(
                connection,
                chunks=[TextChunk(delta="a"), TextChunk(delta="b")],
                chunk_delay=_PROVIDER_DELAY * 4,
            )
        )

        saw_delta = asyncio.Event()

        async def _turn():
            async with aclosing(facilitator.submit_stream(_Reply, "hello")) as rounds:
                async for event in rounds:
                    if isinstance(event, TextDelta):
                        saw_delta.set()

        task = asyncio.create_task(_turn())
        await saw_delta.wait()
        # Only now is the turn inside the chunk loop, waiting on the next chunk.
        await asyncio.sleep(_PROVIDER_DELAY)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert facilitator.last_submit_seconds >= _PROVIDER_DELAY
        await asyncio.sleep(_PROVIDER_DELAY)  # the finaliser hook's turn
        # A weaker claim than it looks, and worth saying so: cancellation destroys
        # `_stream_turn`'s frame on the way out, which makes the decoder unreachable
        # whether or not `_release_round` ran — verified, this line still passes with
        # the release mutated out. It is here to say a cancelled turn does not LEAK,
        # not to pin the mechanism; the deterministic pin for that is
        # `test_the_connection_is_let_go_of_and_not_left_to_the_collector`.
        assert connection.released, "a cancelled turn still owes the connection"


@pytest.mark.llm
@pytest.mark.asyncio
class TestTheFigureIsTheProvidersAndNotTheHosts:
    async def test_the_happy_path_is_not_inflated_by_a_slow_consumer(self):
        """`last_submit_seconds` is stamped the moment the reply EXISTS, and the
        `finally` must not overwrite it with a later reading — otherwise every
        ordinary turn absorbs however long the host took to come back for the last
        event, which on a UI is unbounded.

        This one guards the NEW machinery rather than the old defect: the pre-fix
        code also assigned before the final yield, so it would have passed. It is
        the `recorded` flag it pins — drop that and the `finally` overwrites a good
        figure with the consumer's.
        """
        facilitator = _facilitator(_Stream(chunks=[TextChunk(delta="hi")]))

        saw_complete = False
        async for event in facilitator.submit_stream(_Reply, "hello"):
            if isinstance(event, ResponseComplete):
                saw_complete = True
                # The host rendering, or the person reading, or the socket flushing.
                await asyncio.sleep(_PROVIDER_DELAY * 2)

        assert saw_complete
        assert facilitator.last_submit_seconds < _PROVIDER_DELAY


@pytest.mark.llm
@pytest.mark.asyncio
class TestAStaleTurnCannotOverwriteALiveOne:
    async def test_a_late_finalisation_leaves_the_newer_turns_figure_alone(self):
        """The reason the `finally` is guarded by an epoch rather than trusted.

        An abandoned generator's `finally` runs when it is CLOSED, and that can be
        long after the next turn has started — a reconnecting host is the ordinary
        case. Unguarded, the stale turn would then stamp its own elapsed time,
        measured from ITS start and therefore arbitrarily large, onto a healthy turn
        that has already reported correctly. A gap is a gap; this would be a lie
        about a turn that went fine, which is the same class of bug as the unreset
        `last_tool_results` that once attributed a crash to a healthy turn.
        """
        connection = _Connection()
        abandoned = _Stream(
            connection,
            chunks=[TextChunk(delta="a"), TextChunk(delta="b")],
            delay=_PROVIDER_DELAY,
        )
        facilitator = _facilitator(abandoned, _Stream(chunks=[TextChunk(delta="hi")]))

        # Held in a name so the collector cannot finalise it early: the point is a
        # close that happens AFTER the next turn.
        stale = facilitator.submit_stream(_Reply, "hello")
        async for event in stale:
            if isinstance(event, TextDelta):
                break

        # A whole second turn, start to finish, on the same facilitator.
        async for _ in facilitator.submit_stream(_Reply, "again"):
            pass
        healthy_seconds = facilitator.last_submit_seconds
        assert healthy_seconds < _PROVIDER_DELAY, "the fresh turn was the fast one"

        await stale.aclose()

        assert facilitator.last_submit_seconds == healthy_seconds
        # Skipping the write is the only thing the guard skips: the stale turn is
        # still finalised, and its connection still let go of.
        await asyncio.sleep(_PROVIDER_DELAY)
        assert connection.released


class _StubAdvisor:
    """`Advisor.chat_stream` over a REAL facilitator, at the host boundary.

    Same idiom and same reason as `_StubAdvisor` in `test_turn_timing.py`:
    `Advisor.__init__` wants a DB and a live container, while `chat_stream` itself
    needs only a conversation, a scope and the two seams around it. Binding the real
    method is the point — what is under test is one line INSIDE it (the `aclosing`),
    so a stand-in that re-implemented the body would be testing its own copy of it.
    """

    AGENT_NAME = Advisor.AGENT_NAME

    def __init__(self, facilitator: ConversationFacilitator) -> None:
        self.last_turn_timing = None
        self._conversation = facilitator

    async def _refresh_context(self) -> float:
        return 0.0

    async def _repair_unrecorded_decision(self, _user, _assistant) -> None:
        return None

    chat_stream = Advisor.chat_stream
    _record_turn_timing = Advisor._record_turn_timing


@pytest.mark.llm
@pytest.mark.asyncio
class TestTheChainOnlyRunsWhenTheHostClosesTheOutermostGenerator:
    """The half of this fix that is NOT the framework's to guarantee.

    `chat_stream` is itself an async generator wrapping `submit_stream`, so the
    cleanup chain unwinds from the OUTSIDE in: nothing below can run until
    `chat_stream` is closed, and only its consumer can close it. The `aclosing`
    inside `chat_stream` makes the link from there downward real; the link above it
    is a documented obligation on the host (`Advisor.chat_stream`'s docstring,
    `docs/agents.md`, the README example) and cannot be anything else — an
    unreachable frame suspended at a `yield` is unreachable in both directions.

    So these two tests are a pair, and the second is as important as the first: it
    records what a bare `break` actually costs, so nobody has to rediscover it by
    watching connections pile up.
    """

    async def test_closing_the_agents_generator_reaches_the_connection(self):
        """The inner generator is pinned in a name, and that is what makes this a
        test rather than a coin toss.

        Left to itself, `chat_stream`'s frame dies with the close and the inner
        `submit_stream` becomes unreachable, so the collector finalises it within a
        few milliseconds whether or not anything closed it deliberately — verified:
        with the `aclosing` mutated out, this test passed. Holding a reference is
        what a real host does anyway (its event source outlives one turn), and it
        removes the collector from the question entirely: after this, the ONLY thing
        that can release the connection is `chat_stream` closing it on purpose.
        """
        connection = _Connection()
        stream = _Stream(
            connection, chunks=[TextChunk(delta="a"), TextChunk(delta="b")]
        )
        facilitator = _facilitator(stream)
        pinned: list = []
        inner = facilitator.submit_stream

        def _pinning_submit_stream(*args, **kwargs):
            rounds = inner(*args, **kwargs)
            pinned.append(rounds)
            return rounds

        facilitator.submit_stream = _pinning_submit_stream  # type: ignore[method-assign]
        advisor = _StubAdvisor(facilitator)

        with scope("sid-test"):
            async with aclosing(advisor.chat_stream("hello")) as events:
                async for event in events:
                    if isinstance(event, TextDelta):
                        break

        assert pinned, "the spy never fired, so nothing below was exercised"
        assert not stream.exhausted, "the test would be vacuous if it had finished"
        await asyncio.sleep(_PROVIDER_DELAY)  # the finaliser hook's turn
        assert connection.released
        # The seconds too: same close, same `finally`, and unlike the connection
        # this one cannot be reached by the collector afterwards — a newer turn may
        # own the slot by then.
        assert facilitator.last_submit_seconds > 0.0

    async def test_a_bare_break_defers_everything_to_the_collector(self):
        """Not an endorsement — a record of the cost, and of where it lands.

        Held in a name so nothing is finalised early, which is exactly what a host
        holding a reference to its own event source does. Note what is NOT wrong
        here: `last_turn_timing` stays `None` rather than going stale, because the
        recording is below the abandoned `yield` and never runs at all. A gap, not a
        lie — the failure mode is the held connection and the unrecorded seconds.
        """
        connection = _Connection()
        stream = _Stream(
            connection, chunks=[TextChunk(delta="a"), TextChunk(delta="b")]
        )
        facilitator = _facilitator(stream)
        advisor = _StubAdvisor(facilitator)

        with scope("sid-test"):
            events = advisor.chat_stream("hello")
            async for event in events:
                if isinstance(event, TextDelta):
                    break

            await asyncio.sleep(_PROVIDER_DELAY)
            assert not connection.released, (
                "if this ever passes, async generators finalise on `break` and the"
                " host contract can be dropped from the docs"
            )
            assert facilitator.last_submit_seconds == 0.0
            assert advisor.last_turn_timing is None

            # And the close is all it was ever waiting for.
            await events.aclose()

        assert facilitator.last_submit_seconds > 0.0
        await asyncio.sleep(_PROVIDER_DELAY)
        assert connection.released
