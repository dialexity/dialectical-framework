"""
CausalityNormalizer: Normalizes probabilities across a group of Cycles or Wheels.

Takes structures that already have CausalityProbabilityEstimation (raw AI scores)
and normalizes into per-transition probabilities that sum to 1.0.

Usage:
    from dialectical_framework.concerns.causality.causality_normalizer import CausalityNormalizer

    normalizer = CausalityNormalizer()

    # Normalize a group of Cycles (must all have estimations)
    normalizer.normalize(cycles)

    # Normalize Wheels
    normalizer.normalize(wheels)
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, getcontext
from typing import Union

from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.estimation import CausalityProbabilityEstimation
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.utils.decompose_probability_uniformly import (
    decompose_probability_uniformly,
)


class CausalityNormalizer:
    """
    Normalizes causality probabilities across a group of Cycles or Wheels.

    Reads CausalityProbabilityEstimation from structures (raw AI scores),
    normalizes to sum to 1.0, and decomposes into per-transition probabilities.

    Requirements:
    - All structures must have CausalityProbabilityEstimation (raw AI score)
    - All structures must be same type (all Cycles or all Wheels)
    """

    def normalize(self, structures: list[Union[Cycle, Wheel]]) -> None:
        """
        Normalize probabilities across structures and decompose into transitions.

        Reads raw CausalityProbabilityEstimation from structures, normalizes,
        then writes normalized probabilities on individual Transitions.

        Args:
            structures: List of Cycles or Wheels (must all have estimations)

        Raises:
            ValueError: If structures is empty, mixed types, or missing estimations
        """
        if not structures:
            raise ValueError("No structures provided for normalization")

        # Validate all same type
        first_type = type(structures[0])
        if not all(type(s) == first_type for s in structures):
            raise ValueError(
                "All structures must be same type (all Cycles or all Wheels)"
            )

        # Collect raw scores (CausalityProbabilityEstimation on structures)
        scores: dict[str, Decimal] = {}
        for structure in structures:
            raw_score = self._get_raw_score(structure)
            if raw_score is None:
                raise ValueError(
                    f"Structure {structure.short_hash} is missing CausalityProbabilityEstimation. "
                    "All structures must have estimations before normalization."
                )
            scores[structure.hash] = Decimal(str(raw_score))

        # Normalize
        normalized = self._normalize_scores(scores)

        # Decompose into transitions for Wheels
        for structure in structures:
            if isinstance(structure, Wheel):
                prob_value = float(normalized[structure.hash])
                self._decompose_probability_into_transitions(structure, prob_value)

    def _get_raw_score(self, structure: Union[Cycle, Wheel]) -> float | None:
        """Get CausalityProbabilityEstimation value from structure."""
        for est, _ in structure.estimations.all():
            if isinstance(est, CausalityProbabilityEstimation):
                return est.value
        return None

    def _normalize_scores(self, scores: dict[str, Decimal]) -> dict[str, Decimal]:
        """
        Normalize scores to sum to 1.0.

        Returns dict mapping hash to normalized probability (quantized to 3 decimals).
        """
        getcontext().prec = 28
        q = Decimal("0.001")

        total = sum(scores.values())
        if total > 0:
            normalized = {h: score / total for h, score in scores.items()}
        else:
            uniform = Decimal("1") / Decimal(str(len(scores))) if scores else Decimal("0")
            normalized = {h: uniform for h in scores}

        # Quantize and adjust remainder
        sorted_hashes = sorted(normalized.keys(), key=lambda h: normalized[h], reverse=True)
        quantized: dict[str, Decimal] = {
            h: normalized[h].quantize(q, rounding=ROUND_HALF_UP) for h in sorted_hashes
        }

        if quantized:
            remainder = Decimal("1.000") - sum(quantized.values())
            first_hash = sorted_hashes[0]
            quantized[first_hash] = (quantized[first_hash] + remainder).quantize(
                q, rounding=ROUND_HALF_UP
            )

        return quantized

    def _decompose_probability_into_transitions(
        self, wheel: Wheel, probability: float
    ) -> None:
        """Decompose wheel probability into individual transition probabilities."""
        estimation_manager = EstimationManager()

        transitions = wheel.edges
        if not transitions:
            return

        # Clear existing and set uniform
        for trans in transitions:
            estimation_manager.clear_estimations(trans, [CausalityProbabilityEstimation])

        individual_prob = decompose_probability_uniformly(probability, len(transitions))
        for trans in transitions:
            estimation_manager.upsert_estimation(trans, CausalityProbabilityEstimation, individual_prob)
