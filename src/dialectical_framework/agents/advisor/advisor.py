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

import logging
from typing import AsyncGenerator, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.system_prompts import \
    system_prompt
from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import StreamEvent

logger = logging.getLogger(__name__)


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

    The system prompt is static after its first render: the Current
    Understanding dump reflects the graph at construction time. Fresh graph
    state flows through the conversation itself — tool results carry each
    change, and the model calls `sync` when it wants a full re-dump. (One
    exception: an exploration-pinned Advisor constructed without a precomputed
    dialectical_context renders its scoped dump lazily on the first turn,
    because __init__ is sync and DialecticalContext.resolve() is async. A
    transient render failure retries on the next turn; only success — or a
    vanished nexus — consumes the one shot.)

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

    Usage (Advisor mode of an exploration session — Explorer handover):
        # User was chatting in Explorer (operator mode) and asks "what does
        # this all mean for me?" — the host toggles to counsel mode by
        # handing the SAME conversation to an Advisor pinned to the SAME
        # exploration:
        with scope(case.sid):
            advisor = Advisor(
                app_preamble=EXPLORATION_ADVISOR_APP,
                nexus_hash=explorer.nexus_hash,
                messages=explorer.messages,
            )
            response = await advisor.chat("So what does this all mean for me?")

        # Toggling back to operator mode is the reverse handover:
        #   Explorer(nexus_hash=nx, messages=advisor.messages, ...)

        This is a register toggle, not a different scope: same conversation,
        same exploration, different head. The Advisor keeps its full
        analytical power (it IS Analyst+Explorer behind one voice): it
        anchors new tensions from the conversation and weaves them in. The
        nexus pin is enforced in code: the tools close over nexus_hash — the
        model cannot create sibling nexuses or reach outside the exploration.
        Requires an active scope(sid) at construction (nexus is validated
        against the DB). The host app drives the toggle — there is no
        automatic agent-switching.
    """

    AGENT_NAME = "advisor"

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        dialectical_context: Optional[str] = None,
        messages: Optional[list] = None,
        nexus_hash: Optional[str] = None,
    ) -> None:
        self._nexus_hash = nexus_hash
        if nexus_hash:
            self._validate_nexus(nexus_hash)
            self._tools = _build_scoped_tools(nexus_hash)
        else:
            self._tools = _build_tools()
        self._conversation = ConversationFacilitator(tools=self._tools)
        if messages:
            self._conversation._messages = list(messages)
        self._app_preamble = app_preamble
        # Scoped mode without a precomputed context: render the scoped dump
        # lazily on turn 1 (init is sync; resolve() is async). One-shot —
        # the system prompt is static after its first render.
        self._pending_context_render = bool(nexus_hash and not dialectical_context)
        self._conversation.set_system_prompt(
            self._build_system_prompt(app_preamble, dialectical_context)
        )

    @staticmethod
    def _validate_nexus(nexus_hash: str) -> None:
        from dialectical_framework.graph.repositories.nexus_repository import \
            NexusRepository

        if NexusRepository().find_by_hash_prefix(nexus_hash) is None:
            raise ValueError(f"Nexus not found: {nexus_hash}")

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
        # Rendered at construction (not the import-time SYSTEM_PROMPT
        # constant) so settings-derived prompt values (max_wheel_layer)
        # reflect the live DI configuration.
        engine = system_prompt(
            tool_names=[t.__name__ for t in self._tools],
            scoped_nexus_hash=self._nexus_hash,
        )
        parts.append(engine.replace("{dialectical_context}", context_text))

        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        with agent_scope(self.AGENT_NAME):
            await self._render_pending_context()
            result = await self._conversation.submit(ChatResponse, user_message)
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        with agent_scope(self.AGENT_NAME):
            await self._render_pending_context()
            async for event in self._conversation.submit_stream(
                ChatResponse, user_message
            ):
                yield event

    async def _render_pending_context(self) -> None:
        """One-shot deferred render of the scoped Current Understanding dump
        (scoped construction without a precomputed dialectical_context).

        One-shot on SUCCESS — a transient failure (DB blip) keeps the flag
        set so the next turn retries, instead of leaving the whole session
        with a prompt that claims rich understanding over an empty slot.
        """
        if not self._pending_context_render:
            return
        try:
            from dialectical_framework.concerns.dialectical_context import \
                DialecticalContext

            context = await DialecticalContext(
                nexus_hash=self._nexus_hash
            ).resolve()
            self._conversation.set_system_prompt(
                self._build_system_prompt(self._app_preamble, context)
            )
            self._pending_context_render = False
        except ValueError:
            # Nexus disappeared — not transient, don't retry forever.
            self._pending_context_render = False
            logger.exception("Deferred dialectical context render failed")
        except Exception:
            # Fail-soft this turn; retry next turn. The model still reaches
            # graph state through sync meanwhile.
            logger.exception("Deferred dialectical context render failed")

    @property
    def messages(self) -> list:
        return self._conversation._messages


def _build_tools() -> list:
    from dialectical_framework.agents.advisor.tools.anchor import anchor
    from dialectical_framework.agents.advisor.tools.deepen import deepen
    from dialectical_framework.agents.advisor.tools.explore import explore
    from dialectical_framework.agents.advisor.tools.ingest import ingest
    from dialectical_framework.agents.advisor.tools.sync import sync
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest
    from dialectical_framework.agents.orchestrator.tools.discard import \
        discard

    return [
        ingest,
        anchor,
        explore,
        deepen,
        sync,
        inspect_node,
        read_digest,
        discard,
    ]


def _build_scoped_tools(nexus_hash: str) -> list:
    from dialectical_framework.agents.advisor.tools.scoped import \
        build_scoped_tools

    return build_scoped_tools(nexus_hash)
