"""
CausalityAgent: Subagent for creating causal cycles from a Nexus.

Takes a Nexus hash and intent, then creates Cycles and Wheels representing
different causal arrangements of the WisdomUnits. Optionally attaches AI
estimations for probability assessment.

Intents:
- "preset:balanced" - Equal consideration of all factors
- "preset:desirable" - Focus on optimal outcomes
- "preset:feasible" - Focus on implementation feasibility
- "preset:realistic" - Focus on realistic occurrence

Usage:
    # Programmatic use
    agent = CausalityAgent(
        nexus_hash="abc123...",
        intent="preset:balanced",
        estimate=True,
    )
    result = await agent.execute()
    for cycle in result.cycles:
        print(f"Cycle: {cycle.short_hash}")
        for wheel, _ in cycle.wheels.all():
            print(f"  Wheel: {wheel.short_hash}")

    # LLM tool use
    agent = CausalityAgent(nexus_hash="abc123...")
    json_result = await agent.call()  # Returns JSON string
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.synthesist.causality.causality_sequencer_balanced import (
    CausalitySequencerBalanced,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.protocols.causality_sequencer import CausalitySequencer


@dataclass
class CausalityAgentResult:
    """Result from the CausalityAgent."""

    nexus: Nexus
    cycles: list[Cycle]
    wheels: list[Wheel]
    estimated: bool


class CausalityAgent(BaseTool, ExecutableCapability[CausalityAgentResult]):
    """
    Subagent for creating causal cycles from a Nexus.

    This agent orchestrates the full causality sequencing pipeline:
    1. Resolves Nexus from hash
    2. Arranges WisdomUnits into Cycles and Wheels using the specified intent
    3. Optionally estimates probabilities using AI

    Multiple intents can be applied to the same Nexus by running the agent
    multiple times with different intent values.

    Dual interface:
    - execute() returns CausalityAgentResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    nexus_hash: str = Field(
        description="Hash (full or prefix) of the Nexus to arrange into causal cycles"
    )
    intent: str = Field(
        default="preset:balanced",
        description="Causality intent: 'preset:balanced', 'preset:desirable', 'preset:feasible', or 'preset:realistic'"
    )
    estimate: bool = Field(
        default=True,
        description="If True, attach AI-generated probability estimations to cycles and wheels"
    )

    _report: ExecutionReport = PrivateAttr()

    async def call(self) -> str:
        """Execute causality sequencing and return ExecutionReport as JSON (for LLM tool use)."""
        await self.execute()
        return str(self._report)

    async def execute(self) -> CausalityAgentResult:
        """
        Execute the causality sequencing pipeline.

        Returns:
            CausalityAgentResult with cycles, wheels, and estimation status
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # 1. Resolve Nexus
        nexus = self._resolve_nexus()
        self._report.artifacts["nexus_hash"] = nexus.short_hash

        # 2. Arrange into Cycles and Wheels
        sequencer = self._get_sequencer()
        cycles = sequencer.arrange(nexus, intent=self.intent)

        # Collect all wheels
        wheels: list[Wheel] = []
        for cycle in cycles:
            self._report.node_created(cycle, meta={"intent": self.intent})
            for wheel, _ in cycle.wheels.all():
                wheels.append(wheel)
                self._report.node_created(wheel)

        self._report.artifacts["cycle_count"] = len(cycles)
        self._report.artifacts["wheel_count"] = len(wheels)
        self._report.artifacts["intent"] = self.intent

        # 3. Optionally estimate probabilities
        estimated = False
        if self.estimate and wheels:
            await sequencer.estimate(wheels)
            estimated = True
            self._report.artifacts["estimated"] = True

        # Summary
        self._report.summary = (
            f"Created {len(cycles)} cycle(s) and {len(wheels)} wheel(s) "
            f"for Nexus {nexus.short_hash} with intent '{self.intent}'"
            + (" (estimated)" if estimated else "")
        )

        return CausalityAgentResult(
            nexus=nexus,
            cycles=cycles,
            wheels=wheels,
            estimated=estimated,
        )

    def _resolve_nexus(self) -> Nexus:
        """Resolve Nexus from hash or prefix."""
        from dialectical_framework.graph.nodes.nexus import Nexus

        repo = NodeRepository()
        node = repo.find_by_hash(self.nexus_hash, node_type=Nexus)
        if node is None:
            raise ValueError(f"Nexus not found: {self.nexus_hash}")
        return node

    @inject
    def _get_sequencer(
        self,
        causality_sequencer: CausalitySequencer = Provide[DI.causality_sequencer],
    ) -> CausalitySequencerBalanced:
        """Get the causality sequencer from DI."""
        return causality_sequencer
