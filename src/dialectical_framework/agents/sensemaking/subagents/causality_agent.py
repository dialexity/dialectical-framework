"""
CausalityAgent: Subagent for creating causal cycles from WisdomUnits.

Takes WisdomUnit hashes and intent, then creates Cycles and Wheels representing
different causal arrangements. Optionally attaches AI estimations for probability
assessment.

Intents:
- "preset:balanced" - Equal consideration of all factors
- "preset:desirable" - Focus on optimal outcomes
- "preset:feasible" - Focus on implementation feasibility
- "preset:realistic" - Focus on realistic occurrence

Usage:
    # Programmatic use
    agent = CausalityAgent(
        wisdom_unit_hashes=["abc123...", "def456..."],
        intent="preset:balanced",
        estimate=True,
    )
    result = await agent.execute()
    for cycle in result.cycles:
        print(f"Cycle: {cycle.short_hash}")
        for wheel, _ in cycle.wheels.all():
            print(f"  Wheel: {wheel.short_hash}")

    # LLM tool use
    agent = CausalityAgent(wisdom_unit_hashes=["abc123...", "def456..."])
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

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.protocols.causality_sequencer import CausalitySequencer


@dataclass
class CausalityAgentResult:
    """Result from the CausalityAgent."""

    wisdom_units: list[WisdomUnit]
    cycles: list[Cycle]
    wheels: list[Wheel]
    estimated: bool


class CausalityAgent(BaseTool, ExecutableCapability[CausalityAgentResult]):
    """
    Subagent for creating causal cycles from WisdomUnits.

    This agent orchestrates the full causality sequencing pipeline:
    1. Resolves WisdomUnits from hashes
    2. Arranges WisdomUnits into Cycles and Wheels using the specified intent
    3. Optionally estimates probabilities using AI

    Multiple intents can be applied to the same WisdomUnits by running the agent
    multiple times with different intent values.

    Dual interface:
    - execute() returns CausalityAgentResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    wisdom_unit_hashes: list[str] = Field(
        description="List of WisdomUnit hashes (full or prefix) to arrange into causal cycles"
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

        # 1. Resolve WisdomUnits
        wisdom_units = self._resolve_wisdom_units()
        self._report.artifacts["wisdom_unit_count"] = len(wisdom_units)
        self._report.artifacts["wisdom_unit_hashes"] = [wu.short_hash for wu in wisdom_units]

        # 2. Arrange into Cycles and Wheels
        sequencer = self._get_sequencer()
        cycles = sequencer.arrange(wisdom_units, intent=self.intent)

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
            f"from {len(wisdom_units)} WisdomUnit(s) with intent '{self.intent}'"
            + (" (estimated)" if estimated else "")
        )

        return CausalityAgentResult(
            wisdom_units=wisdom_units,
            cycles=cycles,
            wheels=wheels,
            estimated=estimated,
        )

    def _resolve_wisdom_units(self) -> list[WisdomUnit]:
        """Resolve WisdomUnits from hashes or prefixes."""
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit

        repo = NodeRepository()
        wisdom_units = []
        for wu_hash in self.wisdom_unit_hashes:
            node = repo.find_by_hash(wu_hash, node_type=WisdomUnit)
            if node is None:
                raise ValueError(f"WisdomUnit not found: {wu_hash}")
            wisdom_units.append(node)
        return wisdom_units

    @inject
    def _get_sequencer(
        self,
        causality_sequencer: CausalitySequencer = Provide[DI.causality_sequencer],
    ) -> CausalitySequencer:
        """Get the causality sequencer from DI."""
        return causality_sequencer
