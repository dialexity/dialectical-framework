"""
Explorer: Conversational agent for dialectical exploration.

Scoped to a Case + Nexus (sid + nexus_hash). Helps users navigate
transformations and understand the synthetic wisdom (Ac+, Re+, S+).

Also contains ExplorationPipeline — the headless pipeline for programmatic use.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, AsyncGenerator, Optional

from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.agent_context import agent_scope
from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.explorer.system_prompts import system_prompt
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.app_spec import AppSpec, resolve_app_layer
from dialectical_framework.agents.stream_events import StreamEvent
from dialectical_framework.agents.toolsets import merge_app_tools
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

    AGENT_NAME = "explorer"

    def __init__(
        self,
        nexus_hash: str,
        app_preamble: Optional[str] = None,
        messages: Optional[list] = None,
        app_tools: Optional[list] = None,
        app: Optional[AppSpec] = None,
    ) -> None:
        self._nexus_hash = nexus_hash
        # app: declarative app definition (Navigator base + voicing +
        # tool_guide + tools) — see AppSpec. Pass the SAME AppSpec to every
        # head (Analyst, Explorer, Advisor): the Explorer<->Advisor toggle
        # shares literal history (a missing tool breaks capability
        # mid-conversation), and the Analyst thread owes the user the same
        # domain resources by parity. For advanced-mode preambles compose
        # manually: app_preamble=my_app.navigator_preamble(advanced=True).
        app_preamble, app_tools = resolve_app_layer(
            app, app_preamble, app_tools, preamble_for="navigator"
        )
        self._tools = merge_app_tools(_build_tools(), app_tools)
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
        parts.append(system_prompt(nexus_hash=nexus_hash, nexus_intent=nexus_intent))
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

    @property
    def nexus_hash(self) -> str:
        return self._nexus_hash


def _build_tools() -> list:
    from dialectical_framework.agents.explorer.skills.build_wheels import \
        build_wheels
    from dialectical_framework.agents.explorer.skills.explore_transformations import \
        explore_transformations
    from dialectical_framework.agents.explorer.tools.expand_nexus import \
        expand_nexus
    from dialectical_framework.agents.explorer.tools.generate_synthesis import \
        generate_synthesis
    from dialectical_framework.agents.explorer.tools.present_exploration import \
        present_exploration
    from dialectical_framework.agents.orchestrator.tools.create_dx_input import \
        create_dx_input
    from dialectical_framework.agents.orchestrator.tools.digest_input import \
        digest_input
    from dialectical_framework.agents.orchestrator.tools.get_schema import \
        get_schema
    from dialectical_framework.agents.orchestrator.tools.inspect_node import \
        inspect_node
    from dialectical_framework.agents.orchestrator.tools.query_graph import \
        query_graph
    from dialectical_framework.agents.orchestrator.tools.read_digest import \
        read_digest
    from dialectical_framework.agents.orchestrator.tools.read_input import \
        read_input

    return [
        build_wheels,
        explore_transformations,
        generate_synthesis,
        expand_nexus,
        create_dx_input,
        present_exploration,
        digest_input,
        read_digest,
        read_input,
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
    # Wheels that got transformations this run (== wheel_hashes unless the
    # pipeline was capped via max_deep_wheels). Synthesis should follow these.
    deepened_wheel_hashes: list[str] = []
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

    `max_deep_wheels` caps step 2: ALL wheels are still built and estimated
    (structural, cheap), but only the top-plausibility wheels — deepest layer
    first, then highest causality P — get transformations. The rest stay
    shallow, available for deepening on demand. None (default) deepens every
    wheel (the Explorer agent's path, where the user selects wheels, is
    already lazy and never sets this).

    Does not create nexuses — that's the Analyst's job.
    Does not interact with the user — curates the graph and returns results.
    """

    def __init__(
        self,
        nexus_hash: str,
        perspective_hashes: Optional[list[str]] = None,
        max_deep_wheels: Optional[int] = None,
    ) -> None:
        self.nexus_hash = nexus_hash
        self.perspective_hashes = perspective_hashes or []
        self.max_deep_wheels = max_deep_wheels

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

        deep_wheel_hashes = self._select_deep_wheels(build_result.new_wheels)

        transformation_count = 0

        async def _explore_wheel(wheel_hash: str) -> tuple[int, Optional[StepError]]:
            try:
                explore_tr = ExploreTransformations(wheel_hash=wheel_hash)
                tr_result = await explore_tr.resolve()
                reports.append(explore_tr.report)
                return len(tr_result.new), None
            except Exception as e:
                return 0, StepError(
                    step="explore_transformations",
                    message=str(e),
                    hash=wheel_hash,
                )

        wheel_results = await asyncio.gather(
            *[_explore_wheel(wh) for wh in deep_wheel_hashes]
        )
        for count, error in wheel_results:
            transformation_count += count
            if error:
                errors.append(error)

        shallow_count = len(wheel_hashes) - len(deep_wheel_hashes)
        self._report.ok = True
        self._report.summary = (
            f"Exploration complete: {len(cycle_hashes)} cycles, "
            f"{len(wheel_hashes)} wheels, "
            f"{transformation_count} transformations"
            + (
                f" (deepened top {len(deep_wheel_hashes)} wheel(s) by "
                f"plausibility; {shallow_count} built but not deepened)"
                if shallow_count
                else ""
            )
        )
        self._report.artifacts["nexus_hash"] = self.nexus_hash
        self._report.artifacts["cycle_hashes"] = cycle_hashes
        self._report.artifacts["wheel_hashes"] = wheel_hashes
        self._report.artifacts["deepened_wheel_hashes"] = deep_wheel_hashes
        self._report.artifacts["transformation_count"] = transformation_count

        return ExplorationResult(
            nexus_hash=self.nexus_hash,
            cycle_hashes=cycle_hashes,
            wheel_hashes=wheel_hashes,
            deepened_wheel_hashes=deep_wheel_hashes,
            transformation_count=transformation_count,
            errors=errors,
            reports=reports,
        )

    def _select_deep_wheels(self, wheels: list) -> list[str]:
        """
        Pick which wheels get transformations this run.

        No cap → all of them. With a cap: rank by layer (perspective count,
        deepest first — richer causal chains) then by raw causality P within
        the layer (raw is comparable among siblings; normalization shares the
        denominator). Wheels without an estimation (e.g. 1-PP) rank last
        within their layer.
        """
        hashes = [w.hash for w in wheels if w.hash]
        if self.max_deep_wheels is None or self.max_deep_wheels >= len(hashes):
            return hashes
        if self.max_deep_wheels <= 0:
            return []

        from dialectical_framework.graph.nodes.estimation import \
            CausalityProbabilityEstimation

        def _probability(wheel) -> float:
            for est, _ in wheel.estimations.all():
                if isinstance(est, CausalityProbabilityEstimation):
                    return est.value if est.value is not None else -1.0
            return -1.0

        def _layer(wheel) -> int:
            try:
                return wheel.polarity_count
            except ValueError:
                return 0

        ranked = sorted(
            (w for w in wheels if w.hash),
            key=lambda w: (_layer(w), _probability(w)),
            reverse=True,
        )
        return [w.hash for w in ranked[: self.max_deep_wheels]]


@llm.tool
async def explore(
    nexus_hash: Annotated[
        str, Field(description="Hash of the Nexus to explore within")
    ],
    perspective_hashes: Annotated[
        list[str] | None,
        Field(
            description="Additional perspective hashes to add to Nexus before building"
        ),
    ] = None,
) -> str:
    """Run full exploration pipeline within a Nexus: builds structural combinations (Cycles + Wheels) and generates action-reflection transformations. Use when all perspectives are ready and exploration should proceed."""
    pipeline = ExplorationPipeline(
        nexus_hash=nexus_hash, perspective_hashes=perspective_hashes
    )
    await pipeline.resolve()
    return str(pipeline.report)
