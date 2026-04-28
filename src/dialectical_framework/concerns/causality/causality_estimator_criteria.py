from __future__ import annotations

from dependency_injector.wiring import Provide, inject
from mirascope import Messages, prompt_template

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

    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences best satisfies the following assessment criteria: {criteria}
        (given that the final step cycles back to the first step):
        {sequences:list}

        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) with emphasis on the assessment criteria above
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        - Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps.
        </instructions>

        <formatting>
        - Output each circular causality sequence (cycle) as ordered aliases (technical placeholders) of statements as provided e.g. C1, C2, C3, ...
        - In the explanations, for fluency, use explicit wording instead of aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_assess_multiple_sequences(
        self, *, sequences: list[str]
    ) -> "Messages.Type":
        return {
            "computed_fields": {
                "criteria": self._criteria,
            }
        }

    @prompt_template(
        """
        USER:
        Assess the following circular causality sequence with focus on the following assessment criteria: {criteria}
        (given that the final step cycles back to the first step):
        {sequence}

        <instructions>
        1) Estimate the numeric probability (0 to 1) with emphasis on the assessment criteria above
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        - Only use the sequence **exactly as provided**, do not shorten, skip, collapse, or reorder steps.
        </instructions>

        <formatting>
        - In the explanations and argumentation, for fluency, try to use explicit wording instead of technical aliases.
        - Probability is a float between 0 and 1.
        </formatting>
        """
    )
    def prompt_assess_single_sequence(
        self, *, sequence: str
    ) -> "Messages.Type":
        return {
            "computed_fields": {
                "criteria": self._criteria,
            }
        }
