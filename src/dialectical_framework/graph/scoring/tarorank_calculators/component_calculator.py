"""
Calculator for DialecticalComponent nodes.

DialecticalComponents are leaf nodes in the content hierarchy.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

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
        1. Collect manual P values from ProbabilityEstimation nodes
        2. Collect rationale P values (using audit-wins for critiques)
        3. If no values: return 1.0 (default for components = facts)
        4. Aggregate via GM

        Args:
            component: DialecticalComponent to calculate P for

        Returns:
            P value (0.0-1.0) or 1.0 if no evidence (fact default)
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Manual probability estimations
        manual_p = component.probability  # Uses existing property
        if manual_p is not None:
            values.append(manual_p)

        # Rationale probabilities (with audit-wins)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in component.rationales.all()]

        for rationale in rationales:
            rat_p = auditor.get_probability(rationale)
            if rat_p is not None:
                values.append(rat_p)

        # Default: 1.0 for components (facts)
        if not values:
            return 1.0

        return gm_with_zeros_and_nones_handled(values)

    def calculate_relevance(self, component: DialecticalComponent) -> Optional[float]:
        """
        Calculate R for a DialecticalComponent.

        Algorithm:
        1. Collect manual R values from RelevanceEstimation nodes
        2. Collect rationale R values (using audit-wins)
        3. Hard veto: if any R=0, return 0
        4. Aggregate via GM
        5. Return None if no evidence

        Args:
            component: DialecticalComponent to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Manual relevance estimations
        manual_r = component.relevance  # Uses existing property
        if manual_r is not None:
            # Hard veto check
            if manual_r == 0:
                return 0.0

            values.append(manual_r)

        # Rationale relevances (with audit-wins, no rating weighting)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in component.rationales.all()]

        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None:
                # Soft exclusion: rationales with R=0 don't veto (already handled by auditor returning None)
                if rat_r == 0:
                    continue

                values.append(rat_r)

        # No free lunch: return None if no evidence
        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)
