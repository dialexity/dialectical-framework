"""
Calculator for Cycle nodes.

Cycles are sequences of transitions.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING
from functools import reduce
import operator

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle


class CycleCalculator(BaseCalculator):
    """
    Calculator for Cycle nodes.

    Cycles are sequences of transitions.

    P calculation:
    - Product of all transition Ps (sequence semantics)
    - Any P=0 → cycle P=0 (sequence veto)
    - Any P=None → cycle P=None (insufficient data)

    R calculation:
    - GM of all transition Rs
    - Includes cycle-level rationale Rs (via GM, no rating)
    """

    def score_children(self, cycle: Cycle) -> None:
        """
        Score all transitions in this cycle.

        Args:
            cycle: Cycle whose transitions should be scored
        """
        transitions = cycle.transitions_ordered  # Uses SequenceTopologyMixin
        for trans in transitions:
            self.scorer.calculate_score(trans)

    def calculate_probability(self, cycle: Cycle) -> Optional[float]:
        """
        Calculate P for Cycle as product of transition Ps.

        Sequence semantics: P = P1 × P2 × ... × Pn
        Any missing P breaks the chain.

        Args:
            cycle: Cycle to calculate P for

        Returns:
            P value (0.0-1.0) or None if any transition has no P
        """
        transitions = cycle.transitions_ordered

        if not transitions:
            return None

        p_values = []
        for trans in transitions:
            trans_p = trans.probability
            if trans_p is None:
                # Missing data: cycle P is unknown
                return None
            p_values.append(trans_p)

        # Product of all probabilities (sequence semantics)
        return reduce(operator.mul, p_values, 1.0)

    def calculate_relevance(self, cycle: Cycle) -> Optional[float]:
        """
        Calculate R for Cycle as GM of transition Rs.

        Args:
            cycle: Cycle to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Transition relevances
        transitions = cycle.transitions_ordered
        for trans in transitions:
            trans_r = trans.relevance
            if trans_r is not None:
                values.append(trans_r)

        # Cycle-level rationales
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in cycle.rationales.all()]
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

    def clear_children(self, cycle: Cycle) -> None:
        """
        Clear scores from all transitions.

        Args:
            cycle: Cycle whose transitions should be cleared
        """
        transitions = cycle.transitions_ordered
        for trans in transitions:
            self.scorer.clear_scores(trans)
