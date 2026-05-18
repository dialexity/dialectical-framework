"""
Explorer: Autonomous sub-agent for dialectical exploration.

Takes perspectives and autonomously runs the full exploration pipeline:
create nexus → build wheels → explore transformations.

Usage:
    # Programmatic (headless)
    explorer = Explorer(
        perspective_hashes=["abc123", "def456", "ghi789"],
        intent="understand how growth and culture interact",
    )
    result = await explorer.resolve()
    print(result.wheel_hashes)

    # Via orchestrator tool
    @llm.tool explore(perspective_hashes=...) delegates here.
"""

from __future__ import annotations

from typing import Optional

from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.agents.explorer.tools.create_nexus import CreateNexus
from dialectical_framework.agents.explorer.skills.build_wheels import BuildWheels
from dialectical_framework.agents.explorer.skills.explore_transformations import (
    ExploreTransformations,
)
from dialectical_framework.enums.causality_preset import CausalityPreset


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


class Explorer(ReasonableConcern[ExplorationResult]):
    """
    Autonomous explorer sub-agent.

    Runs the full dialectical exploration pipeline:
    1. Create a Nexus grouping the perspectives
    2. Build structural combinations (Cycles + Wheels)
    3. Generate Action-Reflection transformations for each Wheel

    Does not interact with the user — curates the graph and returns results.
    """

    def __init__(
        self,
        perspective_hashes: list[str],
        intent: Optional[str] = None,
        preset: str = CausalityPreset.AUTO,
    ) -> None:
        self.perspective_hashes = perspective_hashes
        self.intent = intent or "explore interactions between perspectives"
        self.preset = preset

    async def resolve(self) -> ExplorationResult:
        errors: list[StepError] = []
        reports: list = []

        if not self.perspective_hashes:
            self._report.ok = False
            self._report.summary = "No perspective hashes provided"
            return ExplorationResult(
                nexus_hash="",
                errors=[StepError(step="create_nexus", message="No perspective hashes provided")],
            )

        # Step 1: Create Nexus
        try:
            create = CreateNexus()
            nexus_result = await create.resolve(
                intent=self.intent,
                perspective_hashes=self.perspective_hashes,
                preset=self.preset,
            )
            reports.append(create.report)
            nexus_hash = nexus_result.nexus.hash
        except Exception as e:
            self._report.ok = False
            self._report.summary = f"Failed to create Nexus: {e}"
            return ExplorationResult(
                nexus_hash="",
                errors=[StepError(step="create_nexus", message=str(e))],
                reports=reports,
            )

        # Step 2: Build Wheels
        cycle_hashes: list[str] = []
        wheel_hashes: list[str] = []

        try:
            build = BuildWheels(
                nexus_hash=nexus_hash,
                perspective_hashes=self.perspective_hashes,
            )
            build_result = await build.resolve()
            reports.append(build.report)

            cycle_hashes = [c.hash for c in build_result.new_cycles if c.hash]
            wheel_hashes = [w.hash for w in build_result.new_wheels if w.hash]
        except Exception as e:
            errors.append(StepError(step="build_wheels", message=str(e)))
            self._report.ok = True
            self._report.summary = f"Nexus created, wheel building failed: {e}"
            return ExplorationResult(
                nexus_hash=nexus_hash,
                errors=errors,
                reports=reports,
            )

        if not wheel_hashes:
            self._report.ok = True
            self._report.summary = f"Nexus created with {len(cycle_hashes)} cycles, no wheels generated"
            return ExplorationResult(
                nexus_hash=nexus_hash,
                cycle_hashes=cycle_hashes,
                errors=errors,
                reports=reports,
            )

        # Step 3: Explore transformations for each wheel
        transformation_count = 0

        for wheel_hash in wheel_hashes:
            try:
                explore = ExploreTransformations(wheel_hash=wheel_hash)
                tr_result = await explore.resolve()
                reports.append(explore.report)
                transformation_count += len(tr_result.new)
            except Exception as e:
                errors.append(StepError(
                    step="explore_transformations",
                    message=str(e),
                    hash=wheel_hash,
                ))

        # Final report
        self._report.ok = True
        self._report.summary = (
            f"Exploration complete: {len(cycle_hashes)} cycles, "
            f"{len(wheel_hashes)} wheels, "
            f"{transformation_count} transformations"
        )
        self._report.artifacts["nexus_hash"] = nexus_hash
        self._report.artifacts["cycle_hashes"] = cycle_hashes
        self._report.artifacts["wheel_hashes"] = wheel_hashes
        self._report.artifacts["transformation_count"] = transformation_count

        return ExplorationResult(
            nexus_hash=nexus_hash,
            cycle_hashes=cycle_hashes,
            wheel_hashes=wheel_hashes,
            transformation_count=transformation_count,
            errors=errors,
            reports=reports,
        )


@llm.tool
async def explore(
    perspective_hashes: list[str] = Field(description="Hashes of Perspectives to explore"),
    intent: Optional[str] = Field(default=None, description="What to navigate or understand (e.g., 'understand how growth and culture interact')"),
    preset: str = Field(default="preset:auto", description="Estimation strategy: 'preset:auto', 'preset:balanced', 'preset:realistic', 'preset:desirable', 'preset:feasible'"),
) -> str:
    """Run full dialectical exploration: groups perspectives into a Nexus, builds structural combinations (Cycles + Wheels), and generates action-reflection transformations for each Wheel. Use when the user wants to understand how perspectives interact or find pathways."""
    agent = Explorer(perspective_hashes=perspective_hashes, intent=intent, preset=preset)
    await agent.resolve()
    return str(agent.report)
