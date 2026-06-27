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
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional, TypeVar

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
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

from mirascope.llm import TextChunk, ThoughtChunk

if TYPE_CHECKING:
    from mirascope.llm.calls import AsyncCall
    from mirascope.llm.responses import AsyncResponse

T = TypeVar("T")


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
        user_content: str,
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

        if not self._tools:
            return await self._call_with_response_model(response_model)

        # Agentic loop: resume() accumulates messages internally
        response = await self._call_with_tools()
        for _ in range(max_tool_rounds):
            if not response.tool_calls:
                break
            self._log_tool_calls(response.tool_calls)
            tool_outputs = await response.execute_tools()
            self._strip_caller_from_messages(response.messages)
            response = await response.resume(tool_outputs)

        # Sync full conversation history from the response chain
        self._messages = list(response.messages)
        self._strip_unsupported_input_fields()

        # Extract structured response
        return await self._call_with_response_model(response_model)

    @observe()
    async def submit_stream(
        self,
        response_model: type[T],
        user_content: str,
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

        if not self._tools:
            result = await self._call_with_response_model(response_model)
            yield ResponseComplete(result=result)
            return

        stream = await self._open_stream_with_retry()

        for _ in range(max_tool_rounds):
            async for chunk in stream.chunk_stream():
                if isinstance(chunk, ThoughtChunk):
                    yield ThinkingDelta(text=chunk.delta)
                elif isinstance(chunk, TextChunk):
                    yield TextDelta(text=chunk.delta)

            if not stream.tool_calls:
                break

            for tc in stream.tool_calls:
                yield ToolStart(
                    tool_name=tc.name,
                    tool_args=json.loads(tc.args) if tc.args else {},
                )

            self._log_tool_calls(stream.tool_calls)
            tool_outputs = await stream.execute_tools()

            for i, output in enumerate(tool_outputs):
                tool_name = stream.tool_calls[i].name if i < len(stream.tool_calls) else "unknown"
                raw_str = str(output)
                report = self._try_parse_execution_report(raw_str)
                yield ToolResult(tool_name=tool_name, report=report, raw_output=raw_str)

            self._strip_caller_from_messages(stream.messages)
            stream = await stream.resume(tool_outputs)

        self._messages = list(stream.messages)
        self._strip_unsupported_input_fields()
        result = await self._call_with_response_model(response_model)
        yield ResponseComplete(result=result)

    # --- Internal helpers ---

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

    async def _call_with_response_model(self, response_model: type[T]) -> T:
        """Call LLM with format for structured output."""
        messages = self._messages

        # Bedrock requires conversations to end with a user message.
        # After the agentic tool loop, messages end with assistant — inject a
        # user prompt so the extraction call is valid for all providers.
        if messages and messages[-1].role == "assistant":
            messages = [*messages, llm.messages.user("Provide your structured response.")]

        @use_brain(format=response_model)
        async def _llm_call():
            return messages

        result = await _llm_call()
        self._messages.append(llm.messages.assistant(str(result), model_id=None, provider_id=None))
        return result
