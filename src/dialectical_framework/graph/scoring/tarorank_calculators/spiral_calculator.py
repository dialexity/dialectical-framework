"""
Calculator for Spiral nodes.

Spirals are transformational sequences of transitions.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from functools import reduce
import operator

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.spiral import Spiral


class SpiralCalculator(BaseCalculator):
    """
    Calculator for Spiral nodes.

    Spirals are transformational sequences of transitions.

    P calculation:
    - Product of all transition Ps (sequence semantics)
    - Similar to Cycle, but may skip zeros/Nones (softer policy)
    - Domain implementation skips None and 0.0, which makes sense for spirals

    R calculation:
    - GM of all transition Rs
    - Includes spiral-level rationale Rs (via GM, no rating)
    """

    def score_children(self, spiral: Spiral, skip_valid: bool = True) -> None:
        """
        Score all transitions in this spiral.

        Args:
            spiral: Spiral whose transitions should be scored
            skip_valid: If True, skip scoring transitions with valid scores
        """
        transitions = spiral.transitions_ordered  # Uses SequenceTopologyMixin
        for trans in transitions:
            self.scorer.score_node(trans, recursive=True, skip_valid=skip_valid)

    def calculate_probability(self, spiral: Spiral) -> Optional[float]:
        """
        Calculate P for Spiral as product of transition Ps.

        Softer policy than Cycle: skips None and 0.0 values.
        This makes sense for spirals which represent transformational
        paths rather than strict causal sequences.

        Args:
            spiral: Spiral to calculate P for

        Returns:
            P value (0.0-1.0) or None if no valid transitions
        """
        transitions = spiral.transitions_ordered

        if not transitions:
            return None

        prob = None
        for trans in transitions:
            p = trans.probability
            if p is not None and p > 0:
                if prob is None:
                    prob = 1.0
                prob *= p

        return prob

    def calculate_relevance(self, spiral: Spiral) -> Optional[float]:
        """
        Calculate R for Spiral as GM of transition Rs.

        Args:
            spiral: Spiral to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition relevances
        transitions = spiral.transitions_ordered
        for trans in transitions:
            trans_r = trans.relevance
            if trans_r is not None:
                values.append(trans_r)

        # Spiral-level rationales (no rating weighting)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in spiral.rationales.all()]
        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None and rat_r > 0:
                values.append(rat_r)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)

    def clear_children(self, spiral: Spiral) -> None:
        """
        Clear scores from all transitions.

        Args:
            spiral: Spiral whose transitions should be cleared
        """
        transitions = spiral.transitions_ordered
        for trans in transitions:
            self.scorer.clear_scores(trans, recursive=True)
