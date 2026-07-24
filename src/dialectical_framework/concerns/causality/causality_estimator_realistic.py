from __future__ import annotations

from dialectical_framework.concerns.causality.causality_estimator_balanced import \
    CausalityEstimatorBalanced


class CausalityEstimatorRealistic(CausalityEstimatorBalanced):

    def _lens_phrase(self) -> str:
        return "for realism, i.e. what typically happens in natural systems"

    def _probability_instruction(self) -> str:
        return "regarding its realistic existence in natural/existing systems"
