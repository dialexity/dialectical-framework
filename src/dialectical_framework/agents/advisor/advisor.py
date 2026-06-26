"""
Advisor: Conversational agent for advisory apps.

Pure conversation — the framework runs silently in the background.
The user never sees framework terminology, just experiences progressively
wiser responses as dialectical understanding builds.

Two use cases:
- Fresh start: user talks, framework builds graph behind the scenes.
- Post-analysis: rich graph exists, advisor draws on it immediately.
"""

from __future__ import annotations

from typing import AsyncGenerator, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.system_prompts import SYSTEM_PROMPT
from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import StreamEvent


class ChatResponse(BaseModel):
    """Response from the advisor chat."""

    message: str = Field(description="The assistant's response message")


class Advisor:
    """
    Conversational agent for advisory apps.

    The host app is responsible for:
    - Creating the Case and managing scope(sid)
    - Persisting and loading conversation messages
    - Wrapping chat() calls in `with scope(sid):`
    - Optionally pre-computing dialectical_context via DialecticalContext

    Usage (fresh start):
        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_APP)
            response = await advisor.chat("My son started smoking...")

    Usage (post-analysis, rich graph exists):
        with scope(case.sid):
            context = await DialecticalContext().resolve()
            advisor = Advisor(app_preamble=COUNSELOR_APP, dialectical_context=context)
            response = await advisor.chat("I want to talk through what we found...")

    Usage (resuming conversation):
        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_APP, messages=saved_messages)
            response = await advisor.chat("What about the other angle?")
    """

    AGENT_NAME = "advisor"

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        dialectical_context: Optional[str] = None,
        messages: Optional[list] = None,
    ) -> None:
        self._tools = _build_tools()
        self._conversation = ConversationFacilitator(tools=self._tools)
        if messages:
            self._conversation._messages = list(messages)
        self._conversation.set_system_prompt(
            self._build_system_prompt(app_preamble, dialectical_context)
        )

    def _build_system_prompt(
        self,
        app_preamble: Optional[str] = None,
        dialectical_context: Optional[str] = None,
    ) -> str:
        parts = []
        if app_preamble:
            parts.append(app_preamble)

        context_text = (
            dialectical_context
            or "No prior understanding — this is a fresh conversation."
        )
        system = SYSTEM_PROMPT.replace("{dialectical_context}", context_text)
        parts.append(system)

        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        with agent_scope(self.AGENT_NAME):
            result = await self._conversation.submit(ChatResponse, user_message)
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        with agent_scope(self.AGENT_NAME):
            async for event in self._conversation.submit_stream(
                ChatResponse, user_message
            ):
                yield event

    @property
    def messages(self) -> list:
        return self._conversation._messages


def _build_tools() -> list:
    from dialectical_framework.agents.advisor.tools.anchor import anchor
    from dialectical_framework.agents.advisor.tools.explore import explore
    from dialectical_framework.agents.advisor.tools.ingest import ingest
    from dialectical_framework.agents.advisor.tools.sync import sync
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest

    return [
        ingest,
        anchor,
        explore,
        sync,
        inspect_node,
        read_digest,
    ]
