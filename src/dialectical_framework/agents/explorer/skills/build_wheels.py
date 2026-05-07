"""
BuildWheels: Main LLM-facing entry point for dialectical exploration.

Takes a Nexus (exploration context with intent and preset) and optional
Perspective hashes, then creates all structural combinations (Cycles + Wheels)
and estimates them.

The Nexus has two separate concerns:
- preset: Selects the estimator class for estimation
  (e.g. "preset:balanced", "preset:realistic", "preset:auto")
- intent: Free-form exploration purpose.

When preset is "preset:auto", the LLM resolves the best assessment strategy
from the intent — either matching a system preset or formulating custom criteria.

Usage:
    agent = BuildWheels(
        nexus_hash="abc123...",
        perspective_hashes=["def456...", "ghi789..."],
    )
    result = await agent.resolve()
    for cycle in result.new_cycles:
        print(f"Cycle: {cycle.short_hash}")
    for wheel in result.new_wheels:
        print(f"Wheel: {wheel.short_hash}")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.protocols.base_tool import BaseTool
from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective


class _AutoPresetResolutionDto(BaseModel):
    """Result of resolving preset:auto — either a matching system preset or custom criteria."""

    preset: Optional[str] = Field(
        default=None,
        description=(
            "System preset if the intent clearly matches one: "
            "'preset:realistic', 'preset:desirable', 'preset:feasible', or 'preset:balanced'. "
            "null if none fit well."
        ),
    )
    criteria: Optional[str] = Field(
        default=None,
        description=(
            "Custom assessment criteria paragraph, only when no system preset fits. "
            "Must be null when preset is set."
        ),
    )


def _auto_preset_prompt(*, exploration_intent: str) -> list:
    return [llm.messages.user(f"""Given the following exploration purpose:
{exploration_intent}

Determine the best assessment strategy for evaluating circular causality sequences
(ordered chains of thesis statements that cycle back to the beginning).

<system_presets>
The following system presets exist. Pick one if it clearly fits the exploration purpose:

- preset:realistic — Evaluates what is most likely to happen in reality.
  Best for: practical analysis, real-world dynamics, predicting outcomes.

- preset:desirable — Evaluates what would be most beneficial or ideal.
  Best for: aspirational goals, ethical reasoning, envisioning best outcomes.

- preset:feasible — Evaluates what is most achievable given constraints.
  Best for: implementation planning, resource-aware analysis, pragmatic paths.

- preset:balanced — Generic balanced assessment with no particular lens.
  Best for: when no specific angle is needed, general-purpose exploration.
</system_presets>

<instructions>
1. If the exploration purpose clearly aligns with one of the system presets above,
   return that preset. Prefer system presets — they are well-tuned.
2. Only if the intent requires a perspective that none of the system presets capture,
   formulate 2-4 concise custom assessment criteria as a single paragraph.
