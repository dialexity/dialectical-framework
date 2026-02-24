"""
ConversationalTool: Base class for LLM tools with conversation history.

Enables prompt caching by maintaining conversation context across steps.

Benefits:
- Prompt caching: Sequential steps share cached prefix
- Context preservation: Later steps see earlier responses

Usage:
    class MyTool(ConversationalTool):
        async def call(self) -> str:
            self._messages.append(Messages.System("You are a helpful assistant."))

            result1 = await self._converse(
                response_model=Step1Dto,
                user_content="Step 1: ...",
            )

            # Step 2 has context from step 1
            result2 = await self._converse(
                response_model=Step2Dto,
                user_content=f"Step 2: based on {result1.value}...",
            )
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from mirascope import BaseTool, Messages
from mirascope.integrations.langfuse import with_langfuse
from pydantic import PrivateAttr

from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from mirascope.core.base import BaseMessageParam

T = TypeVar("T")


class ConversationalTool(BaseTool, HasBrain, SettingsAware):
    """
    Base class for LLM tools that maintain conversation history.

    Enables prompt caching by preserving context across multiple LLM calls
    within a single tool execution.

    Subclasses should:
    1. Append system message to _messages at start of call()
    2. Use _converse() for each LLM interaction
    """

    _messages: list[BaseMessageParam] = PrivateAttr(default_factory=list)

    async def _converse(
        self,
        response_model: type[T],
        user_content: str,
    ) -> T:
        """
        Continue conversation with a new user message and extract structured response.

        Appends user message to history, makes LLM call with full context,
        and appends assistant response to history.

        Args:
            response_model: Pydantic model for structured extraction
            user_content: The user message content

        Returns:
            Extracted response matching response_model
        """
        self._messages.append(Messages.User(user_content))

        messages = self._messages

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=response_model)
        async def _llm_call():
            return {"messages": messages}

        result = await _llm_call()

        self._messages.append(Messages.Assistant(str(result)))

        return result

    async def _converse_isolated(
        self,
        response_model: type[T],
        user_content: str,
    ) -> T:
        """
        Make an isolated LLM call using a snapshot of current conversation context.

        Use this for parallel calls (e.g., with asyncio.gather) to avoid race
        conditions on self._messages. Each call gets its own copy of the message
        history, so concurrent modifications don't interfere.

        NOTE: Does NOT merge results back into self._messages. Use only when
        these are terminal calls (no subsequent _converse calls depend on them).

        Args:
            response_model: Pydantic model for structured extraction
            user_content: The user message content

        Returns:
            Extracted response matching response_model
        """
        # Snapshot current messages and append user content to the copy
        messages = [*self._messages, Messages.User(user_content)]

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=response_model)
        async def _llm_call():
            return {"messages": messages}

        return await _llm_call()
