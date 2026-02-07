"""
Calculator for DialecticalComponent nodes.

DialecticalComponents are leaf nodes in the content hierarchy.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class ComponentCalculator(BaseCalculator):
    """
    Calculator for DialecticalComponent nodes.

    DialecticalComponents are leaf nodes in the content hierarchy.

    P calculation:
    - Default: 1.0 (facts exist with certainty)
    - Can be manually set via ProbabilityEstimation nodes
    - Aggregates with rationale probabilities (if any)

    R calculation:
    - Combines multiple independent evidence sources via GM:
      * Component's own R (if provided)
      * Each rationale R (no weighting)
    - Hard veto: R=0 → return 0 (structural impossibility)
    - Returns None if no evidence
    """

    def calculate_probability(self, component: DialecticalComponent) -> Optional[float]:
        """
        Calculate P for a DialecticalComponent.

        Algorithm:
        1. Get component's P (from property, which aggregates all P estimations)
        2. Hard veto: if P=0, return 0
        3. If no values: return 1.0 (default for components = facts)

        Note: In the new model, rationale-provided estimations target the component
        directly, so they're already included in component.probability.

        Args:
            component: DialecticalComponent to calculate P for

        Returns:
            P value (0.0-1.0) or 1.0 if no evidence (fact default)
        """
        # Component's probability (aggregates all P estimations including rationale-provided)
        p = component.probability
        if p is not None:
            # Hard veto: if component P=0, return 0 immediately
            if p == 0:
                return 0.0
            return p

        # Default: 1.0 for components (facts)
        return 1.0

    def calculate_relevance(self, component: DialecticalComponent) -> Optional[float]:
        """
        Calculate R for a DialecticalComponent.

        Algorithm:
        1. Get component's R (from property, which aggregates all R estimations)
        2. Hard veto: if R=0, return 0
        3. Return None if no evidence

        Note: In the new model, rationale-provided estimations target the component
        directly, so they're already included in component.relevance.

        Args:
            component: DialecticalComponent to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        # Component's relevance (aggregates all R estimations including rationale-provided)
        r = component.relevance
        if r is not None:
            # Hard veto: if component R=0, return 0 immediately
            if r == 0:
                return 0.0
            return r

        # No free lunch: return None if no evidence
        return None
