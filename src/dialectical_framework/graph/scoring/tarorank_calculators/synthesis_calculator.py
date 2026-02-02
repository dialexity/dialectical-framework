"""
Calculator for Synthesis nodes.

Synthesis is a composite node containing emergent properties from dialectic.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.graph.scoring.pm import pm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.synthesis import Synthesis


class SynthesisCalculator(BaseCalculator):
    """
    Calculator for Synthesis nodes.

    Each Synthesis represents ONE synthesis interpretation with a symmetric S+/S- pair:
    - S+ (exactly one): Complementary harmony (1+1>2)
    - S- (exactly one): Reinforcing uniformity (1+1<2)

    R calculation:
    - Uses power mean (p=4) for S+ ↔ S- pair
    - Includes synthesis-level rationale Rs (with rating)
    - Aggregates via GM

    P calculation:
    - Synthesis has no structural probability (returns 1.0)
    """

    def score_children(self, synthesis: Synthesis, force: bool = False) -> None:
        """
        Score the S+ and S- components in this Synthesis.

        Args:
            synthesis: Synthesis whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score S+ component (exactly one)
        sp_result = synthesis.s_plus.get()
        if sp_result:
            self.scorer.calculate_score(sp_result[0], force=force)

        # Score S- component (exactly one)
        sm_result = synthesis.s_minus.get()
        if sm_result:
            self.scorer.calculate_score(sm_result[0], force=force)

    def calculate_relevance(self, synthesis: Synthesis) -> Optional[float]:
        """
        Calculate R for Synthesis using power mean for the S+/S- pair.

        Args:
            synthesis: Synthesis to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Get S+ component R (exactly one component)
        sp_result = synthesis.s_plus.get()
        sp_r = sp_result[0].relevance if sp_result else None

        # Get S- component R (exactly one component)
        sm_result = synthesis.s_minus.get()
        sm_r = sm_result[0].relevance if sm_result else None

        # S+ ↔ S- pair: Use power mean (p=4) for symmetric dialectical pair
        if sp_r is not None or sm_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((sp_r, sm_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # Synthesis-level rationales
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in synthesis.rationales.all()]
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

    def calculate_probability(self, synthesis: Synthesis) -> Optional[float]:
        """
        Calculate P for Synthesis.

        Synthesis has no structural probability - it's derived content.

        Args:
            synthesis: Synthesis to calculate P for

        Returns:
            P = 1.0 (no structural constraint)
        """
        return 1.0

    def clear_children(self, synthesis: Synthesis) -> None:
        """
        Clear scores from the S+ and S- components.

        Args:
            synthesis: Synthesis whose children should be cleared
        """
        # Clear S+ component (exactly one)
        sp_result = synthesis.s_plus.get()
        if sp_result:
            self.scorer.clear_scores(sp_result[0])

        # Clear S- component (exactly one)
        sm_result = synthesis.s_minus.get()
        if sm_result:
            self.scorer.clear_scores(sm_result[0])
