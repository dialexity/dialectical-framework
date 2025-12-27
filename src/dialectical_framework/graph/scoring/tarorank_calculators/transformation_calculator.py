"""
Calculator for Transformation nodes.

Transformations are internal spirals within WisdomUnits.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from functools import reduce
import operator

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transformation import Transformation


class TransformationCalculator(BaseCalculator):
    """
    Calculator for Transformation nodes.

    Transformations are internal spirals within WisdomUnits (T- → A+, A- → T+).

    P calculation:
    - Product of all transition Ps (exactly 2 transitions)
    - Sequence semantics: Any P=0 or P=None breaks the chain

    R calculation:
    - GM of all transition Rs
    - Includes transformation-level rationale Rs (via GM, no rating)
    """

    def score_children(self, transformation: Transformation) -> None:
        """
        Score all transitions in this transformation.

        Args:
            transformation: Transformation whose transitions should be scored
        """
        transitions = transformation.transitions_ordered  # Uses SequenceTopologyMixin
        for trans in transitions:
            self.scorer.calculate_score(trans)

    def calculate_probability(self, transformation: Transformation) -> Optional[float]:
        """
        Calculate P for Transformation as product of transition Ps.

        Args:
            transformation: Transformation to calculate P for

        Returns:
            P value (0.0-1.0) or None if any transition has no P
        """
        transitions = transformation.transitions_ordered

        if not transitions:
            return None

        p_values = []
        for trans in transitions:
            trans_p = trans.probability
            if trans_p is None:
                # Missing data: transformation P is unknown
                return None
            p_values.append(trans_p)

        # Product of all probabilities (sequence semantics)
        return reduce(operator.mul, p_values, 1.0)

    def calculate_relevance(self, transformation: Transformation) -> Optional[float]:
        """
        Calculate R for Transformation as GM of transition Rs.

        Args:
            transformation: Transformation to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition relevances
        transitions = transformation.transitions_ordered
        for trans in transitions:
            trans_r = trans.relevance
            if trans_r is not None:
                values.append(trans_r)

        # Transformation-level rationales (no rating weighting)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in transformation.rationales.all()]
        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None and rat_r > 0:
                values.append(rat_r)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)

    def clear_children(self, transformation: Transformation) -> None:
        """
        Clear scores from all transitions.

        Args:
            transformation: Transformation whose transitions should be cleared
        """
        transitions = transformation.transitions_ordered
        for trans in transitions:
            self.scorer.clear_scores(trans)
