"""
Calculator for Wheel nodes.

Wheel is the top-level composite containing WisdomUnits via Cycle→Nexus.
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

    Wheel is the top-level composite. WisdomUnits are accessed via Cycle→Nexus.

    R calculation (content relevance):
    - Nexus R (GM of all WisdomUnit Rs - the main content)
    - Wheel-level Transition Rs (wheel's own transitions only, not cycle's)
    - Spiral R (aggregated, includes spiral transitions and rationales)
    - Wheel-level rationale Rs (with rating)

    P calculation (structural feasibility, Markovian):
    - Product of: Cycle P × Nexus P × Wheel trans P × Spiral P
    - All terms are conjunctive requirements (all must work)
    - Skip None values (unknown), keep zeros (hard constraints)
    """

    def score_children(self, wheel: Wheel, force: bool = False) -> None:
        """
        Score Nexus (via Cycle), parent Cycle, and Spiral.

        Nexus scoring recursively scores all WisdomUnits within it.

        Args:
            wheel: Wheel whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score parent Cycle (which will score its Nexus, which scores WUs)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            self.scorer.calculate_score(cycle_result[0], force=force)

        # Score Spiral if present
        spiral_result = wheel.spiral.get()
        if spiral_result:
            self.scorer.calculate_score(spiral_result[0], force=force)

    def calculate_relevance(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate R for Wheel as GM of content relevance signals.

        Per scoring.md, Wheel R includes:
        - Nexus R (summarizes all WisdomUnit Rs - the main content)
        - Wheel-level Transition Rs (ta-cycle detail - wheel's own transitions only)
        - Spiral R (aggregated, if present - includes spiral transitions and rationales)
        - Wheel-level Rationale Rs

        Note: Cycle transitions are NOT included - they belong to Cycle R.
        R measures content relevance, not structural dependencies.

        Args:
            wheel: Wheel to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Nexus R (summarized WisdomUnit relevances - the main content)
        nexus = wheel.get_nexus()
        if nexus:
            nexus_r = nexus.relevance
            if nexus_r is not None:
                values.append(nexus_r)

        # Wheel-level Transition Rs (wheel's own transitions only, not cycle's)
        for trans in wheel.transitions:
            trans_r = trans.relevance
            if trans_r is not None and trans_r > 0.0:
                values.append(trans_r)

        # Spiral R (aggregated - includes spiral transitions and rationales)
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral = spiral_result[0]
            spiral_r = spiral.relevance
            if spiral_r is not None:
                values.append(spiral_r)

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
        Calculate P for Wheel as product of Cycle P, Nexus P, Wheel transitions, and Spiral P.

        Wheel P = Cycle P × Nexus P × Wheel_transitions_product × Spiral P

        Uses Product (not GM) because these are conjunctive requirements - all must
        work for the Wheel to be structurally feasible. This follows causal/Markovian
        semantics where the Wheel's feasibility is limited by its weakest link.

        Nexus P is already a summary of WU transformation Ps (via GM, since WUs are
        independent units in a pool), so we use it directly.

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
            cycle_p = cycle_result[0].probability
            if cycle_p is not None:
                all_terms.append(cycle_p)

        # Nexus P (summarized WU transformation Ps - GM of independent WUs)
        nexus = wheel.get_nexus()
        if nexus:
            nexus_p = nexus.probability
            if nexus_p is not None:
                all_terms.append(nexus_p)

        # Wheel's own transitions P (product for sequential probability)
        wheel_transitions = wheel.transitions
        if wheel_transitions:
            trans_probs = []
            for trans in wheel_transitions:
                trans_p = trans.probability
                if trans_p is not None:
                    trans_probs.append(trans_p)
            if trans_probs:
                wheel_trans_p = reduce(operator.mul, trans_probs, 1.0)
                all_terms.append(wheel_trans_p)

        # Spiral P (transformation path feasibility)
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral_p = spiral_result[0].probability
            if spiral_p is not None:
                all_terms.append(spiral_p)

        if not all_terms:
            return None

        # Product of all terms (conjunctive - all must work)
        # Skip None values (unknown), but any 0 will result in 0 (hard constraint)
        return reduce(operator.mul, all_terms, 1.0)

    def clear_children(self, wheel: Wheel) -> None:
        """
        Clear scores from Cycle (which clears Nexus→WUs) and Spiral.

        Args:
            wheel: Wheel whose children should be cleared
        """
        # Clear parent Cycle (which will clear its Nexus, which clears WUs)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            self.scorer.clear_scores(cycle_result[0])

        # Clear Spiral if present
        spiral_result = wheel.spiral.get()
        if spiral_result:
            self.scorer.clear_scores(spiral_result[0])
