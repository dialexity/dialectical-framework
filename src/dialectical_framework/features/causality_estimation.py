"""
CausalityEstimation: Feature for estimating causality on Cycles and Wheels.

This is the "smart" orchestrator that:
- Groups structures by type and size for parallel estimation
- Decides what to estimate: if the requested group matches what's in the DB,
  re-estimates everything; if DB has more, only estimates what was requested
- Normalizes probabilities across ALL structures of same type+size in the DB

Usage:
    from dialectical_framework.features.causality_estimation import CausalityEstimation

    feature = CausalityEstimation()

    # Estimate structures (automatically grouped by type and size)
    result = await feature.execute([cycle1, cycle2, cycle3])
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Union

from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.features.causality.causality_normalizer import (
    CausalityNormalizer,
)
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.estimation import RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.cycle_repository import CycleRepository
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    from dialectical_framework.features.causality.causality_sequencer import (
        CausalitySequencer,
        EstimationStructured,
    )


@dataclass
class EstimationResult:
    """Result from CausalityEstimation."""

    estimated: list[Union[Cycle, Wheel]] = field(default_factory=list)


class CausalityEstimation(ExecutableCapability[EstimationResult], SettingsAware):
    """
    Feature for estimating causality on Cycles and Wheels.

    This is the "smart" orchestrator that:
    - Groups structures by type (Cycle/Wheel) and size (Perspective count)
    - Runs estimation in parallel for each group
    - Persists Rationale + RelevanceEstimation nodes
    - Normalizes probabilities (ProbabilityEstimation) across ALL structures
      of same type+size in the DB

    Estimation logic per group:
    - If the requested group IS the full set in the DB → re-estimate all
    - If the DB has more structures → only estimate the ones requested
    - Either way, normalization covers everything in the DB
    """

    def __init__(self) -> None:
        self._report: ExecutionReport

    @property
    def report(self) -> ExecutionReport:
        """Access the execution report."""
        return self._report

    async def execute(
        self,
        structures: list[Union[Cycle, Wheel]],
    ) -> EstimationResult:
        """
        Estimate causality for Cycles and/or Wheels.

        Resolves the sequencer from the structures' intent (all structures
        in one call share the same intent from their Nexus origin).
        Groups by type and size, then estimates in parallel.

        Args:
            structures: Cycles and/or Wheels to estimate

        Returns:
            EstimationResult with list of estimated structures
        """
        from dialectical_framework.features.causality.sequencer_resolver import (
            resolve_sequencer,
        )

        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not structures:
            self._report.summary = "No structures provided"
            return EstimationResult()

        # Resolve sequencer from intent (shared across all structures)
        ref = structures[0]
        intent = ref.get_effective_intent() if isinstance(ref, Wheel) else ref.intent
        sequencer = resolve_sequencer(intent)

        result = EstimationResult()

        # Group by type and size
        groups = self._group_by_type_and_size(structures)

        self._report.artifacts["input_count"] = len(structures)
        self._report.artifacts["groups"] = len(groups)

        # Run estimation in parallel for each group
        tasks = []
        for key, group in groups.items():
            tasks.append(self._estimate_group(key, group, sequencer))

        group_results = await asyncio.gather(*tasks)

        # Collect results
        for estimated_structures in group_results:
            result.estimated.extend(estimated_structures)

        self._report.artifacts["estimated_count"] = len(result.estimated)
        self._report.summary = f"Estimated {len(result.estimated)} structures"

        return result

    def _group_by_type_and_size(
        self, structures: list[Union[Cycle, Wheel]]
    ) -> dict[tuple[str, int], list[Union[Cycle, Wheel]]]:
        """
        Group structures by type and size.

        Returns dict with key (type_name, size) -> list of structures.
        """
        groups: dict[tuple[str, int], list[Union[Cycle, Wheel]]] = {}

        for structure in structures:
            if isinstance(structure, Cycle):
                type_name = "Cycle"
                size = structure.perspective_count
            else:
                type_name = "Wheel"
                size = structure.polarity_count

            key = (type_name, size)
            if key not in groups:
                groups[key] = []
            groups[key].append(structure)

        return groups

    async def _estimate_group(
        self,
        key: tuple[str, int],
        requested: list[Union[Cycle, Wheel]],
        sequencer: CausalitySequencer,
    ) -> list[Union[Cycle, Wheel]]:
        """
        Estimate a group of same-type, same-size structures.

        Logic:
        - Find all structures of same type+size in DB
        - If requested set IS the full DB set → estimate all (forced re-estimation)
        - If DB has more → only estimate the requested ones
        - Normalize probabilities across all DB structures

        Returns list of structures that were estimated.
        """
        # Find all structures of same type+size in DB
        all_in_db = self._find_all_in_layer(requested)
        requested_hashes = {s.hash for s in requested}
        db_hashes = {s.hash for s in all_in_db}

        # Determine what to estimate
        if requested_hashes == db_hashes:
            # Requested set IS the full DB set → estimate all
            to_estimate = requested
        else:
            # DB has more → only estimate what was requested
            to_estimate = requested

        # Run AI estimation (returns raw, non-normalized results)
        raw_estimations = await sequencer.estimate(to_estimate)

        if not raw_estimations:
            return []

        # Persist RelevanceEstimation + Rationale for estimated structures
        self._persist_estimations(to_estimate, raw_estimations)

        # Normalize probabilities across ALL structures in DB for this layer
        # (includes both newly estimated and previously estimated)
        self._normalize_layer(all_in_db)

        return to_estimate

    def _find_all_in_layer(
        self, structures: list[Union[Cycle, Wheel]]
    ) -> list[Union[Cycle, Wheel]]:
        """
        Find all structures of same type and size in the DB.
        """
        if not structures:
            return []

        ref = structures[0]

        if isinstance(ref, Cycle):
            perspectives = ref.perspectives
            cycle_repo = CycleRepository()
            return cycle_repo.find_by_layer(perspectives)

        # Wheel: find all wheels with same PP set via their parent Cycles
        from dialectical_framework.graph.repositories.wheel_repository import (
            WheelRepository,
        )

        perspectives = ref._perspectives
        wheel_repo = WheelRepository()
        return wheel_repo.find_by_layer(perspectives)

    def _normalize_layer(self, all_structures: list[Union[Cycle, Wheel]]) -> None:
        """
        Normalize probabilities across all structures in a layer.

        Only normalizes structures that have RelevanceEstimation.
        Structures without estimation are skipped (not an error here,
        unlike CausalityNormalizer which raises).
        """
        # Filter to only structures with RelevanceEstimation
        with_estimation = [
            s for s in all_structures if self._has_estimation(s)
        ]

        if not with_estimation:
            return

        normalizer = CausalityNormalizer()
        normalizer.normalize(with_estimation)

    def _has_estimation(self, structure: Union[Cycle, Wheel]) -> bool:
        """Check if a structure has a RelevanceEstimation."""
        for est, _ in structure.estimations.all():
            if isinstance(est, RelevanceEstimation):
                return True
        return False

    def _persist_estimations(
        self,
        structures: list[Union[Cycle, Wheel]],
        raw_estimations: dict[str, EstimationStructured],
    ) -> None:
        """
        Persist raw estimations to the database.

        Creates Rationale + RelevanceEstimation for each structure.
        """
        estimation_manager = EstimationManager()

        for structure in structures:
            if structure.hash not in raw_estimations:
                continue

            est = raw_estimations[structure.hash]

            # Create Rationale
            rationale = Rationale(
                text=est.reasoning,
                summary=est.argumentation,
            )
            rationale.set_explanation_target(structure)
            rationale.commit()

            # Store raw AI score as RelevanceEstimation
            estimation_manager.upsert_estimation(
                structure, RelevanceEstimation, est.probability, provider=rationale
            )
