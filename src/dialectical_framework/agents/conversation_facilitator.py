"""
ConversationFacilitator: Helper for managing LLM conversation with tool calling.

Facilitator that:
- Maintains conversation message history
- Supports tool calling with automatic execution loop
- Provides easy LLM calls with structured responses
- Can be composed into tools, services, or agents
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, TypeVar

from mirascope import llm

from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
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
        Set the system prompt for this conversation.

        Must be the first message. If called after other messages exist,
        inserts at the beginning (if no system prompt yet) or raises error.
        """
        system_msg = llm.messages.system(system_prompt)

        if not self._messages:
            self._messages.append(system_msg)
        elif hasattr(self._messages[0], "role") and self._messages[0].role == "system":
            raise ValueError("System prompt already set. Cannot set it twice.")
        elif isinstance(self._messages[0], dict) and self._messages[0].get("role") == "system":
            raise ValueError("System prompt already set. Cannot set it twice.")
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
            tool_outputs = await response.execute_tools()
            response = await response.resume(tool_outputs)

        # Sync full conversation history from the response chain
        self._messages = list(response.messages)

        # Extract structured response
        return await self._call_with_response_model(response_model)

    # --- Internal helpers ---

    async def _call_with_tools(self) -> AsyncResponse:
        """Call LLM with tools available (no format)."""
        messages = self._messages

        @use_brain(tools=self._tools)
        async def _llm_call():
            return messages

        return await _llm_call()

    async def _call_with_response_model(self, response_model: type[T]) -> T:
        """Call LLM with format for structured output."""
        messages = self._messages

        @use_brain(format=response_model)
        async def _llm_call():
            return messages

        result = await _llm_call()
        self._messages.append(llm.messages.assistant(str(result), model_id=None, provider_id=None))
        return result
