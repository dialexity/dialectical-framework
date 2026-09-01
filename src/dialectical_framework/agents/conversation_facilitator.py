"""
ConversationFacilitator: Helper for managing LLM conversation with tool calling.

Facilitator that:
- Maintains conversation message history
- Supports tool calling with automatic execution loop
- Provides easy LLM calls with structured responses
- Can be composed into tools, services, or agents
"""

from __future__ import annotations

import json
import logging
import time
from typing import (TYPE_CHECKING, Any, AsyncGenerator, Awaitable, Callable,
                    NamedTuple, Optional, Sequence, TypeVar)

from langfuse import observe
from mirascope import llm

from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.stream_events import (
    ResponseComplete,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolResult,
    ToolStart,
)
from dialectical_framework.agents.turn_timing import ToolRound
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.call_census import record_call
from dialectical_framework.utils.retry_accounting import (RetryAccount,
                                                          retry_account)
from dialectical_framework.utils.use_brain import (prefill_token_kwargs,
                                                  retry_transient, use_brain)

from mirascope.llm import TextChunk, ThoughtChunk, ToolOutput

if TYPE_CHECKING:
    from mirascope.llm import UserContent
    from mirascope.llm.calls import AsyncCall
    from mirascope.llm.responses import AsyncResponse

T = TypeVar("T")

#: Injected in the user role before the structured-extraction call (see
#: `_call_with_response_model`) because Bedrock requires a conversation to end
#: with a user message. It is machinery, so it says so: the model must not read
#: it as something the person said, must not answer it, and must not mention it.
_EXTRACTION_REQUEST = (
    "[FRAMEWORK NOTICE — machinery, not a message from the person you are"
    " talking to. The person did not write this and cannot see it.]\n"
    "Your reply to them is finished. This is the framework's own extraction step:"
    " restate that same reply in the required structured format so the host"
    " application can render it. Add nothing new, ask nothing, draw no conclusion"
    " about why this was requested, and never refer to this notice or to"
    " \"structured responses\" in anything the person reads."
)


def _tool_output_text(output: Any) -> str:
    """The tool's own return value as text, not the envelope's repr.

    `execute_tools()` returns Mirascope `ToolOutput` wrappers, whose `str()` is
    the dataclass repr (`ToolOutput(type='tool_output', id=..., result='{...}')`).
    Using that directly is a silent bug: it is a perfectly good string, so
    nothing raises — but `ExecutionReport.model_validate_json` can never parse
    it, so every `ToolResult` event carried `report=None` and consumers saw no
    graph effects at all. Present since streaming was introduced.

    Falls back to `str()` for plain values, since tools may return bare strings.
    """
    result = getattr(output, "result", output)
    return result if isinstance(result, str) else str(result)


class _RoundStart(NamedTuple):
    """A streaming round that has already proven it can answer.

    The first chunk is pulled as part of STARTING the round, not as part of
    consuming it, because that is where a streamed round actually fails: no HTTP
    request is issued by `await call.stream()`, so a throttle or a 503 arrives on
    the first `__anext__`. Pulling it here is what makes the failure retryable —
    and the chunk has to be carried out again so the caller can put it back at the
    front of the loop (`_replay_first_chunk`), since it must still reach the host.
    """

    stream: Any
    #: An async GENERATOR, not merely an iterator, because an abandoned turn has to
    #: close it — see `_release_round`, which also explains why closing this one
    #: alone is not enough.
    chunks: AsyncGenerator
    #: `None` only if the provider ended the stream without a single chunk, which
    #: is not the same as a tool-only round: those still emit tool-call chunks.
    first_chunk: Optional[Any]
    #: When the attempt that SUCCEEDED began — not when the round was first
    #: attempted. The difference is the retry ladder, and it must stay out of
    #: `first_token_seconds` or one throttled round would report as a 10-second
    #: prefill and quietly ruin an arm comparison.
    provider_started: float
    first_chunk_at: Optional[float]


async def _replay_first_chunk(start: _RoundStart) -> AsyncGenerator[Any, None]:
    """The round's chunks, with the one already pulled put back at the front."""
    if start.first_chunk is not None:
        yield start.first_chunk
    async for chunk in start.chunks:
        yield chunk


async def _release_round(start: _RoundStart) -> None:
    """Let go of the round's provider connection, as far as it can be reached.

    Only needed when a turn is ABANDONED: an exhausted round is already closed and
    so is one that raised, which makes both calls below no-ops on every ordinary
    exit. What abandonment leaves behind is three suspended generators, and only
    the deepest of them holds the HTTP response:

    1. `start.chunks` — `AsyncStreamResponse.chunk_stream()`, which iterates
    2. `stream._chunk_iterator` — mirascope's `_wrap_async_iterator_errors`
       (`providers/base/base_provider.py:_wrap_async_iterator_errors`, bound onto
       the response), whose body is a SYNCHRONOUS `with self._wrap_errors()` around
       the relay — so it runs on unwind but holds nothing and cannot swallow the
       `GeneratorExit` (that handler catches `Exception`, and `contextlib`
       re-propagates a `BaseException` unchanged). It iterates
    3. the provider decoder's `decode_async_stream`, suspended inside
       `async with anthropic_stream_manager` — THE one whose `__aexit__` closes
       the SSE response.

    Closing an async generator does not close what it was iterating (that is the
    same fact that makes this cleanup necessary at all, one level up), so closing
    (1) alone frees nothing: `_chunk_iterator` is an ATTRIBUTE of the response
    object, and the response outlives the round because the code after the chunk
    loop reads its usage and tool calls from it. (2) would therefore stay suspended
    with (3) inside it until the whole response became garbage — which is exactly
    the behaviour this is meant to replace.

    Closing (2) as well drops (3) to zero references, and the event loop's
    async-generator finaliser hook then runs its `aclose` and with it the
    `__aexit__`. That last hop is the interpreter's rather than ours: mirascope
    exposes no close on a stream response, which is also why reaching through
    `_chunk_iterator` — private, and flagged as such in mirascope's own source — is
    the deliberate choice it looks like.

    So of the two closes, (2) is the load-bearing one; (1) merely drops its own
    frame, since the real `chunk_stream()` has no cleanup of its own. It is kept
    because it is the generator this module actually owns, and because a future
    mirascope that DID clean up there would otherwise be missed silently.

    One thing this leaves behind, for whoever touches the round after it: the
    response object survives with `consumed` still False and `usage` still None,
    over a chunk iterator that is now closed. Anything that re-entered
    `chunk_stream()` would get `StopAsyncIteration` on the first pull and read as a
    complete, empty stream rather than an error. Nothing does today — the round is
    dead by the time this runs, and `resume` is only called on exhausted rounds,
    where both closes are no-ops.
    """
    await start.chunks.aclose()
    inner = getattr(start.stream, "_chunk_iterator", None)
    # Guarded rather than assumed: it is private, and on a sync response it is a
    # plain generator with `close` instead.
    if inner is not None and hasattr(inner, "aclose"):
        await inner.aclose()


