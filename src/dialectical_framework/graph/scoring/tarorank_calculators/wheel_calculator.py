"""
Calculator for Wheel nodes.

Wheel is the top-level composite containing Perspectives via Cycle.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator
from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wheel import Wheel


class WheelCalculator(BaseCalculator):
    """
    Calculator for Wheel nodes.

    Wheel is the top-level composite. Perspectives are accessed via Cycle.

    R calculation (content relevance):
    - Perspective Rs (GM of all PP Rs via Cycle - the main content)
    - Wheel-level Transition Rs (wheel's own transitions)
    - Transformation Rs (wheel's transformations)
    - Wheel-level rationale Rs (with rating)

    P calculation (structural feasibility, Markovian):
    - Product of: Cycle P × PP Ps × Wheel trans P × Transformation Ps
    - All terms are conjunctive requirements (all must work)
    - Skip None values (unknown), keep zeros (hard constraints)
    """

    def score_children(self, wheel: Wheel, force: bool = False) -> None:
        """
        Score parent Cycle (which scores PPs) and Transformations.

        Args:
            wheel: Wheel whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score parent Cycle (which scores Perspectives)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            self.scorer.calculate_score(cycle_result[0], force=force)

        # Score Transformations
        for transformation in wheel.transformations:
            self.scorer.calculate_score(transformation, force=force)

    def calculate_relevance(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate R for Wheel as GM of content relevance signals.

        Wheel R includes:
        - Perspective Rs (via Cycle - the main content)
        - Wheel-level Transition Rs
        - Transformation Rs
        - Wheel-level Rationale Rs

        Args:
            wheel: Wheel to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Perspective Rs (via Cycle)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            cycle_obj, _ = cycle_result
            for pp in cycle_obj.perspectives:
                pp_r = pp.relevance
                if pp_r is not None:
                    values.append(pp_r)

        # Wheel-level Transition Rs
        for trans in wheel.edges:
            trans_r = trans.relevance
            if trans_r is not None and trans_r > 0.0:
                values.append(trans_r)

        # Transformation Rs
        for transformation in wheel.transformations:
            trans_r = transformation.relevance
            if trans_r is not None:
                values.append(trans_r)

        # Wheel-level rationales
        # Apply rationale.rating as per scoring.md (parent applies rating)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in wheel.rationales.all()]
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

    def calculate_probability(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate P for Wheel as product of Cycle P, PP Ps, Wheel transitions, and Transformation Ps.

        Wheel P = Cycle P × PP_Ps × Wheel_transitions_product × Transformation_Ps

        Uses Product (not GM) because these are conjunctive requirements - all must
        work for the Wheel to be structurally feasible.

        Args:
            wheel: Wheel to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence
        """
        from functools import reduce
        import operator

        all_terms = []

        # Parent Cycle P (thesis ordering feasibility)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            cycle_obj, _ = cycle_result
            cycle_p = cycle_obj.probability
            if cycle_p is not None:
                all_terms.append(cycle_p)

            # PP Ps (via Cycle)
            for pp in cycle_obj.perspectives:
                pp_p = pp.probability
                if pp_p is not None:
                    all_terms.append(pp_p)

        # Wheel's own transitions P (product for sequential probability)
        wheel_transitions = wheel.edges
        if wheel_transitions:
            trans_probs = []
            for trans in wheel_transitions:
                trans_p = trans.probability
                if trans_p is not None:
                    trans_probs.append(trans_p)
            if trans_probs:
                wheel_trans_p = reduce(operator.mul, trans_probs, 1.0)
                all_terms.append(wheel_trans_p)

        # Transformation Ps
        for transformation in wheel.transformations:
            trans_p = transformation.probability
            if trans_p is not None:
                all_terms.append(trans_p)

        if not all_terms:
            return None

        # Product of all terms (conjunctive - all must work)
        return reduce(operator.mul, all_terms, 1.0)

    def clear_children(self, wheel: Wheel) -> None:
        """
        Clear scores from Cycle (which clears PPs) and Transformations.

        Args:
            wheel: Wheel whose children should be cleared
        """
        # Clear parent Cycle (which clears Perspectives)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            self.scorer.clear_scores(cycle_result[0])

        # Clear Transformations
        for transformation in wheel.transformations:
            self.scorer.clear_scores(transformation)
