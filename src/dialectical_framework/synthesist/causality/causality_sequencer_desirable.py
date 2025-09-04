
from mirascope import Messages, prompt_template

from dialectical_framework.synthesist.causality.causality_sequencer_balanced import \
    CausalitySequencerBalanced


class CausalitySequencerDesirable(CausalitySequencerBalanced):
    @prompt_template(
        """
        USER:
        Which of the following circular causality sequences is the most desirable, i.e. would produce optimal outcomes and maximum results (given that the final step cycles back to the first step):
        {sequences:list}

        <instructions>
        For each sequence:
        1) Estimate the numeric probability (0 to 1) regarding how beneficial/optimal this sequence would be if implemented
        2) Explain why this sequence might occur (or already occurs) in reality
        3) Describe circumstances or contexts where this sequence would be most applicable or useful

        Only use the sequences **exactly as provided**, do not shorten, skip, collapse, or reorder steps. 
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
    ) -> Messages.Type: ...

    @prompt_template(
        """
        USER:
        Assess the following circular causality sequence considering desirability, i.e. producing optimal outcomes and maximum results (given that the final step cycles back to the first step):
        {sequence}

        <instructions>
        1) Estimate the numeric probability (0 to 1) regarding how beneficial/optimal this sequence would be if implemented
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
    def prompt_assess_single_sequence(self, *, sequence: str) -> Messages.Type: ...
