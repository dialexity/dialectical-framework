from dependency_injector.wiring import Provide
from mirascope import Messages, prompt_template

from dialectical_framework import WisdomUnit
from dialectical_framework.enums.di import DI
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.settings import Settings
from dialectical_framework.synthesist.polarity.reason_fast_and_simple import \
    ReasonFastAndSimple


class ReasonFastPolarizedConflict(ReasonFastAndSimple):
    _mode = DialecticalReasoningMode.MAJOR_TENSION

    @prompt_template(
        """
        USER:
        # Dialectical Analysis
    
        <instructions>
        In the given context, identify the major problem.
    
        Frame the problem as a tension between two opposing approaches:
        - Thesis (T): The first approach or position
        - Antithesis (A): The contrasting approach or position
    
        T and A must be such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+).
        </instructions>
    
        ASSISTANT:
        {assistant_msg}
    
        USER:
        <instructions>
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
