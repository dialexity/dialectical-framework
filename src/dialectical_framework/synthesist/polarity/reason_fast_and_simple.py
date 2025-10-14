from dependency_injector.wiring import Provide
from mirascope import Messages, prompt_template

from dialectical_framework import WisdomUnit
from dialectical_framework.enums.di import DI
from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.polarity.reason_fast import ReasonFast


class ReasonFastAndSimple(ReasonFast):
    @prompt_template(
        """
        USER:
        # Dialectical Analysis
    
        <instructions>
        In the provided context, identify the most important single thesis (idea, concept) T.
    
        Identify its semantic/functional antithesis (A), such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+). 
        </instructions>
    
        ASSISTANT:
        {assistant_msg}
    
        USER:
        <instructions>
        For example:
        T = Love
        T+ = Happiness (positive aspect of Love)
        T- = Fixation (negative aspect of Love)
        A = Indifference (antithesis of Love)
        A+ = Objectivity (positive aspect of Indifference, contradicts Fixation)
        A- = Misery (negative aspect of Indifference, contradicts Happiness).
        </instructions>
    
        <formatting>
        Output the dialectical components within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice, but don't mention any special denotations such as "T", "T+", "A-", etc. in them.
        
        IMPORTANT: For the structured output, use these EXACT alias values:
        - "T" for the main thesis
        - "A" for the antithesis 
        - "T+" for positive side of thesis
        - "T-" for negative side of thesis
        - "A+" for positive side of antithesis
        - "A-" for negative side of antithesis
        
        Do NOT use descriptive names like "Positive Thesis" or "Negative Antithesis" - only use the exact technical labels above.
        </formatting>
    """
    )
    def prompt_next(self, wu_so_far: WisdomUnit, config: Settings = Provide[DI.settings]) -> Messages.Type:
        assistant_msg = "Ok, will do, any additional instructions?"
        if wu_so_far.t or wu_so_far.a:
            assistant_msg = "\n".join([f'T = {wu_so_far.t.statement}', f'A = {wu_so_far.a.statement}'])
        return {
            "computed_fields": {
                "assistant_msg": assistant_msg,
                "component_length": config.component_length,
            }
        }
