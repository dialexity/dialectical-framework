from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.analyst.domain.symmetrical_transition import \
    SymmetricalTransition
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.reciprocal_solution import ReciprocalSolution
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.wheel_segment import WheelSegment
from dialectical_framework.wisdom_unit import WisdomUnit


class ThinkReciprocalSolution(StrategicConsultant, SettingsAware):
    @prompt_template(
        """
        USER:
        <context>{text}</context>
        
        USER:
        Previous Dialectical Analysis:
        {dialectical_analysis}
        
        USER:
        <instructions>
        Given the initial context and the previous dialectical analysis, suggest solution(s).
        
        Step 1: Frame the problem as a tension between two opposing approaches, where:
        - Thesis (T): The first approach or position
        - Antithesis (A): The contrasting approach or position
        
        The solution that is suggested or implied in the text must represent the Linear Action (Ac) that transforms the negative aspect of the thesis (T-) into the positive aspect of the antithesis (A+)
        
        Step 2: Create a Dialectical Reflection (Re):
        - A complementary solution that is NOT present in the analyzed text
        - This solution should transform the negative aspect of the antithesis (A-) into the positive aspect of the thesis (T+)
        - It should work harmoniously with the Linear Action to create a more complete solution
        
        <example>
            For example:
            In a token vesting dispute, stakeholders disagreed about extending the lock period from January 2025 to January 2026. The original solution was a staged distribution with incentives.
            
            Thesis T: Vest Now
            T+ = Trust Building
            T- = Loss of Value
            
            Antithesis A: Vest Later
            A+ = Value Protection (contradicts T-)
            A- = Trust Erosion (contradicts T+)
            
            Linear Action: Staged distribution with added incentives, offering 25% immediate unlock with enhanced benefits for the delayed 75% portion.
            
            Dialectical Reflection: Liquid staking derivatives for immediate utility (25%) combined with guaranteed exit rights (75%) - complements the linear action.
        </example>
        </instructions>
    
        <formatting>
        Output Linear Action and Dialectical Reflection as a fluent text that could be useful for someone who provided the initial context. Compose the problem statement in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
        </formatting>
        """
    )
    def prompt(self, text: str, focus: WisdomUnit) -> Messages.Type:
        # TODO: do we want to include the whole wheel reengineered? Also transitions so far?
        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": focus.pretty(),
                "component_length": self.settings.component_length,
            }
        }

    @with_langfuse()
    @use_brain(
        response_model=ReciprocalSolution,
    )
    async def reciprocal_solution(self, focus: WisdomUnit):
        return self.prompt(self._text, focus=focus)

    async def think(self, focus: WheelSegment) -> SymmetricalTransition:
        wu = self._wheel.wisdom_unit_at(focus)

        s: ReciprocalSolution = await self.reciprocal_solution(focus=wu)

        self._transition = SymmetricalTransition(
            reciprocal_solution=s,
            source_aliases=[wu.t.alias],
            target_aliases=[wu.a.alias],
            opposite_source_aliases=[wu.a.alias],
            opposite_target_aliases=[wu.t.alias],
            source=wu.extract_segment_t(),
            target=wu.extract_segment_a(),
            predicate=Predicate.TRANSFORMS_TO,
        )

        return self._transition
