"""
Calculator for Perspective nodes.

Perspective is a composite node containing dialectical pairs.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.graph.scoring.pm import pm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective


class PerspectiveCalculator(BaseCalculator):
    """
    Calculator for Perspective nodes.

    Perspective contains 6 core dialectical positions (exactly one component each).

    R calculation:
    - For each polarity position, gets the single component's R
    - Uses power mean (p=4) for symmetric thesis-antithesis pairs:
      * T ↔ A (neutral pair)
      * T+ ↔ A- (positive thesis ↔ negative antithesis)
      * T- ↔ A+ (negative thesis ↔ positive antithesis)
    - Includes transformations Rs (aggregated if multiple)
    - Includes synthesis Rs (PP-level, aggregated if multiple)
    - Includes unit-level rationale Rs (with rating)
    - Aggregates all via GM

    P calculation:
    - P comes from Transformations (aggregated via product if multiple)
    - If no transformations: P = 1.0 (no structural constraint)
    """

    def score_children(self, pp: Perspective, force: bool = False) -> None:
        """
        Score all components, transformations, and synthesis in this PP.

        Args:
            pp: Perspective whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score all 6 core components
        for rel_manager in [pp.t, pp.t_plus, pp.t_minus, pp.a, pp.a_plus, pp.a_minus]:
            components = [comp for comp, _ in rel_manager.all()]
            for comp in components:
                self.scorer.calculate_score(comp, force=force)

        # Score all transformations
        for transformation, _ in pp.transformations.all():
            self.scorer.calculate_score(transformation, force=force)

        # Score all synthesis alternatives (PP-level)
        for synthesis, _ in pp.synthesis.all():
            self.scorer.calculate_score(synthesis, force=force)

    def calculate_relevance(self, pp: Perspective) -> Optional[float]:
        """
        Calculate R for Perspective using power mean for pairs.

        Uses power mean (p=4) for dialectically symmetric pairs,
        which allows dominance of the stronger angle while balancing opposites.

        Args:
            pp: Perspective to calculate R for

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
        t_r = get_comp_r(pp.t)
        a_r = get_comp_r(pp.a)
        if t_r is not None or a_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((t_r, a_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # T+ ↔ A- pair
        tp_r = get_comp_r(pp.t_plus)
        am_r = get_comp_r(pp.a_minus)
        if tp_r is not None or am_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((tp_r, am_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # T- ↔ A+ pair
        tm_r = get_comp_r(pp.t_minus)
        ap_r = get_comp_r(pp.a_plus)
        if tm_r is not None or ap_r is not None:
            pair_r = pm_with_zeros_and_nones_handled((tm_r, ap_r), p=4)
            if pair_r is not None:
                values.append(pair_r)

        # Transformations Rs (aggregate if multiple)
        trans_rs = []
        for transformation, _ in pp.transformations.all():
            trans_r = transformation.relevance
            if trans_r is not None:
                trans_rs.append(trans_r)
        if trans_rs:
            if len(trans_rs) == 1:
                values.append(trans_rs[0])
            else:
                aggregated_trans_r = gm_with_zeros_and_nones_handled(trans_rs)
                if aggregated_trans_r is not None:
                    values.append(aggregated_trans_r)

        # Synthesis Rs (PP-level, aggregate if multiple)
        synth_rs = []
        for synthesis, _ in pp.synthesis.all():
            synth_r = synthesis.relevance
            if synth_r is not None:
                synth_rs.append(synth_r)
        if synth_rs:
            if len(synth_rs) == 1:
                values.append(synth_rs[0])
            else:
                aggregated_synth_r = gm_with_zeros_and_nones_handled(synth_rs)
                if aggregated_synth_r is not None:
                    values.append(aggregated_synth_r)

        # Unit-level rationales
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in pp.rationales.all()]
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

    def calculate_probability(self, pp: Perspective) -> Optional[float]:
        """
        Calculate P for Perspective from its Transformations.

        If multiple transformations, aggregates via product.

        Args:
            pp: Perspective to calculate P for

        Returns:
            P value (0.0-1.0) or 1.0 if no transformations (no structural constraint)
        """
        # Aggregate P from all transformations via product
        prob = None
        for transformation, _ in pp.transformations.all():
            trans_p = transformation.probability
            if trans_p is not None and trans_p > 0:
                if prob is None:
                    prob = 1.0
                prob *= trans_p

        # No transformations: no structural constraint
        return prob if prob is not None else 1.0

    def clear_children(self, pp: Perspective) -> None:
        """
        Clear scores from all components, transformations, and synthesis.

        Args:
            pp: Perspective whose children should be cleared
        """
        # Clear all 6 core components
        for rel_manager in [pp.t, pp.t_plus, pp.t_minus, pp.a, pp.a_plus, pp.a_minus]:
            components = [comp for comp, _ in rel_manager.all()]
            for comp in components:
                self.scorer.clear_scores(comp)

        # Clear all transformations
        for transformation, _ in pp.transformations.all():
            self.scorer.clear_scores(transformation)

        # Clear all synthesis alternatives (PP-level)
        for synthesis, _ in pp.synthesis.all():
            self.scorer.clear_scores(synthesis)
