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
        1. Get transition's own P (from property, which returns manual since calculated was cleared)
        2. Collect rationale probabilities
        3. Aggregate via GM
        4. Fallback to scorer.default_transition_probability if no values

        Args:
            transition: Transition to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence and no default
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition's own probability (manual, since calculated was cleared before this)
        if transition.probability is not None:
            # Hard veto: if transition P=0, return 0 immediately (matches legacy _hard_veto_on_own_zero)
            if transition.probability == 0:
                return 0.0
            # If we're here, probability is not None and not 0, so must be positive
            values.append(transition.probability)

        # Rationale probabilities
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in transition.rationales.all()]

        for rationale in rationales:
            rat_p = auditor.get_probability(rationale)
            if rat_p is not None and rat_p > 0.0:
                rating = rationale.rating if rationale.rating is not None else 1.0
                weighted_p = rat_p * rating
                if weighted_p > 0.0:  # Filter after rating application
                    values.append(weighted_p)

        if not values:
            # Fallback to global default (intentionally global, not instance-level)
            return self.scorer.default_transition_probability

        return gm_with_zeros_and_nones_handled(values)

    def calculate_relevance(self, transition: Transition) -> Optional[float]:
        """
        Calculate R for a Transition.

        Algorithm:
        1. Get transition's own R (from property, which returns manual since calculated was cleared)
        2. Hard veto: if transition R=0, return 0
        3. Collect rationale R values (using audit-wins)
        4. Aggregate via GM
        5. Return None if no evidence

        Args:
            transition: Transition to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition's own relevance (manual, since calculated was cleared before this)
        if transition.relevance is not None:
            # Hard veto: if transition R=0, return 0 immediately
            if transition.relevance == 0:
                return 0.0
            # If we're here, relevance is not None and not 0, so must be positive
            # (relevance is constrained to [0, 1])
            # Note: Transition's own value has no rating (only Rationale.rating exists)
            values.append(transition.relevance)

        # Rationale relevances
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in transition.rationales.all()]

        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None and rat_r > 0.0:
                rating = rationale.rating if rationale.rating is not None else 1.0
                weighted_r = rat_r * rating
                if weighted_r > 0.0:  # Filter after rating application
                    values.append(weighted_r)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)