3. Return EITHER a preset OR criteria, never both.
</instructions>""")]


@dataclass
class BuildWheelsResult:
    """Result from BuildWheels."""

    nexus: Optional[Nexus]
    new_cycles: list[Cycle]
    new_wheels: list[Wheel]


class BuildWheels(BaseTool, ReasonableConcern[BuildWheelsResult]):
    """
    Main LLM-facing entry point for dialectical exploration.

    Creates structural combinations (Cycles + Wheels) from Perspectives
    within a Nexus, then estimates them using the appropriate estimator
    based on the Nexus intent.

    Flow:
    1. Resolve Nexus by hash
    2. Add Perspectives to Nexus (idempotent)
    3. Create all Cycle/Wheel combinations (via PerspectiveCombination)
    4. Estimate new structures (via CausalityEstimation)

    Idempotent: re-running with same inputs creates no duplicates.

    Dual interface:
    - resolve() returns BuildWheelsResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    nexus_hash: str = Field(description="Hash of the Nexus to build wheels in")
    perspective_hashes: list[str] = Field(default_factory=list, description="Perspective hashes to add to Nexus before building")

    async def call(self) -> str:
        """Resolve and return ExecutionReport as JSON (for LLM tool use)."""
        await self.resolve()
        return str(self._report)

    async def resolve(self) -> BuildWheelsResult:
        """
        Create structural combinations and estimate them.

        Returns:
            BuildWheelsResult with newly created structures
        """

        # 1. Resolve Nexus
        nexus = self._resolve_nexus()
        if nexus is None:
            self._report.ok = False
            self._report.summary = f"Nexus not found: {self.nexus_hash}"
            return BuildWheelsResult(
                nexus=None,
                new_cycles=[],
                new_wheels=[],
            )

        exploration_intent = nexus.intent
        self._report.artifacts["nexus"] = nexus.short_hash
        if exploration_intent:
            self._report.artifacts["intent"] = exploration_intent

        # 2. Resolve the cycle intent — what gets written to Cycle.intent
        #    For preset:auto, check existing Cycles first (already resolved),
        #    then fall back to LLM resolution.
        #    For explicit presets, pass through as-is.
        if nexus.preset == CausalityPreset.AUTO:
            cycle_intent = self._find_existing_cycle_intent(nexus)
            if cycle_intent is None:
                if exploration_intent:
                    cycle_intent = await self._resolve_auto_preset(
                        exploration_intent
                    )
                else:
                    cycle_intent = CausalityPreset.BALANCED
        else:
            cycle_intent = nexus.preset

        self._report.artifacts["cycle_intent"] = cycle_intent

        # 3. Resolve Perspectives
        perspectives = self._resolve_perspectives()

        if not perspectives:
            self._report.summary = (
                f"No Perspectives to combine in Nexus {nexus.short_hash}"
            )
            return BuildWheelsResult(
                nexus=nexus,
                new_cycles=[],
                new_wheels=[],
            )

        self._report.artifacts["pp_count"] = len(perspectives)

        # 4. Create structural combinations (Cycles + Wheels)
        #    cycle_intent flows onto Cycle.intent — never "preset:auto"
        from dialectical_framework.concerns.perspective_combination import (
            PerspectiveCombination,
        )

        combination = PerspectiveCombination()
        combination_result = combination.resolve(
            nexus=nexus, perspectives=perspectives, preset=cycle_intent
        )
        self._report = self._report.merge(combination.report)

        new_cycles = combination_result.cycles
        new_wheels = combination_result.wheels

        self._report.artifacts["new_cycles"] = len(new_cycles)
        self._report.artifacts["new_wheels"] = len(new_wheels)

        # 5. Estimate new structures (layer 2+ only — single-PP cycles are tautological)
        #    CausalityEstimation resolves the estimator from Cycle.intent
        causal_cycles = [c for c in new_cycles if c.perspective_count >= 2]
        causal_wheels = [w for w in new_wheels if w.polarity_count >= 2]
        if causal_cycles or causal_wheels:
            await self._run_estimation(causal_cycles, causal_wheels)

        # 6. Build summary
        if not new_cycles and not new_wheels:
            self._report.summary = (
                f"All structures already exist for Nexus {nexus.short_hash} "
                f"({len(perspectives)} PPs, intent: {cycle_intent})"
            )
        else:
            self._report.summary = (
                f"Created {len(new_cycles)} cycles, {len(new_wheels)} wheels "
                f"for Nexus {nexus.short_hash} "
                f"(intent: {cycle_intent})"
            )

        return BuildWheelsResult(
            nexus=nexus,
            new_cycles=new_cycles,
            new_wheels=new_wheels,
        )

    async def _run_estimation(
        self,
        cycles: list[Cycle],
        wheels: list[Wheel],
    ) -> None:
        """
        Estimate newly created Cycles and Wheels.

        The estimator is resolved from each structure's intent by CausalityEstimation.
        """
        from dialectical_framework.concerns.causality_estimation import (
            CausalityEstimation,
        )

        if cycles:
            estimation = CausalityEstimation()
            await estimation.resolve(cycles)
            self._report = self._report.merge(estimation.report)

        if wheels:
            estimation = CausalityEstimation()
            await estimation.resolve(wheels)
            self._report = self._report.merge(estimation.report)

    @inject
    def _resolve_nexus(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Optional[Nexus]:
        """Resolve Nexus by hash prefix, scoped by sid."""
        query = """
            MATCH (n:Nexus)
            WHERE n.hash STARTS WITH $nexus_hash AND n.sid = $sid
            RETURN n
        """
        results = list(
            graph_db.execute_and_fetch(
                query, {"nexus_hash": self.nexus_hash, "sid": sid}
            )
        )
        if not results:
            return None
        if len(results) > 1:
            raise ValueError(
                f"Ambiguous nexus hash '{self.nexus_hash}': "
                f"matches {len(results)} nexuses"
            )
        return results[0]["n"]

    @staticmethod
    def _find_existing_cycle_intent(nexus: Nexus) -> Optional[str]:
        """
        Check if this Nexus already has Cycles with a resolved intent.

        When preset:auto was resolved in a previous run, the resolved intent
        is already on existing Cycles. Reuse it to avoid redundant LLM calls.

        Looks at layer 2+ Cycles (2+ PPs) since layer-1 (single PP)
        Cycles are tautological and not estimated.

        Returns:
            The intent from an existing Cycle, or None if no Cycles exist.
        """
        from dialectical_framework.graph.repositories.cycle_repository import (
            CycleRepository,
        )

        pp_pairs = nexus.perspectives.all()
        if len(pp_pairs) < 2:
            return None

        # Check layer-2 Cycles (pairs) scoped to this Nexus
        first_pp, _ = pp_pairs[0]
        second_pp, _ = pp_pairs[1]
        cycle_repo = CycleRepository()
        cycles = cycle_repo.find_by_layer([first_pp, second_pp], nexus=nexus)

        if cycles:
            return cycles[0].intent

        return None

    async def _resolve_auto_preset(
        self,
        exploration_intent: str,
    ) -> str:
        """
        Resolve preset:auto — LLM picks a system preset or formulates custom criteria.

        Returns the resolved intent string for Cycle.intent:
        - A system preset string (e.g. "preset:realistic") if the intent matches one
        - Custom criteria text if no preset fits
        - "preset:balanced" as fallback
        """
        @use_brain(format=_AutoPresetResolutionDto)
        async def _resolve() -> list:
            return _auto_preset_prompt(exploration_intent=exploration_intent)

        result: _AutoPresetResolutionDto = await _resolve()

        if result.preset:
            return result.preset

        if result.criteria:
            return result.criteria

        return CausalityPreset.BALANCED

    def _resolve_perspectives(self) -> list[Perspective]:
        """Resolve Perspectives from hashes or prefixes."""
        from dialectical_framework.graph.nodes.perspective import Perspective

        repo = NodeRepository()
        perspectives = []
        for pp_hash in self.perspective_hashes:
            node = repo.find_by_hash(pp_hash, node_type=Perspective)
            if node is None:
                raise ValueError(f"Perspective not found: {pp_hash}")
            perspectives.append(node)
        return perspectives


@llm.tool
async def build_wheels(nexus_hash: str, perspective_hashes: Optional[list[str]] = None) -> str:
    """Create structural combinations (Cycles + Wheels) from Perspectives within a Nexus and estimate them. Provide Nexus hash and Perspective hashes to combine."""
    concern = BuildWheels(nexus_hash=nexus_hash, perspective_hashes=perspective_hashes or [])
    return await concern.call()
