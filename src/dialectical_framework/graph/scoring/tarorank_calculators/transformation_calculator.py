"""
Calculator for Transformation nodes.

Transformations are internal spirals within WisdomUnits.
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

    Transformations are internal spirals within WisdomUnits (T- → A+, A- → T+).

    P calculation:
    - Product of transition Ps (exactly 2 transitions)
    - Softer policy like Spiral: skips None and 0.0 values
    - Transformational semantics (not strict causal sequence)

    R calculation:
    - GM of all transition Rs
    - GM of ac_re WisdomUnit R (action-reflection context)
    - Includes transformation-level rationale Rs (with rating)
    """

    def score_children(self, transformation: Transformation, force: bool = False) -> None:
        """
        Score all transitions and ac_re WisdomUnit in this transformation.

        Args:
            transformation: Transformation whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score all transitions
        transitions = transformation.transitions  # Uses SequenceTopologyMixin
        for trans in transitions:
            self.scorer.calculate_score(trans, force=force)

        # Score ac_re WisdomUnit (action-reflection context)
        ac_re_result = transformation.ac_re.get()
        if ac_re_result:
            ac_re_wu = ac_re_result[0]
            self.scorer.calculate_score(ac_re_wu, force=force)

    def calculate_probability(self, transformation: Transformation) -> Optional[float]:
        """
        Calculate P for Transformation as product of transition Ps.

        Softer policy than Cycle: skips None and 0.0 values.
        This makes sense for transformations which represent transformational
        paths rather than strict causal sequences.

        Args:
            transformation: Transformation to calculate P for

        Returns:
            P value (0.0-1.0) or None if no valid transitions
        """
        transitions = transformation.transitions

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

    def calculate_relevance(self, transformation: Transformation) -> Optional[float]:
        """
        Calculate R for Transformation as GM of transition Rs and ac_re R.

        Args:
            transformation: Transformation to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition relevances
        transitions = transformation.transitions
        for trans in transitions:
            trans_r = trans.relevance
            if trans_r is not None:
                values.append(trans_r)

        # ac_re WisdomUnit relevance (action-reflection context)
        ac_re_result = transformation.ac_re.get()
        if ac_re_result:
            ac_re_wu = ac_re_result[0]
            ac_re_r = ac_re_wu.relevance
            if ac_re_r is not None:
                values.append(ac_re_r)

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
            # Neutral fallback: non-leaf nodes return R=1.0 when no evidence
            return 1.0

        return gm_with_zeros_and_nones_handled(values)

    def clear_children(self, transformation: Transformation) -> None:
        """
        Clear scores from all transitions and ac_re WisdomUnit.

        Args:
            transformation: Transformation whose children should be cleared
        """
        # Clear all transitions
        transitions = transformation.transitions
        for trans in transitions:
            self.scorer.clear_scores(trans)

        # Clear ac_re WisdomUnit (action-reflection context)
        ac_re_result = transformation.ac_re.get()
        if ac_re_result:
            ac_re_wu = ac_re_result[0]
            self.scorer.clear_scores(ac_re_wu)
