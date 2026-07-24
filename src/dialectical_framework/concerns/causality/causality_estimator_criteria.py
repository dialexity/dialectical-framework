from __future__ import annotations

from dependency_injector.wiring import Provide, inject

from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.causality.causality_estimator_balanced import \
    CausalityEstimatorBalanced
from dialectical_framework.protocols.input_resolver import InputResolver


class CausalityEstimatorCriteria(CausalityEstimatorBalanced):
    """
    Causality estimator that uses custom assessment criteria.

    Instead of the balanced/realistic/desirable/feasible perspective,
    this estimator evaluates sequences against pre-formulated criteria
    derived from a free-form exploration intent.

    Criteria formulation happens upstream (in BuildWheels).
    """

    @inject
    def __init__(
        self,
        criteria: str,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ):
        super().__init__(input_resolver=input_resolver)
        self._criteria = criteria

    def _lens_phrase(self) -> str:
        return f"with focus on the following assessment criteria: {self._criteria}"

    def _probability_instruction(self) -> str:
        return "with emphasis on the assessment criteria above"
