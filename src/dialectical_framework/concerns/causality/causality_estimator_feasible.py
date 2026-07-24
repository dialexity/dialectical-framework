from __future__ import annotations

from mirascope import llm

from dialectical_framework.concerns.causality.causality_estimator_balanced import \
    CausalityEstimatorBalanced


class CausalityEstimatorFeasible(CausalityEstimatorBalanced):

    def prompt_assess_single_sequence(self, *, sequence: str) -> list:
        return [llm.messages.user(
            f"Assess the following circular causality sequence considering feasibility, "
            f"i.e. best achievable with minimum resistance "
            f"(given that the final step cycles back to the first step):\n"
            f"{sequence}\n\n"
            f"<instructions>\n"
            f"1) Estimate the numeric probability (0 to 1) regarding how easily this sequence could be implemented given current constraints\n"
            f"2) Explain why this sequence might occur (or already occurs) in reality\n"
            f"3) Describe circumstances or contexts where this sequence would be most applicable or useful\n\n"
            f"- Only use the sequence **exactly as provided**, do not shorten, skip, collapse, or reorder steps.\n"
            f"</instructions>\n\n"
            f"<formatting>\n"
            f"- In the explanations and argumentation, for fluency, try to use explicit wording instead of technical aliases.\n"
            f"- Probability is a float between 0 and 1.\n"
            f"</formatting>"
        )]
