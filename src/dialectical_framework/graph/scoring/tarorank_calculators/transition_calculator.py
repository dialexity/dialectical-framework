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
        1. Get transition's P (from property, which aggregates all P estimations)
        2. Hard veto: if P=0, return 0
        3. Fallback to scorer.default_transition_probability if no values

        Note: In the new model, rationale-provided estimations target the transition
        directly, so they're already included in transition.probability.

        Args:
            transition: Transition to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence and no default
        """
        # Transition's probability (aggregates all P estimations including rationale-provided)
        p = transition.probability
        if p is not None:
            # Hard veto: if transition P=0, return 0 immediately
            if p == 0:
                return 0.0
            return p

        # Fallback to global default (intentionally global, not instance-level)
        return self.scorer.default_transition_probability

    def calculate_relevance(self, transition: Transition) -> Optional[float]:
        """
        Calculate R for a Transition.

        Algorithm:
        1. Get transition's R (from property, which aggregates all R estimations)
        2. Hard veto: if R=0, return 0
        3. Return None if no evidence

        Note: In the new model, rationale-provided estimations target the transition
        directly, so they're already included in transition.relevance.

        Args:
            transition: Transition to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        # Transition's relevance (aggregates all R estimations including rationale-provided)
        r = transition.relevance
        if r is not None:
            # Hard veto: if transition R=0, return 0 immediately
            if r == 0:
                return 0.0
            return r

        return None
