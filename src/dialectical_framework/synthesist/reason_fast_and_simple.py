from mirascope import Messages, prompt_template

from dialectical_framework.synthesist.reason_fast import ReasonFast


class ReasonFastAndSimple(ReasonFast):
    @prompt_template(
    """
    USER:
    <context>{text}</context>
    
    USER:
    # Dialectical Analysis

    <instructions>
    In the given context, identify the most important single thesis (idea, concept) T.

    Identify its semantic/functional antithesis (A), such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+). 

    For example:
    T = Love
    T+ = Happiness (positive aspect of Love)
    T- = Fixation (negative aspect of Love)
    A = Indifference (antithesis of Love)
    A+ = Objectivity (positive aspect of Indifference, contradicts Fixation)
    A- = Misery (negative aspect of Indifference, contradicts Happiness).
    </instructions>

    <formatting>
    Output the dialectical components within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", etc.
    
    IMPORTANT: For the structured output, use these EXACT alias values:
    - "T" for the main thesis
    - "A" for the antithesis 
    - "T+" for positive side of thesis
    - "T-" for negative side of thesis
    - "A+" for positive side of antithesis
    - "A-" for negative side of antithesis
    
    Do NOT use descriptive names like "Positive Thesis" or "Negative Antithesis" - only use the exact technical labels above.
    </formatting>
    """)
    def prompt_wu(self, text: str) -> Messages.Type:
        return {
            "computed_fields": {
                "text": text,
                "component_length": self._component_length,
            }
        }