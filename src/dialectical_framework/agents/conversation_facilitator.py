"""
ConversationFacilitator: Helper for managing LLM conversation with tool calling.

Facilitator that:
- Maintains conversation message history
- Supports tool calling with automatic execution loop
- Provides easy LLM calls with structured responses
- Can be composed into tools, services, or agents
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional, Sequence, TypeVar

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
from dialectical_framework.utils.retry_accounting import (RetryAccount,
                                                          record_retry,
                                                          retry_account)
from dialectical_framework.utils.use_brain import use_brain

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

        # `finally`, not a plain assignment before each return: a turn that
        # RAISED still waited the person's time, and a duration recorded only on
        # the happy path makes the expensive failures the invisible ones.
        started = time.monotonic()
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
        """
        self._messages.append(llm.messages.user(user_content))
        self.last_tool_calls = []
        # Reset the results too, exactly as `submit` does. Without this a turn
        # inherits the previous turn's outcomes, so a crash gets attributed to a
        # healthy turn and the healthy turn's own tools look unreported.
        self.last_tool_results = []
        self.last_tool_call_args = []
        self.last_tool_rounds = []
        self.last_submit_seconds = 0.0
        self.last_submit_retries = RetryAccount()
        started = time.monotonic()

        # Re-entered per await instead of wrapped around the whole generator, and
        # `retry_account` explains why: a contextvar set across a `yield` installs
        # itself in the consumer's context and never resets if the consumer stops
        # iterating. The uncovered gap is the `chunk_stream()` loop below, which
        # cannot retry anyway once tokens are flowing.
        turn = self.last_submit_retries

        if not self._tools:
            # No stream at all on this path: one formatted call, so there is
            # nothing to yield until it returns. `streamed=False` says so.
            with retry_account(turn):
                result = await self._call_with_response_model(response_model)
            self.last_submit_seconds = time.monotonic() - started
            yield ResponseComplete(result=result)
            return

        with retry_account(turn):
            stream = await self._open_stream_with_retry()

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
        for _ in range(max_tool_rounds):
            answer = []
            async for chunk in stream.chunk_stream():
                if isinstance(chunk, ThoughtChunk):
                    yield ThinkingDelta(text=chunk.delta)
                elif isinstance(chunk, TextChunk):
                    answer.append(chunk.delta)
                    yield TextDelta(text=chunk.delta)

            if not stream.tool_calls:
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
            with retry_account(turn):
                stream = await stream.resume(tool_outputs)

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
        # Before the yield: the reply-path interval ends when the reply EXISTS,
        # and a consumer that stops iterating at ResponseComplete would otherwise
        # leave this unset on the very turns it is measuring.
        self.last_submit_seconds = time.monotonic() - started
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

    async def _open_stream_with_retry(self, max_attempts: int = 3) -> Any:
        """Open a streaming connection with retry on transient failures.

        Retries the initial stream connection (provider errors, network blips).
        Once streaming begins and tokens are yielded, retry is no longer possible
        for that round — only the connection handshake is retried.
        """
        delay = 5.0
        last_error: Optional[Exception] = None
        for attempt in range(max_attempts):
            attempt_started = time.monotonic()
            try:
                call = await self._get_tools_call()
                return await call.stream()
            except Exception as e:
                last_error = e
                if attempt < max_attempts - 1:
                    logging.getLogger(__name__).warning(
                        "Stream connection failed (attempt %d/%d): %s",
                        attempt + 1, max_attempts, e,
                    )
                    # This ladder is the facilitator's own, so `use_brain` never
                    # sees it — up to 35s of reply-path sleep that would
                    # otherwise land in the generation residual unlabelled.
                    record_retry(
                        "stream_open",
                        sleep_s=delay,
                        attempt_s=time.monotonic() - attempt_started,
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2.0, 30.0)
        raise last_error  # type: ignore[misc]

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
        text inside a one-field envelope. It was roughly half of an 18.55s
        median reply path (`tests/e2e/rounds.md`, the timing rounds), and it
        also put the reply into history TWICE — once from the response chain,
        once from `_call_with_response_model`'s own append.

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
