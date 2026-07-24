from __future__ import annotations

from dialectical_framework.concerns.causality.causality_estimator_balanced import \
    CausalityEstimatorBalanced


class CausalityEstimatorDesirable(CausalityEstimatorBalanced):

    def _lens_phrase(self) -> str:
        return "considering desirability, i.e. producing optimal outcomes and maximum results"

    def _probability_instruction(self) -> str:
        return "regarding how beneficial/optimal this sequence would be if implemented"
