"""
ConversationFacilitator: Helper for managing LLM conversation with tool calling.

Facilitator that:
- Maintains conversation message history
- Supports tool calling with automatic execution loop
- Provides easy LLM calls with structured responses
- Can be composed into tools, services, or agents
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, TypeVar

from mirascope import Messages
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from mirascope import BaseTool
    from mirascope.core.base import BaseMessageParam

T = TypeVar("T")


class ConversationFacilitator(HasBrain, SettingsAware):
    """
    Helper for managing LLM conversation with optional tool calling.

    Use via composition in tools, services, or agents that need
    multi-step LLM interactions with shared context.

    Example without tools:
        facilitator = ConversationFacilitator()
        facilitator.set_system_prompt("You are...")
        result = await facilitator.submit(MyDto, "Extract...")

    Example with tools:
        facilitator = ConversationFacilitator(tools=[ExtractTheses, ExtractAntitheses])
        facilitator.set_system_prompt("You are an agent...")
        result = await facilitator.submit(FinalResultDto, "Find 3 theses about trust")
        # Tools are automatically called and results injected into conversation

    Example with parallel isolated calls:
        tasks = [facilitator.isolate().submit(Dto, msg) for msg in messages]
        results = await asyncio.gather(*tasks)
    """

    def __init__(self, tools: Optional[list[type[BaseTool]]] = None) -> None:
        self._messages: list[Messages.Type] = []
        self._tools = tools or []

    def set_system_prompt(self, system_prompt: str) -> None:
        """
        Set the system prompt for this conversation.

        Must be the first message. If called after other messages exist,
        inserts at the beginning (if no system prompt yet) or raises error.
        """
        system_msg = Messages.System(system_prompt)

        if not self._messages:
            self._messages.append(system_msg)
        elif self._messages[0].get("role") == "system":
            raise ValueError("System prompt already set. Cannot set it twice.")
        else:
            self._messages.insert(0, system_msg)

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
        2. If LLM calls tools, execute them and add results to messages
        3. Repeat until LLM returns final response (no tool calls)
        4. Extract structured response from final message

        Args:
            response_model: Pydantic model for structured output
            user_content: User message to submit
            max_tool_rounds: Maximum tool execution rounds (default 10)

        Returns:
            Structured response matching response_model
        """
        self._messages.append(Messages.User(user_content))

        if not self._tools:
            # Simple path: no tools, just call LLM with response_model
            return await self._call_with_response_model(response_model)

        # Agentic loop: call LLM with tools until no more tool calls
        for _ in range(max_tool_rounds):
            response = await self._call_with_tools()

            if response.tools:
                # Execute tools and collect results
                tools_and_outputs: list[tuple[BaseTool, str]] = []
                for tool in response.tools:
                    output = await tool.call()
                    tools_and_outputs.append((tool, output))

                # Add assistant message with tool calls
                self._add_assistant_tool_call_message(response)

                # Add tool results to messages
                self._messages += response.tool_message_params(tools_and_outputs)
            else:
                # No more tool calls - get final structured response
                self._messages.append(response.message_param)

                # Now extract structured response
                return await self._call_with_response_model(response_model)

        # Max rounds reached - try to extract response anyway
        return await self._call_with_response_model(response_model)

    # --- Internal helpers ---

    async def _call_with_tools(self):
        """Call LLM with tools available (no response_model)."""
        messages = self._messages

        @with_langfuse()
        @use_brain(brain=self.brain, tools=self._tools)
        async def _llm_call():
            return {"messages": messages}

        return await _llm_call()

    async def _call_with_response_model(self, response_model: type[T]) -> T:
        """Call LLM with response_model for structured output."""
        messages = self._messages

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=response_model)
        async def _llm_call():
            return {"messages": messages}

        result = await _llm_call()
        self._messages.append(Messages.Assistant(str(result)))
        return result

    def _add_assistant_tool_call_message(self, response) -> None:
        """Add assistant message with tool calls to history."""
        tool_calls = []
        for t in response.common_tools or []:
            tc = t.tool_call
            tool_calls.append({
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            })

        self._messages.append({
            "role": "assistant",
            "content": response.content or "",
            "tool_calls": tool_calls,
        })
