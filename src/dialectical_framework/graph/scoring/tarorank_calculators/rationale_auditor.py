"""
Implements audit-wins semantics for rationale hierarchies.

Audit-wins logic:
- Rationales can have child rationales (critiques)
- Critiques override parent rationale values
- Deepest level critiques win (recursive)
- Multiple critiques at same level aggregate via GM (simplified, no rating)
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.rationale import Rationale
    from dialectical_framework.graph.scoring.tarorank import TaroRank


class RationaleAuditor:
    """
    Implements audit-wins semantics for rationale hierarchies.

    Audit-wins logic:
    - Rationales can have child rationales (critiques)
    - Critiques override parent rationale values
    - Deepest level critiques win (recursive)
    - Multiple critiques at same level aggregate via GM

    Example:
        Rationale(R=0.9, P=0.8)
        └─ Critique(R=0.5, P=0.6)
            └─ Deeper Critique(R=0.3, P=0.4)

        Result: Use deepest critique (R=0.3, P=0.4)
    """

    def __init__(self, scorer: TaroRank):
        """
        Initialize auditor with scorer reference.

        Args:
            scorer: TaroRank instance
        """
        self.scorer = scorer

    def get_probability(self, rationale: Rationale) -> Optional[float]:
        """
        Get probability from rationale using audit-wins semantics.

        Args:
            rationale: Rationale node to evaluate

        Returns:
            P value or None if no probability evidence
        """
        return self._get_value(rationale, 'probability')

    def get_relevance(self, rationale: Rationale) -> Optional[float]:
        """
        Get relevance from rationale using audit-wins semantics.

        Args:
            rationale: Rationale node to evaluate

        Returns:
            R value or None if no relevance evidence
        """
        return self._get_value(rationale, 'relevance')

    def _get_value(self, rationale: Rationale, attribute: str) -> Optional[float]:
        """
        Get P or R value from rationale hierarchy.

        Uses MANUAL estimations only (not calculated) to avoid circular dependencies.

        Args:
            rationale: Rationale node to evaluate
            attribute: 'probability' or 'relevance'

        Returns:
            Value from deepest critiques or rationale itself
        """
        # Get child rationales (critiques)
        critiques = [crit for crit, _ in rationale.rationales.all()]

        if not critiques:
            # No critiques: return own MANUAL value
            return self._get_manual_value(rationale, attribute)

        # Has critiques: recursively get deepest values
        deepest_values = self._get_deepest_critiques(rationale, attribute)

        if not deepest_values:
            # Critiques exist but provide no values: return own MANUAL value
            return self._get_manual_value(rationale, attribute)

        # Aggregate deepest critique values via GM
        return self._aggregate_critiques(deepest_values)

    def _get_deepest_critiques(
        self,
        rationale: Rationale,
        attribute: str
    ) -> list[float]:
        """
        Recursively find deepest critique values.

        Uses MANUAL estimations only (not calculated) to avoid circular dependencies.

        Args:
            rationale: Rationale to search
            attribute: 'probability' or 'relevance'

        Returns:
            List of values from deepest level
        """
        critiques = [crit for crit, _ in rationale.rationales.all()]

        if not critiques:
            return []

        # Check if any critique has its own critiques (go deeper)
        has_deeper = False
        all_deeper_values = []

        for critique in critiques:
            deeper = self._get_deepest_critiques(critique, attribute)
            if deeper:
                has_deeper = True
                all_deeper_values.extend(deeper)

        if has_deeper:
            # Return values from deeper level
            return all_deeper_values

        # This is the deepest level: return MANUAL critique values
        result = []
        for critique in critiques:
            value = self._get_manual_value(critique, attribute)
            if value is not None:
                result.append(value)

        return result

    def _get_manual_value(self, rationale: Rationale, attribute: str) -> Optional[float]:
        """
        Get MANUAL estimation value from rationale (not calculated).

        This matches legacy behavior where calculators read manual_* fields
        (not self.* properties which include calculated values).

        Args:
            rationale: Rationale to get value from
            attribute: 'probability' or 'relevance'

        Returns:
            GM of manual estimations or None
        """
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            RelevanceEstimation
        )

        if attribute == 'probability':
            estimation_type = ProbabilityEstimation
        else:
            estimation_type = RelevanceEstimation

        # Get only manual estimations (not calculated)
        estimations = rationale.estimations.all()
        manual_estimations = [
            est for est, _ in estimations
            if isinstance(est, estimation_type)
        ]

        if not manual_estimations:
            return None

        # If multiple manual estimations, aggregate via GM
        if len(manual_estimations) == 1:
            return manual_estimations[0].value

        values = [est.value for est in manual_estimations]
        return gm_with_zeros_and_nones_handled(values)

    def _aggregate_critiques(self, values: list[float]) -> Optional[float]:
        """
        Aggregate critique values using geometric mean.

        Simplified implementation: no rating/confidence weighting.

        Args:
            values: List of values to aggregate

        Returns:
            Aggregated value or None
        """
        if not values:
            return None

        # Use geometric mean for critique aggregation
        return gm_with_zeros_and_nones_handled(values)
