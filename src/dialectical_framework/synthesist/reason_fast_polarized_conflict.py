from mirascope import Messages, prompt_template

from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple


class ReasonFastPolarizedConflict(ReasonFastAndSimple):

    @prompt_template(
    """
    USER:
    <context>{text}</context>
    
    USER:
    # Dialectical Analysis

    <instructions>
    In the given context, identify the major problem.

    Frame the problem as a tension between two opposing approaches:
    - Thesis (T): The first approach or position
    - Antithesis (A): The contrasting approach or position

    T and A must be such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+).
    
    <example>
        For example:
        In a token vesting dispute, stakeholders disagreed about extending the lock period from January 2025 to January 2026. The original solution was a staged distribution with incentives.
        
        T: Vest Now
        T+ = Trust Building
        T- = Loss of Value
        A: Vest Later
        A+ = Value Protection (contradicts T-)
        A- = Trust Erosion (contradicts T+) 
    </example>
    </instructions>

    <formatting>
    Output the dialectical components within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", etc.
    </formatting>
    """)
    def prompt_wu(self, text: str) -> Messages.Type:
        return {
            "computed_fields": {
                "text": text,
                "component_length": self._component_length,
            }
        }