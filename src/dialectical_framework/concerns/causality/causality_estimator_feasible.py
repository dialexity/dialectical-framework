from __future__ import annotations

from dialectical_framework.concerns.causality.causality_estimator_balanced import \
    CausalityEstimatorBalanced


class CausalityEstimatorFeasible(CausalityEstimatorBalanced):

    def _lens_phrase(self) -> str:
        return "considering feasibility, i.e. best achievable with minimum resistance"

    def _probability_instruction(self) -> str:
        return "regarding how easily this sequence could be implemented given current constraints"
