"""
Explorer: Conversational agent for dialectical exploration.

Scoped to a Case + Nexus (sid + nexus_hash). Helps users navigate
transformations and understand the synthetic wisdom (Ac+, Re+, S+).

Two modes:
- default: Navigational guide. Builds wheels, presents pathways practically.
- advanced: Structural view. Shows raw positions, scores, edges.

Also contains ExplorationPipeline — the headless pipeline for programmatic use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator, Literal, Optional

from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.explorer.system_prompts import (
    advanced_system_prompt, default_system_prompt)
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.graph.repositories.nexus_repository import \
    NexusRepository

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Conversational Agent
# ---------------------------------------------------------------------------


class ChatResponse(BaseModel):
    """Response from the explorer chat."""

    message: str = Field(description="The assistant's response message")


class Explorer:
    """
    Conversational agent for dialectical exploration.

    Scoped to a Nexus within a Case. The host app is responsible for:
    - Managing scope(sid)
    - Persisting and loading conversation messages
    - Wrapping chat() calls in `with scope(sid):`

    Usage:
        with scope(case.sid):
            explorer = Explorer(nexus_hash="abc1234", app_preamble="...")
            response = await explorer.chat("What pathways do I have?")

        # Resuming with history:
        with scope(case.sid):
            explorer = Explorer(nexus_hash="abc1234", messages=loaded_messages)
            response = await explorer.chat("Tell me about the Ac+ path")
    """

    def __init__(
        self,
        nexus_hash: str,
        mode: Literal["default", "advanced"] = "default",
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
    ) -> None:
        self._nexus_hash = nexus_hash
        self._mode = mode
        self._tools = _build_tool_list(mode)
        self._conversation = ConversationFacilitator(tools=self._tools)

        if messages:
            self._conversation._messages = list(messages)
        nexus_intent = self._resolve_nexus_intent()
        self._conversation.set_system_prompt(
            self._build_system_prompt(nexus_hash, nexus_intent, app_preamble)
        )

    def _resolve_nexus_intent(self) -> str:
        repo = NexusRepository()
        nexus = repo.find_by_hash_prefix(self._nexus_hash)
        if nexus is None:
            raise ValueError(f"Nexus not found: {self._nexus_hash}")
        return nexus.intent or "(no intent specified)"

    def _build_system_prompt(
        self, nexus_hash: str, nexus_intent: str, app_preamble: Optional[str] = None
    ) -> str:
        parts = []
        if app_preamble:
            parts.append(app_preamble)
        if self._mode == "advanced":
            parts.append(
                advanced_system_prompt(nexus_hash=nexus_hash, nexus_intent=nexus_intent)
            )
        else:
            parts.append(
                default_system_prompt(nexus_hash=nexus_hash, nexus_intent=nexus_intent)
            )
        return "\n\n".join(parts)

    async def chat(self, user_message: str) -> str:
        result = await self._conversation.submit(ChatResponse, user_message)
        return result.message

    async def chat_stream(self, user_message: str) -> AsyncGenerator[StreamEvent, None]:
        async for event in self._conversation.submit_stream(
            ChatResponse, user_message
        ):
            yield event

    @property
    def messages(self) -> list:
        return self._conversation._messages

    @property
    def nexus_hash(self) -> str:
        return self._nexus_hash

    @property
    def mode(self) -> str:
        return self._mode


def _build_tool_list(mode: str) -> list:
    if mode == "advanced":
        return _advanced_tools()
    return _default_tools()


def _default_tools() -> list:
    from dialectical_framework.agents.explorer.skills.build_wheels import \
        build_wheels
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        explore_transformations
    from dialectical_framework.agents.explorer.tools.present_exploration import \
        present_exploration
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph

    return [
        build_wheels,
        explore_transformations,
        present_exploration,
        inspect_node,
        query_graph,
        get_schema,
    ]


def _advanced_tools() -> list:
    from dialectical_framework.agents.explorer.skills.build_wheels import \
        build_wheels
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        explore_transformations
    from dialectical_framework.agents.explorer.tools.create_nexus import \
        create_nexus
    from dialectical_framework.agents.explorer.tools.present_exploration import \
        present_exploration
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph

    return [
        build_wheels,
        explore_transformations,
        create_nexus,
        present_exploration,
        inspect_node,
        query_graph,
        get_schema,
    ]


# ---------------------------------------------------------------------------
# Headless Pipeline (for programmatic use)
# ---------------------------------------------------------------------------


class StepError(BaseModel):
    step: str
    message: str
    hash: Optional[str] = None


class ExplorationResult(BaseModel):
    nexus_hash: str
    cycle_hashes: list[str] = []
    wheel_hashes: list[str] = []
    transformation_count: int = 0
    errors: list[StepError] = []
    reports: list = []

    model_config = {"arbitrary_types_allowed": True}


class ExplorationPipeline(ReasonableConcern[ExplorationResult]):
    """
    Headless exploration pipeline.

    Runs the full exploration within an existing Nexus:
    1. Build structural combinations (Cycles + Wheels)
    2. Generate Action-Reflection transformations for each Wheel

    Does not create nexuses — that's the Analyst's job.
    Does not interact with the user — curates the graph and returns results.
    """

    def __init__(
        self,
        nexus_hash: str,
        perspective_hashes: Optional[list[str]] = None,
    ) -> None:
        self.nexus_hash = nexus_hash
        self.perspective_hashes = perspective_hashes or []

    async def resolve(self) -> ExplorationResult:
        from dialectical_framework.agents.explorer.skills.build_wheels import \
            BuildWheels
        from dialectical_framework.agents.explorer.skills.explore_transformations import \
            ExploreTransformations

        errors: list[StepError] = []
        reports: list = []

        cycle_hashes: list[str] = []
        wheel_hashes: list[str] = []

        try:
            build = BuildWheels(
                nexus_hash=self.nexus_hash,
                perspective_hashes=self.perspective_hashes,
            )
            build_result = await build.resolve()
            reports.append(build.report)

            cycle_hashes = [c.hash for c in build_result.new_cycles if c.hash]
            wheel_hashes = [w.hash for w in build_result.new_wheels if w.hash]
        except Exception as e:
            errors.append(StepError(step="build_wheels", message=str(e)))
            self._report.ok = False
            self._report.summary = f"Wheel building failed: {e}"
            return ExplorationResult(
                nexus_hash=self.nexus_hash,
                errors=errors,
                reports=reports,
            )

        if not wheel_hashes:
            self._report.ok = True
            self._report.summary = f"Built {len(cycle_hashes)} cycles, no new wheels"
            return ExplorationResult(
                nexus_hash=self.nexus_hash,
                cycle_hashes=cycle_hashes,
                errors=errors,
                reports=reports,
            )

        transformation_count = 0

        for wheel_hash in wheel_hashes:
            try:
                explore_tr = ExploreTransformations(wheel_hash=wheel_hash)
                tr_result = await explore_tr.resolve()
                reports.append(explore_tr.report)
                transformation_count += len(tr_result.new)
            except Exception as e:
                errors.append(
                    StepError(
                        step="explore_transformations",
                        message=str(e),
                        hash=wheel_hash,
                    )
                )

        self._report.ok = True
        self._report.summary = (
            f"Exploration complete: {len(cycle_hashes)} cycles, "
            f"{len(wheel_hashes)} wheels, "
            f"{transformation_count} transformations"
        )
        self._report.artifacts["nexus_hash"] = self.nexus_hash
        self._report.artifacts["cycle_hashes"] = cycle_hashes
        self._report.artifacts["wheel_hashes"] = wheel_hashes
        self._report.artifacts["transformation_count"] = transformation_count

        return ExplorationResult(
            nexus_hash=self.nexus_hash,
            cycle_hashes=cycle_hashes,
            wheel_hashes=wheel_hashes,
            transformation_count=transformation_count,
            errors=errors,
            reports=reports,
        )


@llm.tool
async def explore(
    nexus_hash: str = Field(description="Hash of the Nexus to explore within"),
    perspective_hashes: Optional[list[str]] = Field(
        default=None,
        description="Additional perspective hashes to add to Nexus before building",
    ),
) -> str:
    """Run full exploration pipeline within a Nexus: builds structural combinations (Cycles + Wheels) and generates action-reflection transformations. Use when all perspectives are ready and exploration should proceed."""
    pipeline = ExplorationPipeline(
        nexus_hash=nexus_hash, perspective_hashes=perspective_hashes
    )
    await pipeline.resolve()
    return str(pipeline.report)
