"""
Calculator for Transformation nodes.

Transformations are Action-Reflection structures within WisdomUnits.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transformation import Transformation


class TransformationCalculator(BaseCalculator):
    """
    Calculator for Transformation nodes.

    Transformations are Action-Reflection structures within WisdomUnits,
    containing 6 Transition positions (Ac, Re, Ac+, Ac-, Re+, Re-).

    P calculation:
    - Product of 6 transition Ps
    - Softer policy: skips None and 0.0 values
    - Transformational semantics (not strict causal sequence)

    R calculation:
    - GM of all 6 transition Rs
    - Includes transformation-level rationale Rs (with rating)
    """

    def score_children(self, transformation: Transformation, force: bool = False) -> None:
        """
        Score all 6 transitions in this transformation.

        Args:
            transformation: Transformation whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score all 6 position transitions
        for manager in [
            transformation.ac, transformation.re,
            transformation.ac_plus, transformation.ac_minus,
            transformation.re_plus, transformation.re_minus
        ]:
            result = manager.get()
            if result:
                trans, _ = result
                self.scorer.calculate_score(trans, force=force)

    def calculate_probability(self, transformation: Transformation) -> Optional[float]:
        """
        Calculate P for Transformation as product of transition Ps.

        Softer policy: skips None and 0.0 values.
        This makes sense for transformations which represent transformational
        paths rather than strict causal sequences.

        Args:
            transformation: Transformation to calculate P for

        Returns:
            P value (0.0-1.0) or None if no valid transitions
        """
        prob = None

        for manager in [
            transformation.ac, transformation.re,
            transformation.ac_plus, transformation.ac_minus,
            transformation.re_plus, transformation.re_minus
        ]:
            result = manager.get()
            if result:
                trans, _ = result
                p = trans.probability
                if p is not None and p > 0:
                    if prob is None:
                        prob = 1.0
                    prob *= p

        return prob

    def calculate_relevance(self, transformation: Transformation) -> Optional[float]:
        """
        Calculate R for Transformation as GM of transition Rs and rationale Rs.

        Args:
            transformation: Transformation to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition relevances (6 positions)
        for manager in [
            transformation.ac, transformation.re,
            transformation.ac_plus, transformation.ac_minus,
            transformation.re_plus, transformation.re_minus
        ]:
            result = manager.get()
            if result:
                trans, _ = result
                trans_r = trans.relevance
                if trans_r is not None:
                    values.append(trans_r)

        # Transformation-level rationales
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in transformation.rationales.all()]
        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None and rat_r > 0.0:
                rating = rationale.rating if rationale.rating is not None else 1.0
                weighted_r = rat_r * rating
                if weighted_r > 0.0:  # Filter after rating application
                    values.append(weighted_r)

        if not values:
            # No evidence: return None (excluded from parent aggregation)
            return None

        return gm_with_zeros_and_nones_handled(values)

    def clear_children(self, transformation: Transformation) -> None:
        """
        Clear scores from all 6 transitions.

        Args:
            transformation: Transformation whose children should be cleared
        """
        # Clear all 6 position transitions
        for manager in [
            transformation.ac, transformation.re,
            transformation.ac_plus, transformation.ac_minus,
            transformation.re_plus, transformation.re_minus
        ]:
            result = manager.get()
            if result:
                trans, _ = result
                self.scorer.clear_scores(trans)