class ConversationFacilitator(SettingsAware):
    """
    Helper for managing LLM conversation with optional tool calling.

    Use via composition in tools, services, or agents that need
    multi-step LLM interactions with shared context.

    Example without tools:
        facilitator = ConversationFacilitator()
        facilitator.set_system_prompt("You are...")
        result = await facilitator.submit(MyDto, "Extract...")

    Example with tools:
        facilitator = ConversationFacilitator(tools=[extract_theses, extract_antitheses])
        facilitator.set_system_prompt("You are an agent...")
        result = await facilitator.submit(FinalResultDto, "Find 3 theses about trust")
        # Tools are automatically called and results injected into conversation

    Example with parallel isolated calls:
        tasks = [facilitator.isolate().submit(Dto, msg) for msg in messages]
        results = await asyncio.gather(*tasks)
    """

    def __init__(self, tools: Optional[list[Any]] = None) -> None:
        self._messages: list = []
        self._tools = tools or []
        # Tool names invoked during the most recent submit()/submit_stream()
        # turn. Lets callers (e.g. the Advisor's context-staleness tracking)
        # observe what the model chose to do this turn.
        self.last_tool_calls: list[str] = []
        # Outcomes of those same calls, in call order. Names alone say what the
        # model ATTEMPTED; a tool that ran and reported ok=False is
        # indistinguishable from one that succeeded. That gap cost a 2.6h bench
        # run its diagnosis: the recorded JSON showed eight `anchor` calls and a
        # graph with nothing in it, and nothing in between.
        self.last_tool_results: list[ToolResult] = []
        # The ARGUMENTS of those same calls, parallel to `last_tool_calls`.
        # Names and outcomes together still cannot answer "did the model fill in
        # this optional parameter?" — and for `anchor`'s `context` that question
        # is the difference between a prompt defect (the model omitted the
        # person's particulars) and a framework one (grounding dropped them).
        # Both look identical from outside: `anchor:ok` over a graph with no
        # grounding on it.
        self.last_tool_call_args: list[dict[str, Any]] = []
        # Wall clock per tool ROUND, and the total for the whole submit. Names
        # and outcomes say WHAT ran; these say what it cost the person waiting,
        # which is a different question and the one no field answered. Every
        # figure in `probe_reply_path_latency.py` before this existed was
        # regressed out of 187 runs' cell-level `duration_s` because a turn
        # recorded no duration at all.
        #
        # Per round rather than per call because `execute_tools()` gathers a
        # round and runs it concurrently — see `ToolRound`.
        self.last_tool_rounds: list[ToolRound] = []
        # The whole submit: generation plus every tool round. This is the
        # interval the person actually waits, so it is measured around the
        # outermost await rather than summed from parts that might not cover it.
        self.last_submit_seconds: float = 0.0
        # Of that interval, what was spent retrying: backoff sleep plus the
        # attempts that raised before it, ANYWHERE under this submit — tool
        # rounds and the model's own generation alike. The per-round split lives
        # on `ToolRound.retry_seconds`, so generation retries are this minus
        # their sum. Recorded because r26 quoted `anchor` at a 282.8s median
        # when four of its ten rounds were ~40s of work plus a 750s ParseError
        # ladder, and nothing in the archive could tell the two apart.
        self.last_submit_retries: RetryAccount = RetryAccount()
        # When the person first had something on screen, measured from the moment
        # they hit send. `None` on every non-streaming submit, and on a streamed
        # turn that produced no text or thought at all.
        #
        # NOT "time to first token" as a provider means it, and the name says so
        # deliberately. The Advisor is contracted to call tools without narrating
        # first, so on a tool-electing turn the first delta can arrive AFTER a full
        # tool round and read 140-230s. HOW OFTEN it does is unmeasured: counting
        # text deltas before the first `ToolStart` needs this streaming path, and
        # nothing has done it. (The ~17% once quoted here was the vocabulary-leak
        # rate off the AWAITED path — `probe_leak_reply_reuse.py`, 7 of 40 replies —
        # a different quantity about different turns.) The
        # prefill-sensitive quantity — the one prompt caching can move — is
        # `CallRecord.first_token_seconds` on the turn's first round, not this.
        self.last_submit_first_delta_s: Optional[float] = None
        # Bumped once per submit, and captured by `submit_stream` so its `finally`
        # can tell "this turn is still the current one" from "a turn the consumer
        # walked away from, being finalised now".
        #
        # An async generator's `finally` does not run when the consumer stops
        # iterating — it runs when the generator is CLOSED, which for an abandoned
        # one is whenever the collector gets to it. That can be after the next turn
        # has started, and a `finally` writing `last_submit_seconds` unconditionally
        # would then stamp the abandoned turn's elapsed time (measured from ITS
        # `started`, so arbitrarily large) onto the healthy turn now in flight.
        # Recording nothing is a gap; recording a stale figure on a good turn is a
        # lie, and it is the same class of bug as the unreset `last_tool_results`
        # that once attributed a crash to a healthy turn.
        #
        # What it does NOT do is make overlapping turns safe, and it is worth being
        # exact about that, since the guard looks like it might. Only the `finally`
        # write consults the epoch; the write at `ResponseComplete` does not, and
        # must not — that is the turn reporting its own good figure. So if two
        # submits ever overlapped on one facilitator, whichever finished LAST would
        # own `last_submit_seconds`, epoch or no epoch. The epoch narrows one case
        # only: a turn already abandoned cannot come back later and overwrite a
        # healthy one. ONE turn at a time is still the contract, same as every other
        # `last_*` field here; that is what `isolate()` is for, and no caller shares
        # a facilitator across concurrent turns today.
        self._turn_epoch = 0

    def _begin_turn(self) -> int:
        """Claim the "current turn" slot, returning this turn's epoch."""
        self._turn_epoch += 1
        return self._turn_epoch

    def set_system_prompt(self, system_prompt: str) -> None:
        """
        Set or replace the system prompt for this conversation.

        Replaces any existing system message at position 0, or inserts one.
        """
        system_msg = llm.messages.system(system_prompt)

        if not self._messages:
            self._messages.append(system_msg)
        elif hasattr(self._messages[0], "role") and self._messages[0].role == "system":
            self._messages[0] = system_msg
        elif isinstance(self._messages[0], dict) and self._messages[0].get("role") == "system":
            self._messages[0] = system_msg
        else:
            self._messages.insert(0, system_msg)

    def add_user_message(self, content: str) -> ConversationFacilitator:
        """Add a user message to the conversation. Returns self for chaining."""
        self._messages.append(llm.messages.user(content))
        return self

    def add_assistant_message(self, content: str) -> ConversationFacilitator:
        """Add an assistant message to the conversation. Returns self for chaining."""
        self._messages.append(llm.messages.assistant(content, model_id=None, provider_id=None))
        return self

    def isolate(self) -> ConversationFacilitator:
        """
        Create an isolated copy with current messages snapshot.

        Use for parallel calls to avoid race conditions on self._messages.
        The isolated copy can use submit() normally with full tool support.

        Example:
            # Parallel calls that don't interfere with each other
            tasks = [
                self._conversation.isolate().submit(Dto, f"Process {item}")
                for item in items
            ]
            results = await asyncio.gather(*tasks)
        """
        isolated = ConversationFacilitator(tools=self._tools)
        isolated._messages = [*self._messages]  # Copy messages
        return isolated

    @observe()
    async def submit(
        self,
        response_model: type[T],
        user_content: UserContent,
        max_tool_rounds: int = 10,
    ) -> T:
        """
        Submit a message and get structured response.

        If tools are configured, runs an agentic loop:
        1. Call LLM with tools available
        2. If LLM calls tools, execute them and resume conversation
        3. Repeat until LLM returns final response (no tool calls)
        4. Extract structured response from final message

        Args:
            response_model: Pydantic model for structured output
            user_content: User message to submit
            max_tool_rounds: Maximum tool execution rounds (default 10)

        Returns:
            Structured response matching response_model
        """
        self._messages.append(llm.messages.user(user_content))
        self.last_tool_calls = []
        self.last_tool_results = []
        self.last_tool_call_args = []
        self.last_tool_rounds = []
        self.last_submit_seconds = 0.0
        self.last_submit_retries = RetryAccount()
        # Reset here too although this path can never set it: a facilitator is
        # reused across turns, so without this a non-streaming submit would report
        # the previous STREAMED turn's figure as its own.
        self.last_submit_first_delta_s = None

        # `finally`, not a plain assignment before each return: a turn that
        # RAISED still waited the person's time, and a duration recorded only on
        # the happy path makes the expensive failures the invisible ones.
        started = time.monotonic()
        # Claimed here too, so an abandoned `submit_stream` generator finalised
        # during THIS turn cannot overwrite what this turn records.
        epoch = self._begin_turn()
        try:
            # One account over the whole submit, nested accounts per tool round.
            # Both see every retry (see `retry_accounting._stack`), so the outer
            # total covers generation too — which is where r26's one 644.1s
            # tool-less residual would have shown up.
            with retry_account(self.last_submit_retries):
                if not self._tools:
                    return await self._call_with_response_model(response_model)

                # Agentic loop: resume() accumulates messages internally
                response = await self._call_with_tools()
                for _ in range(max_tool_rounds):
                    if not response.tool_calls:
                        break
                    self.last_tool_calls.extend(tc.name for tc in response.tool_calls)
                    self._record_tool_call_args(response.tool_calls)
                    self._log_tool_calls(response.tool_calls)
                    round_names = tuple(tc.name for tc in response.tool_calls)
                    round_started = time.monotonic()
                    with retry_account() as round_retries:
                        tool_outputs = await response.execute_tools()
                    self.last_tool_rounds.append(
                        ToolRound(
                            names=round_names,
                            seconds=time.monotonic() - round_started,
                            retry_seconds=round_retries.wasted_s,
                            retry_count=round_retries.count,
                        )
                    )
                    self._record_tool_results(response.tool_calls, tool_outputs)
                    self._strip_caller_from_messages(response.messages)
                    response = await response.resume(tool_outputs)

                # Sync full conversation history from the response chain
                self._messages = list(response.messages)
                self._close_dangling_tool_calls(response)
                self._strip_unsupported_input_fields()

                # The answer is usually already written — see `_reuse_written_reply`.
                reused = self._reuse_written_reply(response, response_model)
                if reused is not None:
                    return reused

                # Extract structured response
                return await self._call_with_response_model(response_model)
        finally:
            if epoch == self._turn_epoch:
                self.last_submit_seconds = time.monotonic() - started

    @observe()
    async def submit_stream(
        self,
        response_model: type[T],
        user_content: UserContent,
        max_tool_rounds: int = 10,
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Submit a message and yield stream events as they arrive.

        Yields:
            TextDelta: token-by-token text from intermediate LLM rounds
            ToolStart: when LLM invokes a tool
            ToolResult: after tool execution (with optional ExecutionReport)
            ResponseComplete: final structured message

        Owns the turn's WALL CLOCK and nothing else; `_stream_turn` owns the
        rounds. Split that way because the two guarantees this method makes are
        about exits the round loop does not control — a consumer that walks away
        mid-stream, and a round that raises where nothing can retry:

        - `last_submit_seconds` is recorded on EVERY exit. It used to be assigned
          only after the tool loop, so an abandoned or crashed stream reported 0.0
          for a turn that took eight seconds. A wrong number is worse than a
          missing one: 0.0 reads as "instant" and drags down any mean it enters,
          and the turns it hides are the expensive ones. (The live trigger is not
          hypothetical — mirascope raises `NotImplementedError` from inside the
          chunk loop on a `redacted_thinking` block, so any turn with
          `DIALEXITY_THINKING_LEVEL` set can take this path.)
        - The generator chain is CLOSED rather than left to the collector, which is
          what lets go of the provider's connection. An abandoned turn is suspended
          inside mirascope's decoder, holding the HTTP response open in an
          `async with`; unwinding an `async for` does not close what it iterates, so
          nothing runs those exits unless something closes the chain. See
          `_release_round` for how far down that reaches.

        Both guarantees need the CALLER to close this generator rather than merely
        stop iterating — `contextlib.aclosing`, which every `chat_stream` in the
        tree uses. Left to the collector, the `finally` runs at some later moment
        the epoch guard may well decline to write from.
        """
        started = time.monotonic()
        epoch = self._begin_turn()
        #: Set the moment the reply EXISTS. The `finally` must not overwrite that
        #: with a later reading, or every ordinary turn would silently absorb
        #: however long the consumer took to come back for the last event.
        recorded = False
        # Held in a name so it can be closed; see the docstring.
        rounds = self._stream_turn(
            response_model,
            user_content,
            started=started,
            max_tool_rounds=max_tool_rounds,
        )
        try:
            async for event in rounds:
                if isinstance(event, ResponseComplete):
                    self.last_submit_seconds = time.monotonic() - started
                    recorded = True
                yield event
        finally:
            # Before the close, which can raise: the figure is the point.
            if not recorded and epoch == self._turn_epoch:
                self.last_submit_seconds = time.monotonic() - started
            await rounds.aclose()

    async def _stream_turn(
        self,
        response_model: type[T],
        user_content: UserContent,
        *,
        started: float,
        max_tool_rounds: int,
    ) -> AsyncGenerator[StreamEvent, None]:
        """The rounds themselves. See `submit_stream`, which owns the clock.

        `started` is passed in rather than taken here so that the turn has ONE
        clock: `last_submit_first_delta_s` below and `last_submit_seconds` in the
        caller are both offsets from the same instant, and a second
        `time.monotonic()` could only disagree with the first.
        """
        self._messages.append(llm.messages.user(user_content))
        self.last_tool_calls = []
        # Reset the results too, exactly as `submit` does. Without this a turn
        # inherits the previous turn's outcomes, so a crash gets attributed to a
        # healthy turn and the healthy turn's own tools look unreported.
        self.last_tool_results = []
        self.last_tool_call_args = []
        self.last_tool_rounds = []
        # Reset only; the final value is the caller's to write, on every exit.
        self.last_submit_seconds = 0.0
        self.last_submit_retries = RetryAccount()
        self.last_submit_first_delta_s = None

        # Re-entered per await instead of wrapped around the whole generator, and
        # `retry_account` explains why: a contextvar set across a `yield` installs
        # itself in the consumer's context and never resets if the consumer stops
        # iterating. The uncovered gap is the chunk loop below, PAST its first
        # chunk — which is exactly the part that cannot be retried anyway, since
        # re-asking would duplicate text the host has already shown.
        turn = self.last_submit_retries

        if not self._tools:
            # No stream at all on this path: one formatted call, so there is
            # nothing to yield until it returns. `streamed=False` says so.
            with retry_account(turn):
                result = await self._call_with_response_model(response_model)
            yield ResponseComplete(result=result)
            return

        # Set immediately before each open/resume and read after that round's chunk
        # loop, so one census record covers one provider round-trip. It has to
        # start HERE rather than at the top of the loop: request construction —
        # `_get_tools_call`, `encode_request`, the cache-breakpoint scan over a
        # ~60k-char prompt — happens between the two, and it is the framework's own
        # cost on the person's critical path.
        call_started = time.monotonic()
        with retry_account(turn):
            start = await self._start_stream_round(
                self._open_tools_stream, what="Stream open"
            )
        stream = start.stream

        # The text yielded THIS round, verbatim, and the reply is built from
        # exactly these bytes (below). Same principle as `_record_tool_results`:
        # what the person sees and what the caller receives are one construction,
        # so they cannot disagree. Reading `stream.text()` instead would be a
        # second construction — it joins multiple text parts with a separator the
        # deltas never carried, and a host comparing the two would find them
        # unequal for reasons no test would explain.
        #
        # Reset per round on purpose: text before a tool call is the model saying
        # what it is about to do, and the reply is what it says afterwards.
        answer: list[str] = []
        # One iteration per provider round, and the budget counts the TOOL rounds
        # BETWEEN them: `max_tool_rounds=3` means three rounds of tools plus the
        # fourth generation that reads the last round's outputs. That is the same
        # arithmetic `submit` does above (one call, then up to `max_tool_rounds`
        # resumes), and the `+ 1` is what makes it so here, because this loop
        # consumes at the TOP of the iteration rather than the bottom.
        #
        # Spelled out because the shape it replaces was quietly corrupting every
        # overrun turn, and it read as harmless. This loop used to end with an
        # unconsumed round dangling: `resume()` issues no HTTP, so it looked free.
        # It was not. Everything below the loop then ran against that UNCONSUMED
        # stream, and an unconsumed mirascope stream reports no tool calls, no text
        # and empty content — so three things went wrong at once, none of them
        # visible as an error:
        #
        # - `_reuse_written_reply` saw no pending tool calls, so its budget-overrun
        #   guard could not fire, and it returned the PREVIOUS round's mid-work
        #   narration as the final reply, with `streamed=True`.
        # - `_close_dangling_tool_calls` saw no tool calls either, so it returned
        #   immediately. It has never once fired on this path.
        # - `self._messages` ended on an assistant message whose `content` is a
        #   live alias of the stream's own empty content list, i.e. an empty
        #   assistant message — which the next turn's request 400s on.
        #
        # Since the retry fix that dangling round also PAYS for itself, because
        # opening a round now pulls its first chunk. Consuming N+1 rounds and
        # refusing to spend tools on the last one fixes all four together.
        for round_index in range(max_tool_rounds + 1):
            answer = []
            #: When the provider's first content chunk arrived, and when the first
            #: thing a HOST could render did. Two different questions and they
            #: diverge on the common case, not the rare one — the Advisor is
            #: contracted to call tools without narrating first, so a round can yield
            #: nothing at all here. How often it does is UNMEASURED — this is the
            #: path that would have to count it, and it does not.
            #: Seeded from the round's start rather than measured here: the first
            #: chunk was pulled there, as the retryable half of opening the round.
            first_chunk_at: Optional[float] = start.first_chunk_at
            first_delta_at: Optional[float] = None
            #: Time this round spent suspended in a `yield`, i.e. the CONSUMER's
            #: time, subtracted before recording. The yields below are inside the
            #: chunk loop, so without this a host that renders slowly would be
            #: recorded as a provider that responds slowly, and `parallelism` would
            #: blame the model for the terminal.
            yielded_s = 0.0
            try:
                async for chunk in _replay_first_chunk(start):
                    if first_chunk_at is None:
                        first_chunk_at = time.monotonic()
                    if isinstance(chunk, (ThoughtChunk, TextChunk)):
                        if first_delta_at is None:
                            first_delta_at = time.monotonic()
                        event = (
                            ThinkingDelta(text=chunk.delta)
                            if isinstance(chunk, ThoughtChunk)
                            else TextDelta(text=chunk.delta)
                        )
                        if isinstance(chunk, TextChunk):
                            answer.append(chunk.delta)
                        handed_off = time.monotonic()
                        yield event
                        yielded_s += time.monotonic() - handed_off
            finally:
                # The provider's generators, closed explicitly. Exhausting them
                # makes this a no-op; the case it exists for is the consumer walking
                # away mid-round, where GeneratorExit arrives at the `yield` above
                # and unwinds this `async for` WITHOUT closing what it iterates —
                # leaving mirascope's decoder suspended inside an `async with`,
                # holding the HTTP response. `_release_round` explains why that
                # takes two closes rather than one, and which last hop is still the
                # interpreter's. Called from here and not from inside
                # `_replay_first_chunk`, which has the same problem one level down
                # and is likewise never closed — it holds only a frame.
                await _release_round(start)

            # BEFORE the `break`: the last round is usually the only round, and a
            # record written after it would miss every turn that called no tools.
            self._record_stream_round(
                stream,
                call_started=call_started,
                provider_started=start.provider_started,
                first_chunk_at=first_chunk_at,
                yielded_s=yielded_s,
            )
            if self.last_submit_first_delta_s is None and first_delta_at is not None:
                # From the TURN's start, not this round's: the person has been
                # waiting since they hit send, through the context re-render's
                # caller, every earlier tool round, and any retry ladder. That is
                # the number a UX decision needs, and it is why this is NOT the
                # same quantity as the census record's `first_token_seconds`.
                self.last_submit_first_delta_s = first_delta_at - started

            if not stream.tool_calls:
                break

            if round_index == max_tool_rounds:
                # The budget is spent, so these calls have nowhere to go: sending
                # their outputs means opening a round, and nothing below would read
                # it. Executing them anyway would spend minutes of concern work to
                # throw the results away, and — since the ladder now wraps a real
                # request — a throttle on that round would raise out of
                # `submit_stream` AFTER the answer had already been streamed.
                #
                # Falling through instead leaves the calls unanswered, which is
                # precisely what `_close_dangling_tool_calls` is for: it answers
                # them with `_BUDGET_STOP_NOTICE` so history stays valid and the
                # model is told why it was cut off. Same exit as `submit`.
                #
                # Two things this exit costs, both accepted:
                #
                # - One extra provider call. `_reuse_written_reply` now correctly
                #   declines (tool calls ARE pending), so the structured extraction
                #   runs. That is the price of a correct reply and valid history.
                # - This round's text has already been yielded as `TextDelta`s and
                #   is NOT part of `message`, while `ResponseComplete.streamed` is
                #   False — so a host honouring the documented contract renders
                #   both. Unavoidable without buffering the whole round, since
                #   nothing reveals the overrun until after the text has streamed.
                #
                # And the requested calls are reported ONLY by the warning inside
                # `_close_dangling_tool_calls` — no `ToolStart`, nothing in
                # `last_tool_calls`. That matches `submit`, which is the reason it
                # is left alone rather than the reason it is right.
                break

            for tc in stream.tool_calls:
                yield ToolStart(
                    tool_name=tc.name,
                    tool_args=json.loads(tc.args) if tc.args else {},
                )

            self.last_tool_calls.extend(tc.name for tc in stream.tool_calls)
            self._record_tool_call_args(stream.tool_calls)
            self._log_tool_calls(stream.tool_calls)
            round_names = tuple(tc.name for tc in stream.tool_calls)
            round_started = time.monotonic()
            with retry_account(turn), retry_account() as round_retries:
                tool_outputs = await stream.execute_tools()
            self.last_tool_rounds.append(
                ToolRound(
                    names=round_names,
                    seconds=time.monotonic() - round_started,
                    retry_seconds=round_retries.wasted_s,
                    retry_count=round_retries.count,
                )
            )

            # Recorded and streamed from one construction: the events a UI sees
            # and the outcomes a caller inspects must not be able to disagree.
            for result in self._record_tool_results(stream.tool_calls, tool_outputs):
                yield result

            self._strip_caller_from_messages(stream.messages)
            resuming = stream
            with retry_account(turn):
                call_started = time.monotonic()
                start = await self._start_stream_round(
                    lambda: resuming.resume(tool_outputs), what="Stream resume"
                )
            stream = start.stream

        self._messages = list(stream.messages)
        self._close_dangling_tool_calls(stream)
        self._strip_unsupported_input_fields()
        # Same shortcut as `submit`, and it matters more here: the text this
        # skips re-generating is the text already delivered as `TextDelta`s. So
        # it is built from those deltas, and `streamed` tells the host that the
        # reply is already on their screen — the difference between first-token
        # latency and waiting out the whole turn.
        result = self._reuse_written_reply(
            stream, response_model, text="".join(answer)
        )
        streamed = result is not None
        if result is None:
            with retry_account(turn):
                result = await self._call_with_response_model(response_model)
        # The caller stamps `last_submit_seconds` as this event passes through it,
        # i.e. when the reply EXISTS — not when the consumer next asks for an event.
        yield ResponseComplete(result=result, streamed=streamed)

    # --- Internal helpers ---

    #: Answer written into the synthetic tool_result when the tool loop is cut
    #: short. Addressed to the model, because the model reads it: it must
    #: understand that the tool did not run and that it should wrap up with
    #: what it already has, rather than re-issue the same call forever.
    _BUDGET_STOP_NOTICE = (
        "Tool not executed: this turn's tool-call budget is exhausted. "
        "Do not call more tools — answer now using what you already have, "
        "and say plainly which part is still unverified."
    )

    #: Census `caller` for a streamed round. Deliberately NOT matched to the
    #: awaited path's `_call_with_tools.<locals>._llm_call`: the two are different
    #: code paths with different guarantees — no retry, no concurrency slot, usage
    #: only after consumption — and merging them into one `by_caller()` row would
    #: hide exactly the differences worth seeing.
    _STREAM_ROUND_CALLER = "ConversationFacilitator.submit_stream"

    def _record_stream_round(
        self,
        stream: Any,
        *,
        call_started: float,
        provider_started: float,
        first_chunk_at: Optional[float],
        yielded_s: float,
    ) -> None:
        """Report one drained streaming round to the call census.

        The streaming path reaches none of `use_brain`'s recording, because
        `raw_call=True` returns before it (see the comment there for the full list
        of what that skips). So this is the only place a streamed provider
        round-trip can be counted, and until it existed a whole `chat_stream` turn
        contributed nothing to any census — every token figure the framework
        published came from the non-streaming path alone.

        Called AFTER the chunk loop drains, which is not a preference: Mirascope
        accumulates `stream.usage` from `usage_delta_chunk`s as the iterator runs
        (`base_stream_response.py:722-731` on the async path this drives; `:499-508`
        is its sync twin) and it is `None` before that. Verified that `resume()`
        builds a fresh response with no carried-over usage (`base_provider.py:1253-
        1284` rebuilds the messages and calls `stream_async`), so each round's
        figures are its own rather than a running total.

        One token trap we do not control and cannot fix from here: Anthropic
        documents `message_delta.usage` as CUMULATIVE and says a stream may emit
        more than one `message_delta`, while Mirascope `+=`s each one into the
        running total. On a stream with two, the prefill counts come back roughly
        doubled. One is the norm, so this is latent rather than live — but it is the
        second reason (after the two decoder conventions) that a streamed token
        figure deserves less trust than an awaited one.

        `pre_added=False` because this is Mirascope's STREAMING decoder, which does
        not fold cache tokens into `input_tokens` (`decode.py:286`, against `:99`
        for the awaited path). Stated rather than inferred: the arithmetic fallback
        can only disprove pre-adding, so a streamed turn whose uncached dump exceeds
        its cache read would otherwise be reported with a confidently wrong cache
        share. See `prefill_token_kwargs`.

        TWO clocks, on purpose. `seconds` runs from `call_started` — the whole
        round including any retry ladder, because the person waited through it —
        while `first_token_seconds` runs from `provider_started`, the start of the
        attempt that actually answered. Averaging a throttled round's 10s of
        backoff into a prefill figure would not just be wrong, it would be wrong in
        the direction that makes a prompt-size or caching arm look worse than it is.
        With no retry the two are the same instant to within a microsecond, and both
        deliberately include request construction (`_get_tools_call`, the
        cache-breakpoint scan) — that is the framework's own cost, on the person's
        critical path, and hiding it would flatter us.

        One consequence of subtracting the consumer's time, since `record_call`
        derives `ended` from `started + seconds`: a streamed round's recorded
        interval is SHORTER than its wall span, so `busy_s` (a union of intervals)
        does not cover the seconds the host spent rendering. That is the right side
        of the line — those seconds are not an LLM call, so they belong in the
        `wall - busy_s` remainder the census documents, not inside it.

        Fail-soft. This is observability, and a census that raises would take down
        a turn mid-stream — after the person has already read half their answer.
        """
        try:
            ended = time.monotonic()
            record_call(
                self._STREAM_ROUND_CALLER,
                # The consumer's time removed, so this is what the round cost us
                # rather than what the host did with it.
                seconds=max(0.0, ended - call_started - yielded_s),
                started=call_started,
                # `is not None`, not truthiness: this is the one line whose whole
                # job is telling "no reading" apart from "a reading", and a
                # `monotonic()` value is free to be 0.0.
                first_token_seconds=(
                    first_chunk_at - provider_started
                    if first_chunk_at is not None
                    else None
                ),
                **prefill_token_kwargs(stream, pre_added=False),
            )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).debug(
                "Streaming round not recorded to the census", exc_info=True
            )

    def _close_dangling_tool_calls(self, response: Any) -> None:
        """Answer any tool_call left unanswered when the tool loop ended.

        The loop stops after `max_tool_rounds` even if the model asked for yet
        another tool. That leaves history ending in an assistant `tool_use`
        with no `tool_result` — which every Anthropic-shaped API rejects
        outright ("`tool_use` ids were found without `tool_result` blocks
        immediately after"), because `_call_with_response_model` appends a
        plain user message next.

        Two reasons this is repaired here rather than tolerated:

        - The 400 is not the real cost. `self._messages` has already been
          reassigned from the response chain, so the malformed history is
          PERSISTED and replayed on every subsequent turn: one budget overrun
          bricks the whole session, and each turn fails citing the same stale
          tool_use id. Observed in the bench as six identical failures.
        - Dropping the trailing assistant message instead would discard
          whatever text the model produced alongside the tool call, and would
          silently hide from the model that its request went unanswered.

        Synthetic outputs carry an explicit notice (`_BUDGET_STOP_NOTICE`) so
        the transcript never implies a tool ran when it did not.
        """
        tool_calls = getattr(response, "tool_calls", None)
        if not tool_calls:
            return
        self._messages.append(
            llm.messages.user(
                [
                    ToolOutput(
                        id=tc.id,
                        name=tc.name,
                        result=self._BUDGET_STOP_NOTICE,
                    )
                    for tc in tool_calls
                ]
            )
        )
        logging.getLogger(__name__).warning(
            "Tool-call budget exhausted with %d unanswered call(s) (%s); "
            "closed with a synthetic tool_result to keep history valid.",
            len(tool_calls),
            ", ".join(tc.name for tc in tool_calls),
        )

    def _strip_unsupported_input_fields(self) -> None:
        """Strip output-only fields from self._messages before the next API call."""
        self._strip_caller_from_messages(self._messages)

    @staticmethod
    def _strip_caller_from_messages(messages: list) -> None:
        """Strip 'caller' field from tool_use blocks in raw_message dicts.

        Mirascope passes raw_message dicts back verbatim as input. If the API
        added output-only fields (like 'caller' on tool_use blocks), they cause
        400 errors on the next call. This strips them in-place.
        """
        for msg in messages:
            raw = getattr(msg, "raw_message", None)
            if not isinstance(raw, dict):
                continue
            content = raw.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    block.pop("caller", None)

    def _record_tool_call_args(self, tool_calls: Sequence[Any]) -> None:
        """Keep each call's parsed arguments alongside its name.

        Fail-soft per call: unparseable args record as `{}` rather than breaking
        a turn, since this exists purely to make a run diagnosable.
        """
        for tc in tool_calls:
            try:
                args = json.loads(tc.args) if tc.args else {}
            except (TypeError, ValueError):
                args = {}
            self.last_tool_call_args.append(args if isinstance(args, dict) else {})

    @staticmethod
    def _log_tool_calls(tool_calls: list) -> None:
        """Log tool invocations to the effect logger if configured."""
        logger = ExecutionReport._effect_logger
        if logger is None:
            return
        from dialectical_framework.agents.agent_context import get_current_agent
        from dialectical_framework.graph.scope_context import get_current_sid
        sid = get_current_sid()
        if not sid:
            return
        agent = get_current_agent() or "pipeline"
        for tc in tool_calls:
            args = json.loads(tc.args) if tc.args else {}
            logger.log_tool_call(sid, agent, tc.name, args)

    async def _start_stream_round(
        self, open_round: Callable[[], Awaitable[Any]], *, what: str
    ) -> _RoundStart:
        """Open (or resume) a streaming round, retrying where it actually fails.

        The retried unit is the open PLUS the first chunk, and that pairing is the
        whole point. `await call.stream()` issues no HTTP request — Anthropic's
        `AsyncMessages.stream` builds an un-awaited request and returns a manager
        that sends on `__aenter__`, which Mirascope's decoder defers to the first
        `__anext__`, and on Bedrock not even SigV4 signing has happened yet
        (`anthropic/lib/bedrock/_client.py`). So retrying the open alone retried
        local encoding and nothing else, which is what the ladder here used to do
        while its docstring claimed to retry connections. A 429 or a 503 landed
        inside the caller's chunk loop and took the turn down, on a path where the
        awaited equivalent would have retried it up to ten times.

        Retried on a NEW stream, never the same one: Mirascope's `chunk_stream()`
        caches consumed chunks and drives a single underlying iterator
        (`base_stream_response.py:687-735`), which is spent once it has raised.
        Re-asking is safe on both entry points — `_get_tools_call` re-renders from
        `self._messages`, and `resume_stream_async` is `response.messages + [user(
        content)]` with no mutation of the response it resumes
        (`base_provider.py:1253-1284`) — so a second call re-sends the same request
        rather than a different one. It DOES pay for the prefill twice, which is the
        price of a retry and is why the ladder stays narrow (see `retry_transient`).

        Nothing beyond the first chunk is retryable, and this is where that line
        gets drawn rather than hidden: once a chunk has been handed to the host,
        re-asking would duplicate text on their screen. A failure after that still
        propagates out of `submit_stream`.
        """

        async def _attempt() -> _RoundStart:
            provider_started = time.monotonic()
            stream = await open_round()
            chunks = stream.chunk_stream()
            try:
                first_chunk = await anext(chunks)
            except StopAsyncIteration:
                # A stream that ended before saying anything. Not an error and not
                # a reading: `first_chunk_at` stays None so the census records this
                # round as unmeasured rather than as instant.
                return _RoundStart(stream, chunks, None, provider_started, None)
            return _RoundStart(
                stream, chunks, first_chunk, provider_started, time.monotonic()
            )

        return await retry_transient(_attempt, what=what)

    async def _open_tools_stream(self) -> Any:
        """Open the turn's first streaming round from the current messages."""
        call = await self._get_tools_call()
        return await call.stream()

    async def _get_tools_call(self) -> AsyncCall:
        """Get AsyncCall object for streaming tool-calling mode."""
        messages = self._messages

        @use_brain(tools=self._tools, raw_call=True, **self._thinking_kwargs())
        async def _llm_call():
            return messages

        return await _llm_call()

    def _record_tool_results(
        self, tool_calls: Sequence[Any], tool_outputs: Sequence[Any]
    ) -> list[ToolResult]:
        """Pair executed tool calls with their outputs onto `last_tool_results`.

        Returns the same objects so the streaming path can yield exactly what
        was recorded, instead of building a second copy that could drift.

        `tool_outputs` is index-aligned with `tool_calls` (Mirascope gathers them
        in order), but the name lookup stays defensive: a mismatch must degrade
        to `"unknown"` rather than raise, since this is observability code and
        must never be the reason a turn fails.

        A tool that RAISED is logged here, because nothing else logs it.
        Mirascope catches the exception inside `Tool.execute` and hands back
        `ToolOutput(result=str(e), error=ToolExecutionError(e))` — so the
        framework's own `except: logger.exception(...)` discipline never applies
        (the exception never crosses back into `src/`), the traceback is gone,
        and the recorded outcome is `report=None`, which is exactly what a
        read-only tool produces. Measured cost: an `anchor` call that raised
        recorded as a call with no outcome and a graph with nothing in it, and
        the run had to be re-diagnosed by hand from the transcript. Logged at
        ERROR so the bench's swallowed-error capture (which listens on the
        `dialectical_framework` logger) puts it in the record.
        """
        results = []
        for i, output in enumerate(tool_outputs):
            name = tool_calls[i].name if i < len(tool_calls) else "unknown"
            text = _tool_output_text(output)
            error = getattr(output, "error", None)
            if error is not None:
                # `str(ToolExecutionError)` is the original exception's message.
                logging.getLogger(__name__).error(
                    "Tool %s raised: %s", name, error
                )
            results.append(
                ToolResult(
                    tool_name=name,
                    report=self._try_parse_execution_report(text),
                    raw_output=text,
                    error=str(error) if error is not None else None,
                )
            )
        self.last_tool_results.extend(results)
        return results

    @staticmethod
    def _try_parse_execution_report(raw_output: str) -> ExecutionReport | None:
        """Attempt to parse tool output as ExecutionReport. Returns None if not parseable."""
        try:
            return ExecutionReport.model_validate_json(raw_output)
        except Exception:
            return None

    def _thinking_kwargs(self) -> dict[str, Any]:
        """Build thinking kwargs from settings, if configured."""
        thinking_level = self.settings.thinking_level
        if thinking_level:
            return {"thinking": thinking_level}
        return {}

    async def _call_with_tools(self) -> AsyncResponse:
        """Call LLM with tools available (no format)."""
        messages = self._messages

        @use_brain(tools=self._tools, **self._thinking_kwargs())
        async def _llm_call():
            return messages

        return await _llm_call()

    @staticmethod
    def _response_text(response: Any) -> str:
        """The response's own text, stripped — or `""` if it cannot be read.

        `text` is a METHOD on every real mirascope response and stream alike
        (`RootResponse.text`, which `BaseStreamResponse` inherits), but this
        reads defensively on purpose: the suite is full of hand-rolled response
        fakes, several of which have no `text` at all and one of which is an
        `AsyncMock` where every attribute exists and returns a coroutine. A
        fake that cannot answer must not fail a turn — `""` routes the caller
        back to the extraction call, which is what it did before this existed.
        """
        raw = getattr(response, "text", None)
        if raw is None:
            return ""
        try:
            text = raw() if callable(raw) else raw
        except Exception:  # any fake or provider shape — see above
            logging.getLogger(__name__).debug(
                "Could not read response text; falling back to extraction",
                exc_info=True,
            )
            return ""
        return text.strip() if isinstance(text, str) else ""

    #: The one field a response model may declare for `_reuse_written_reply` to
    #: apply. Not a coincidence of naming: `_assistant_history_text` already
    #: treats `message` as "the prose the person reads", and all three agents'
    #: `ChatResponse` is exactly this shape.
    _REPLY_FIELD = "message"

    @classmethod
    def _is_plain_reply_model(cls, response_model: Any) -> bool:
        """True iff the model is exactly one required `str` named `message`.

        Any additional or differently-typed field means the structured call is
        doing real extraction work that prose cannot stand in for, so the
        shortcut must decline. Checked by shape rather than by identity because
        `submit` is generic and each agent declares its own `ChatResponse`.
        """
        fields = getattr(response_model, "model_fields", None)
        if not isinstance(fields, dict) or len(fields) != 1:
            return False
        field = fields.get(cls._REPLY_FIELD)
        if field is None or field.annotation is not str:
            return False
        return field.is_required()

    def _reuse_written_reply(
        self, response: Any, response_model: type[T], *, text: str | None = None
    ) -> T | None:
        """The reply the model ALREADY wrote, as `response_model` — or None.

        On a turn that ends without a tool call, the tools call has already
        produced the finished answer as prose, and the extraction call that
        follows pays a second full provider round-trip to restate that same
        text inside a one-field envelope. **Measured at +1.6s per turn** (95% CI
        0.6–2.6s, 24 paired turns on the weak tier at a 15.7k-token prompt —
        `tests/e2e/probe_reply_reuse_saving.py`), so about a fifth of a tool-free
        turn rather than the half this docstring used to claim from arithmetic:
        the second round re-sends a prompt Anthropic has already cached, so what
        it really pays for is re-emitting the reply as output tokens. It also put
        the reply into history TWICE — once from the response chain, once from
        `_call_with_response_model`'s own append.

        None means "not eligible", and the caller must fall back to
        `_call_with_response_model`, which stays a live path. Each gate is a
        case where the first response's text is NOT the finished answer:

        - **tool calls still pending.** The loop exited on its round budget,
          not because the model was done, so the text is mid-work and
          `_close_dangling_tool_calls` has just appended a synthetic user
          message. Reusing here would end history on two adjacent user turns
          and hand the person a half-finished thought.
        - **a model that is not a plain reply.** See `_is_plain_reply_model`.
        - **no readable text.** A thinking-only or tool-only response, or a
          fake that cannot answer (see `_response_text`).

        `text` overrides where the prose comes from, and the streaming path
        passes the deltas it actually yielded. That is not an optimisation: it
        is what makes `ResponseComplete.streamed` a promise rather than a hope,
        since the reply is then the same bytes the person watched arrive.

        Deliberately does NOT append to `self._messages`: the response chain
        this reads from already ends with this very assistant message, and
        `self._messages` was just synced from it.
        """
        if getattr(response, "tool_calls", None):
            return None
        if not self._is_plain_reply_model(response_model):
            return None
        reply = text.strip() if text is not None else self._response_text(response)
        if not reply:
            return None
        return response_model(**{self._REPLY_FIELD: reply})

    async def _call_with_response_model(self, response_model: type[T]) -> T:
        """Call LLM with format for structured output.

        Still reached on every turn whose reply cannot be reused as written —
        see `_reuse_written_reply` for which turns those are."""
        messages = self._messages

        # Bedrock requires conversations to end with a user message.
        # After the agentic tool loop, messages end with assistant — inject a
        # user prompt so the extraction call is valid for all providers.
        #
        # It must not read as something the PERSON said. This slot is the only
        # place the framework speaks human-readable prose in the user role, and
        # the model attributed it to the person: measured in 8 turns across four
        # bench runs (r7, r10, r11, r14), all A2 — prompt-only arms never hit it
        # because only the tools path reaches this call. The failure is worse
        # than a stray mention, because the model then interprets the person's
        # imagined motive for "saying" it: "you asked for a structured response,
        # which is code for 'tell me I've decided'", "That's a deflection, and
        # I'm not going to record a decision on a deflection", and one turn
        # answering with a numbered menu of internal operations ("the 'provide
        # structured response' signal tells me you want more than
        # conversation") — scored 1/5 on cross-turn coherence, the worst cell
        # in r14. The person is then accused of deflecting by a system talking
        # to itself.
        #
        # So it is marked as machinery, not speech, and says what it is for.
        # `_reuse_written_reply` removed this call from the common case, which
        # shrinks the exposure but does not close it: the fallback turns are
        # exactly the ones already going badly (budget exhausted, no text), so
        # the framing here still has to hold.
        if messages and messages[-1].role == "assistant":
            messages = [*messages, llm.messages.user(_EXTRACTION_REQUEST)]

        @use_brain(format=response_model)
        async def _llm_call():
            return messages

        result = await _llm_call()
        self._messages.append(
            llm.messages.assistant(
                self._assistant_history_text(result),
                model_id=None,
                provider_id=None,
            )
        )
        return result

    @staticmethod
    def _assistant_history_text(result: Any) -> str:
        """History form of a structured result: natural text, not a Pydantic
        repr. This history is replayed to the provider every turn (and across
        agent-toggle handovers) — `message='...'` repr syntax wastes tokens
        and invites the model to imitate it. DTOs without a `message` field
        fall back to str()."""
        message = getattr(result, "message", None)
        if isinstance(message, str) and message:
            return message
        return str(result)
