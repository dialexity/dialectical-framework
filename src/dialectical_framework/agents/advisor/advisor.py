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

import asyncio
import logging
from typing import AsyncGenerator, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.advisor.system_prompts import (
    SYSTEM_PROMPT, system_prompt)
from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.stream_events import StreamEvent

logger = logging.getLogger(__name__)

# Tools that mutate the graph: when the model already called one of these
# during a turn, the background-analysis guarantee is satisfied by the model
# itself and the hook stays quiet.
_GRAPH_BUILDING_TOOLS = {"ingest", "anchor", "explore"}

# Messages shorter than this (in words) are treated as not counsel-shaped
# (greetings, logistics, quick acknowledgements) and skip background analysis.
_MIN_ANALYSIS_WORDS = 8


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

    Background analysis (default on): graph-building is guaranteed in code,
    not just via the model's tool choices. After each counsel-shaped turn
    where the model did NOT call a graph-building tool, chat() fires an
    AnalysisPipeline run over the user's message as a background task. The
    task is awaited (drained) at the start of the next turn, so graph writes
    never overlap the next turn's tool calls. Call `flush_analysis()` before
    persisting messages or tearing down, so the last turn's analysis lands.
    Caveat: the background task may write to the graph after the host's
    `with scope(sid):` block exits (the sid is captured via contextvars) —
    the host must not tear down the DB connection between turns. Pass
    `background_analysis=False` for manual control.

    The system prompt's Current Understanding section is refreshed at the
    start of a turn whenever the graph changed since it was last rendered
    (via background analysis or the model's own graph tools).

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

    Usage (nexus-scoped: counsel on ONE exploration built by Analyst+Explorer):
        with scope(case.sid):
            advisor = Advisor(app_preamble=COUNSELOR_APP, nexus_hash="abc1234")
            response = await advisor.chat("So what does this all mean for me?")

        Scope is enforced in code: the tools close over nexus_hash — the model
        cannot create sibling nexuses or reach outside the exploration.
        Read-mostly by default (sync/inspect_node/read_digest/discard);
        pass enrichment=True to also allow anchor + explore pinned to this
        nexus. Background analysis is disabled unless enrichment=True (a
        read-mostly advisor must not grow the graph). Requires an active
        scope(sid) at construction (nexus is validated against the DB).
    """

    AGENT_NAME = "advisor"

    def __init__(
        self,
        app_preamble: Optional[str] = None,
        dialectical_context: Optional[str] = None,
        messages: Optional[list] = None,
        background_analysis: bool = True,
        nexus_hash: Optional[str] = None,
        enrichment: bool = False,
    ) -> None:
        self._nexus_hash = nexus_hash
        self._enrichment = enrichment
        if nexus_hash:
            self._validate_nexus(nexus_hash)
            self._tools = _build_scoped_tools(nexus_hash, enrichment)
            # A read-mostly advisor must not grow the graph silently.
            self._background_analysis = background_analysis and enrichment
        else:
            self._tools = _build_tools()
            self._background_analysis = background_analysis
        self._conversation = ConversationFacilitator(tools=self._tools)
        if messages:
            self._conversation._messages = list(messages)
        self._app_preamble = app_preamble
        self._background_task: asyncio.Task | None = None
        # Scoped mode without a precomputed context: mark dirty so turn 1
        # renders the scoped dump (init is sync; resolve() is async).
        self._context_dirty = bool(nexus_hash and not dialectical_context)
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
        if self._nexus_hash:
            engine = system_prompt(
                tool_names=[t.__name__ for t in self._tools],
                scoped_nexus_hash=self._nexus_hash,
                enrichment=self._enrichment,
            )
        else:
            engine = SYSTEM_PROMPT
        parts.append(engine.replace("{dialectical_context}", context_text))

        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        with agent_scope(self.AGENT_NAME):
            await self._drain_background()
            await self._refresh_context()
            result = await self._conversation.submit(ChatResponse, user_message)
            self._maybe_start_background_analysis(user_message)
            return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        with agent_scope(self.AGENT_NAME):
            await self._drain_background()
            await self._refresh_context()
            async for event in self._conversation.submit_stream(
                ChatResponse, user_message
            ):
                yield event
            # Note: if the host abandons the stream mid-way, this never runs
            # and the hook simply skips this turn (fail-soft).
            self._maybe_start_background_analysis(user_message)

    async def flush_analysis(self) -> None:
        """
        Await any in-flight background analysis and refresh the system prompt.

        Hosts should call this before persisting messages or ending the
        session, so the last turn's analysis lands in the graph.
        """
        await self._drain_background()
        await self._refresh_context()

    def _maybe_start_background_analysis(self, user_message: str) -> None:
        """
        Guarantee graph-building in code: if this turn was counsel-shaped and
        the model didn't build graph structure itself, run AnalysisPipeline
        over the user's message as a background task.

        The task inherits scope(sid)/agent_scope via contextvars (captured at
        create_task time). It is drained at the start of the next turn, so
        graph writes stay serialized (GQLAlchemy is not concurrency-safe).
        """
        if not self._background_analysis:
            return
        if len(user_message.split()) < _MIN_ANALYSIS_WORDS:
            return
        if _GRAPH_BUILDING_TOOLS & set(self._conversation.last_tool_calls):
            # Model built structure itself this turn; refresh context next turn.
            self._context_dirty = True
            return
        self._background_task = asyncio.create_task(
            self._run_background_analysis(user_message)
        )

    async def _run_background_analysis(self, user_message: str) -> None:
        from dialectical_framework.agents.analyst.analyst import \
            AnalysisPipeline

        try:
            pipeline = AnalysisPipeline(text=user_message)
            result = await pipeline.resolve()
            if result and result.perspective_hashes:
                self._context_dirty = True
        except Exception:
            # Fail-soft: background analysis must never break the chat path.
            logger.exception("Background analysis failed")

    async def _drain_background(self) -> None:
        if self._background_task is None:
            return
        task, self._background_task = self._background_task, None
        try:
            await task
        except Exception:
            logger.exception("Background analysis task raised on drain")

    async def _refresh_context(self) -> None:
        """Re-render Current Understanding into the system prompt if stale."""
        if not self._context_dirty:
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
            self._context_dirty = False
        except Exception:
            # Fail-soft: a failed refresh must not block the turn; the model
            # still sees fresh state through tool results / sync.
            logger.exception("Dialectical context refresh failed")

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
    from dialectical_framework.agents.orchestrator.tools.discard import \
        discard

    return [
        ingest,
        anchor,
        explore,
        sync,
        inspect_node,
        read_digest,
        discard,
    ]


def _build_scoped_tools(nexus_hash: str, enrichment: bool = False) -> list:
    from dialectical_framework.agents.advisor.tools.scoped import \
        build_scoped_tools

    return build_scoped_tools(nexus_hash, enrichment)
