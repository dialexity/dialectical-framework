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
    - GM of all external Transition Rs (wheel-level connections)
    - Includes wheel-level rationale Rs (via GM, no rating)

    P calculation:
    - GM of canonical cycle Ps (T-cycle, TA-cycle, Spiral)
    - GM of all WisdomUnit transformation Ps
    - Skip None values (unknown), keep zeros (hard constraints)
    """

    def score_children(self, wheel: Wheel) -> None:
        """
        Score all WUs, cycles, and spiral.

        Args:
            wheel: Wheel whose children should be scored
        """
        # Score all wisdom units
        wus = [wu for wu, _ in wheel.wisdom_units.all()]
        for wu in wus:
            self.scorer.calculate_score(wu)

        # Score canonical cycles
        t_cycle_result = wheel.t_cycle.get()
        if t_cycle_result:
            self.scorer.calculate_score(t_cycle_result[0])

        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            self.scorer.calculate_score(ta_cycle_result[0])

        spiral_result = wheel.spiral.get()
        if spiral_result:
            self.scorer.calculate_score(spiral_result[0])

    def calculate_relevance(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate R for Wheel as GM of WUs and external transitions.

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

        # External transitions (from TA-cycle, not internal to WUs)
        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            ta_cycle = ta_cycle_result[0]
            for trans in ta_cycle.transitions_ordered:
                trans_r = trans.relevance
                if trans_r is not None:
                    values.append(trans_r)

        # Wheel-level rationales (no rating weighting)
        auditor = RationaleAuditor(self.scorer)
        rationales = [rat for rat, _ in wheel.rationales.all()]
        for rationale in rationales:
            rat_r = auditor.get_relevance(rationale)
            if rat_r is not None and rat_r > 0:
                values.append(rat_r)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)

    def calculate_probability(self, wheel: Wheel) -> Optional[float]:
        """
        Calculate P for Wheel as GM of canonical cycles and WU transformations.

        Args:
            wheel: Wheel to calculate P for

        Returns:
            P value (0.0-1.0) or None if no evidence
        """
        values = []

        # T-cycle P
        t_cycle_result = wheel.t_cycle.get()
        if t_cycle_result:
            t_p = t_cycle_result[0].probability
            if t_p is not None:
                values.append(t_p)

        # TA-cycle P
        ta_cycle_result = wheel.ta_cycle.get()
        if ta_cycle_result:
            ta_p = ta_cycle_result[0].probability
            if ta_p is not None:
                values.append(ta_p)

        # Spiral P
        spiral_result = wheel.spiral.get()
        if spiral_result:
            spiral_p = spiral_result[0].probability
            if spiral_p is not None:
                values.append(spiral_p)

        # WisdomUnit transformation Ps
        wus = [wu for wu, _ in wheel.wisdom_units.all()]
        for wu in wus:
            wu_p = wu.probability
            if wu_p is not None:
                values.append(wu_p)

        if not values:
            return None

        return gm_with_zeros_and_nones_handled(values)

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
