"""
Calculator for Wheel nodes.

Wheel is the top-level composite containing WisdomUnits and cycles.
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

    Wheel is the top-level composite.

    R calculation:
    - GM of all WisdomUnit Rs
    - GM of deduplicated external Transition Rs (Spiral > TA-cycle > T-cycle)
    - Includes wheel-level rationale Rs (with rating)

    P calculation:
    - GM of canonical cycle Ps (T-cycle, TA-cycle, Spiral)
    - GM summarizes WU transformation Ps first, then included as single term
    - This prevents over-weighting internal transformations
    - Skip None values (unknown), keep zeros (hard constraints)
    """

    def score_children(self, wheel: Wheel, force: bool = False) -> None:
        """
        Score all WUs, cycles, and spiral.

        Args:
            wheel: Wheel whose children should be scored
            force: If True, force rescore even if children appear valid
        """
        # Score all wisdom units
        wus = [wu for wu, _ in wheel.wisdom_units.all()]
        for wu in wus:
            self.scorer.calculate_score(wu, force=force)

        # Score canonical cycles
        t_cycle_result = wheel.t_cycle.get()
        if t_cycle_result:
            self.scorer.calculate_score(t_cycle_result[0], force=force)

        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            self.scorer.calculate_score(ta_cycle_result[0], force=force)

        spiral_result = wheel.spiral.get()
        if spiral_result:
            self.scorer.calculate_score(spiral_result[0], force=force)

    def calculate_relevance(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate R for Wheel as GM of WUs and external transitions.

        Deduplicates transitions across cycles with specificity preference:
        Spiral > TA-cycle > T-cycle (most specific wins).

        This prevents double-counting if the same transition appears in
        multiple cycles while preferring the most specific version.

        Args:
            wheel: Wheel to calculate R for

        Returns:
            R value (0.0-1.0) or None if no evidence
        """
        from dialectical_framework.graph.scoring.tarorank_calculators.rationale_auditor import RationaleAuditor

        values = []

        # WisdomUnit relevances
        wus = [wu for wu, _ in wheel.wisdom_units.all()]
        for wu in wus:
            wu_r = wu.relevance
            if wu_r is not None:
                values.append(wu_r)

        # Collect transitions from cycles with deduplication
        # Key: transition.uid, Value: transition node
        unique_transitions = {}

        # Get transitions from t_cycle (most generic)
        t_cycle_result = wheel.t_cycle.get()
        if t_cycle_result:
            t_cycle = t_cycle_result[0]
            for trans in t_cycle.transitions_ordered:
                unique_transitions[trans.uid] = trans

        # Get transitions from ta_cycle (more specific, prefer over t_cycle)
        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            ta_cycle = ta_cycle_result[0]
            for trans in ta_cycle.transitions_ordered:
                if trans.uid in unique_transitions:
                    # Calculate the one being overwritten (legacy behavior)
                    old_trans = unique_transitions[trans.uid]
                    _ = old_trans.relevance  # Trigger calculation
                # Prefer ta_cycle version
                unique_transitions[trans.uid] = trans

        # Get transitions from spiral (most specific, prefer over all)
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral = spiral_result[0]
            for trans in spiral.transitions_ordered:
                if trans.uid in unique_transitions:
                    # Calculate the one being overwritten (legacy behavior)
                    old_trans = unique_transitions[trans.uid]
                    _ = old_trans.relevance  # Trigger calculation
                # Prefer spiral version
                unique_transitions[trans.uid] = trans

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
            # Neutral fallback: non-leaf nodes return R=1.0 when no evidence
            return 1.0

        return gm_with_zeros_and_nones_handled(values)

    def calculate_probability(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate P for Wheel as GM of canonical cycles and WU transformations.

        Wheel P = GM(T-cycle P, TA-cycle P, Spiral P, summarized WU transformation Ps)

        The WU transformation probabilities are first summarized via GM, then
        included as a single term in the final wheel GM. This prevents
        over-weighting of internal transformations relative to canonical cycles.

        Args:
            wheel: Wheel to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence
        """
        canonical_vals = []

        # T-cycle P
        t_cycle_result = wheel.t_cycle.get()
        if t_cycle_result:
            t_p = t_cycle_result[0].probability
            if t_p is not None:
                canonical_vals.append(t_p)

        # TA-cycle P
        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            ta_p = ta_cycle_result[0].probability
            if ta_p is not None:
                canonical_vals.append(ta_p)

        # Spiral P
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral_p = spiral_result[0].probability
            if spiral_p is not None:
                canonical_vals.append(spiral_p)

        # WisdomUnit transformation Ps - summarize first via GM
        internal_summary = None
        unit_vals = []
        wus = [wu for wu, _ in wheel.wisdom_units.all()]
        for wu in wus:
            wu_p = wu.probability
            if wu_p is not None:
                unit_vals.append(wu_p)

        if unit_vals:
            internal_summary = gm_with_zeros_and_nones_handled(unit_vals)

        # Build final list: canonical cycles + single summarized WU transformation term
        all_terms = list(canonical_vals)
        if internal_summary is not None:
            all_terms.append(internal_summary)

        if not all_terms:
            return None

        return gm_with_zeros_and_nones_handled(all_terms)

    def clear_children(self, wheel: Wheel) -> None:
        """
        Clear scores from all WUs, cycles, and spiral.

        Args:
            wheel: Wheel whose children should be cleared
        """
        # Clear all wisdom units
        wus = [wu for wu, _ in wheel.wisdom_units.all()]
        for wu in wus:
            self.scorer.clear_scores(wu)

        # Clear canonical cycles
        t_cycle_result = wheel.t_cycle.get()
        if t_cycle_result:
            self.scorer.clear_scores(t_cycle_result[0])

        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            self.scorer.clear_scores(ta_cycle_result[0])

        spiral_result = wheel.spiral.get()
        if spiral_result:
            self.scorer.clear_scores(spiral_result[0])
