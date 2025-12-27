"""
Calculator for WisdomUnit nodes.

WisdomUnit is a composite node containing dialectical pairs.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.utils.pm import pm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class WisdomUnitCalculator(BaseCalculator):
    """
    Calculator for WisdomUnit nodes.

    WisdomUnit is a composite node containing dialectical pairs.

    R calculation:
    - Uses power mean (p=4) for symmetric thesis-antithesis pairs:
      * T ↔ A (neutral pair)
      * T+ ↔ A- (positive thesis ↔ negative antithesis)
      * T- ↔ A+ (negative thesis ↔ positive antithesis)
      * S+ ↔ S- (synthesis pair)
    - Includes transformation R (internal spiral)
    - Includes unit-level rationale Rs (via GM, no rating)
    - Aggregates all via GM

    P calculation:
    - P comes from Transformation (internal spiral)
    - If no transformation: P = 1.0 (no structural constraint)
    """

    def score_children(self, wu: WisdomUnit, skip_valid: bool = True) -> None:
        """
        Score all components and transformation in this WU.

        Args:
            wu: WisdomUnit whose children should be scored
            skip_valid: If True, skip scoring children with valid scores
        """
        # Score all components
        for rel_manager in [wu.t, wu.t_plus, wu.t_minus, wu.a, wu.a_plus, wu.a_minus, wu.s_plus, wu.s_minus]:
            components = [comp for comp, _ in rel_manager.all()]
            for comp in components:
                self.scorer.score_node(comp, recursive=True, skip_valid=skip_valid)

        # Score transformation if present
        trans_result = wu.transformation.get()
        if trans_result:
            transformation = trans_result[0]
            self.scorer.score_node(transformation, recursive=True, skip_valid=skip_valid)

    def calculate_relevance(self, wu: WisdomUnit) -> Optional[float]:
        """
        Calculate R for WisdomUnit using power mean for pairs.

        Uses power mean (p=4) for dialectically symmetric pairs,
        which allows dominance of the stronger pole while balancing opposites.

        Args:
            wu: WisdomUnit to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Helper to get component R
        def get_comp_r(rel_manager) -> Optional[float]:
            comps = [c for c, _ in rel_manager.all()]
            if not comps:
                return None
            # Use first component's relevance (already computed)
            return comps[0].relevance

        # T ↔ A pair (neutral)
        t_r = get_comp_r(wu.t)
        a_r = get_comp_r(wu.a)
        if t_r is not None or a_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((t_r, a_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # T+ ↔ A- pair
        tp_r = get_comp_r(wu.t_plus)
        am_r = get_comp_r(wu.a_minus)
        if tp_r is not None or am_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((tp_r, am_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # T- ↔ A+ pair
        tm_r = get_comp_r(wu.t_minus)
        ap_r = get_comp_r(wu.a_plus)
        if tm_r is not None or ap_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((tm_r, ap_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # S+ ↔ S- pair (if synthesis exists)
        sp_r = get_comp_r(wu.s_plus)
        sm_r = get_comp_r(wu.s_minus)
        if sp_r is not None or sm_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((sp_r, sm_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # Transformation R (internal spiral)
        trans_result = wu.transformation.get()
        if trans_result:
            transformation = trans_result[0]
            trans_r = transformation.relevance
            if trans_r is not None:
                values.append(trans_r)

        # Unit-level rationales (no rating weighting)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in wu.rationales.all()]
        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None and rat_r > 0:
                values.append(rat_r)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)

    def calculate_probability(self, wu: WisdomUnit) -> Optional[float]:
        """
        Calculate P for WisdomUnit from its Transformation.

        Args:
            wu: WisdomUnit to calculate P for

        Returns:
            P value (0.0-1.0) or 1.0 if no transformation (no structural constraint)
        """
        trans_result = wu.transformation.get()
        if not trans_result:
            # No transformation: no structural constraint
            return 1.0

        transformation = trans_result[0]
        return transformation.probability

    def clear_children(self, wu: WisdomUnit) -> None:
        """
        Clear scores from all components and transformation.

        Args:
            wu: WisdomUnit whose children should be cleared
        """
        # Clear all components
        for rel_manager in [wu.t, wu.t_plus, wu.t_minus, wu.a, wu.a_plus, wu.a_minus, wu.s_plus, wu.s_minus]:
            components = [comp for comp, _ in rel_manager.all()]
            for comp in components:
                self.scorer.clear_scores(comp, recursive=True)

        # Clear transformation if present
        trans_result = wu.transformation.get()
        if trans_result:
            transformation = trans_result[0]
            self.scorer.clear_scores(transformation, recursive=True)
