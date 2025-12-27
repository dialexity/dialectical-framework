"""
Calculator for Transition nodes.

Transitions are leaf nodes for both P and R hierarchies.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition


class TransitionCalculator(BaseCalculator):
    """
    Calculator for Transition nodes.

    Transitions are leaf nodes for both P and R hierarchies.

    P calculation:
    - Manual: default_transition_probability field (if set)
    - Fallback: scorer.default_transition_probability
    - Rationales: aggregate rationale probabilities
    - If no values and no default: return None (no free lunch)

    R calculation:
    - Same as components: own R + rationale Rs
    - Do NOT inherit R from source/target components
    - Hard veto: R=0 → return 0
    """

    def calculate_probability(self, transition: Transition) -> Optional[float]:
        """
        Calculate P for a Transition.

        Algorithm:
        1. Check MANUAL ProbabilityEstimation nodes (NOT calculated!)
        2. Collect rationale probabilities
        3. Aggregate via GM
        4. Fallback to scorer.default_transition_probability if no values

        Args:
            transition: Transition to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence and no default
        """
        from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Manual probability from ProbabilityEstimation nodes ONLY (not calculated)
        # This matches legacy: reads manual_probability (not self.probability)
        manual_estimations = self._get_manual_estimations(transition, ProbabilityEstimation)
        for est in manual_estimations:
            values.append(est.value)

        # Rationale probabilities
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in transition.rationales.all()]

        for rationale in rationales:
            rat_p = auditor.get_probability(rationale)
            if rat_p is not None:
                values.append(rat_p)

        if not values:
            # Fallback to global default
            return self.scorer.default_transition_probability

        return gm_with_zeros_and_nones_handled(values)

    def calculate_relevance(self, transition: Transition) -> Optional[float]:
        """
        Calculate R for a Transition.

        Algorithm:
        1. Collect MANUAL R values from RelevanceEstimation nodes (NOT calculated!)
        2. Collect rationale R values (using audit-wins)
        3. Hard veto: if R=0, return 0
        4. Aggregate via GM
        5. Return None if no evidence

        Args:
            transition: Transition to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.nodes.estimation import RelevanceEstimation
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Manual relevance estimations ONLY (not calculated)
        # This matches legacy: reads manual_relevance (not self.relevance)
        manual_estimations = self._get_manual_estimations(transition, RelevanceEstimation)
        for est in manual_estimations:
            if est.value == 0:
                return 0.0
            values.append(est.value)

        # Rationale relevances
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in transition.rationales.all()]

        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None:
                if rat_r == 0:
                    continue

                values.append(rat_r)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)
