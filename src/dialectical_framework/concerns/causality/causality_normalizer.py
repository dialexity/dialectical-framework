"""
CausalityNormalizer: Normalizes probabilities across a group of Cycles or Wheels.

Takes structures that already have estimations and renormalizes their probabilities
so they sum to 1.0. This is useful after adding new structures to an existing layer.

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
from dialectical_framework.graph.nodes.estimation import (
    ProbabilityEstimation,
    RelevanceEstimation,
)
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.utils.decompose_probability_uniformly import (
    decompose_probability_uniformly,
)


class CausalityNormalizer:
    """
    Normalizes probabilities across a group of Cycles or Wheels.

    Uses RelevanceEstimation as the raw score and updates ProbabilityEstimation
    with normalized values that sum to 1.0.

    Requirements:
    - All structures must have RelevanceEstimation (raw AI score)
    - All structures must be same type (all Cycles or all Wheels)
    """

    def normalize(self, structures: list[Union[Cycle, Wheel]]) -> None:
        """
        Normalize probabilities across structures so they sum to 1.0.

        Uses RelevanceEstimation as the raw score for normalization.
        Updates ProbabilityEstimation with normalized values.

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

        # Collect raw scores (RelevanceEstimation)
        scores: dict[str, Decimal] = {}
        for structure in structures:
            relevance = self._get_relevance(structure)
            if relevance is None:
                raise ValueError(
                    f"Structure {structure.short_hash} is missing RelevanceEstimation. "
                    "All structures must have estimations before normalization."
                )
            scores[structure.hash] = Decimal(str(relevance))

        # Normalize
        normalized = self._normalize_scores(scores)

        # Update ProbabilityEstimation on each structure
        estimation_manager = EstimationManager()
        for structure in structures:
            prob_value = float(normalized[structure.hash])
            estimation_manager.upsert_estimation(
                structure, ProbabilityEstimation, prob_value
            )

            # Decompose into transitions for Wheels
            if isinstance(structure, Wheel):
                self._decompose_probability_into_transitions(structure, prob_value)

    def _get_relevance(self, structure: Union[Cycle, Wheel]) -> float | None:
        """Get RelevanceEstimation value from structure."""
        for est, _ in structure.estimations.all():
            if isinstance(est, RelevanceEstimation):
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
            estimation_manager.clear_estimations(trans, [ProbabilityEstimation])

        individual_prob = decompose_probability_uniformly(probability, len(transitions))
        for trans in transitions:
            estimation_manager.upsert_estimation(trans, ProbabilityEstimation, individual_prob)
