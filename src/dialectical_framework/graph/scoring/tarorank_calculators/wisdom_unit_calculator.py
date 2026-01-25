"""
Calculator for WisdomUnit nodes.

WisdomUnit is a composite node containing dialectical pairs.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.graph.scoring.pm import pm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class WisdomUnitCalculator(BaseCalculator):
    """
    Calculator for WisdomUnit nodes.

    WisdomUnit contains 6 core dialectical positions (exactly one component each).

    R calculation:
    - For each polarity position, gets the single component's R
    - Uses power mean (p=4) for symmetric thesis-antithesis pairs:
      * T ↔ A (neutral pair)
      * T+ ↔ A- (positive thesis ↔ negative antithesis)
      * T- ↔ A+ (negative thesis ↔ positive antithesis)
    - Includes transformation R (internal spiral, which includes synthesis)
    - Includes unit-level rationale Rs (with rating)
    - Aggregates all via GM

    Note: Synthesis R flows through Transformation (Synthesis → Transformation → WU)

    P calculation:
    - P comes from Transformation (internal spiral)
    - If no transformation: P = 1.0 (no structural constraint)
    """

    def score_children(self, wu: WisdomUnit, force: bool = False) -> None:
        """
        Score all components and transformation in this WU.

        Args:
            wu: WisdomUnit whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score all 6 core components
        for rel_manager in [wu.t, wu.t_plus, wu.t_minus, wu.a, wu.a_plus, wu.a_minus]:
            components = [comp for comp, _ in rel_manager.all()]
            for comp in components:
                self.scorer.calculate_score(comp, force=force)

        # Score transformation if present (includes synthesis scoring)
        trans_result = wu.transformation.get()
        if trans_result:
            transformation = trans_result[0]
            self.scorer.calculate_score(transformation, force=force)

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

        # Helper to get component R (aggregates multiple components via GM)
        def get_comp_r(rel_manager) -> Optional[float]:
            comps = [c for c, _ in rel_manager.all()]
            if not comps:
                return None

            # Collect relevances from all components
            comp_rs = []
            for comp in comps:
                if comp.relevance is not None:
                    comp_rs.append(comp.relevance)

            if not comp_rs:
                return None

            # If single component, return directly
            if len(comp_rs) == 1:
                return comp_rs[0]

            # Multiple components: aggregate via GM
            return gm_with_zeros_and_nones_handled(comp_rs)

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

        # Transformation R (internal spiral, includes synthesis R)
        trans_result = wu.transformation.get()
        if trans_result:
            transformation = trans_result[0]
            trans_r = transformation.relevance
            if trans_r is not None:
                values.append(trans_r)

        # Unit-level rationales
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in wu.rationales.all()]
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
        # Clear all 6 core components
        for rel_manager in [wu.t, wu.t_plus, wu.t_minus, wu.a, wu.a_plus, wu.a_minus]:
            components = [comp for comp, _ in rel_manager.all()]
            for comp in components:
                self.scorer.clear_scores(comp)

        # Clear transformation if present (includes synthesis clearing)
        trans_result = wu.transformation.get()
        if trans_result:
            transformation = trans_result[0]
            self.scorer.clear_scores(transformation)
