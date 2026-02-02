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

    R calculation:
    - Nexus R (which is GM of all WisdomUnit Rs)
    - GM of deduplicated external Transition Rs (Spiral > Wheel > Cycle)
    - Includes wheel-level rationale Rs (with rating)

    P calculation:
    - Parent Cycle P
    - Nexus P (which is GM of WU transformation Ps)
    - Wheel's own transitions P (product)
    - Spiral P
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
        Calculate R for Wheel as GM of Nexus R and external transitions.

        Leverages Nexus R (which is GM of WisdomUnit Rs) instead of
        iterating WUs directly. Deduplicates transitions across cycles
        with specificity preference: Spiral > Wheel > Cycle.

        Args:
            wheel: Wheel to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # Get Nexus R (summarized WisdomUnit relevances)
        nexus = wheel.get_nexus()
        if nexus:
            nexus_r = nexus.relevance
            if nexus_r is not None:
                values.append(nexus_r)

        # Collect transitions from cycles with deduplication
        # Key: transition.hash, Value: transition node
        unique_transitions = {}

        # Get transitions from parent Cycle (most generic)
        cycle_result = wheel.cycle.get()
        if cycle_result:
            cycle = cycle_result[0]
            for trans in cycle.transitions:
                unique_transitions[trans.hash] = trans

        # Get transitions from Wheel itself (more specific, prefer over Cycle)
        for trans in wheel.transitions:
            if trans.hash in unique_transitions:
                # Calculate the one being overwritten (legacy behavior)
                old_trans = unique_transitions[trans.hash]
                _ = old_trans.relevance  # Trigger calculation
            # Prefer Wheel version
            unique_transitions[trans.hash] = trans

        # Get transitions from spiral (most specific, prefer over all)
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral = spiral_result[0]
            for trans in spiral.transitions:
                if trans.hash in unique_transitions:
                    # Calculate the one being overwritten (legacy behavior)
                    old_trans = unique_transitions[trans.hash]
                    _ = old_trans.relevance  # Trigger calculation
                # Prefer spiral version
                unique_transitions[trans.hash] = trans

        # Extract relevance scores from unique transitions
        for transition in unique_transitions.values():
            trans_r = transition.relevance
            if trans_r is not None and trans_r > 0.0:
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
        Calculate P for Wheel as GM of Cycle P, Nexus P, Wheel transitions, and Spiral P.

        Wheel P = GM(Cycle P, Nexus P, Wheel transitions product, Spiral P)

        Nexus P is already a summary of WU transformation Ps, so we use it
        directly instead of iterating WUs.

        Args:
            wheel: Wheel to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence
        """
        from functools import reduce
        import operator

        all_terms = []

        # Parent Cycle P
        cycle_result = wheel.cycle.get()
        if cycle_result:
            cycle_p = cycle_result[0].probability
            if cycle_p is not None:
                all_terms.append(cycle_p)

        # Nexus P (summarized WU transformation Ps)
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

        # Spiral P
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral_p = spiral_result[0].probability
            if spiral_p is not None:
                all_terms.append(spiral_p)

        if not all_terms:
            return None

        return gm_with_zeros_and_nones_handled(all_terms)

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
