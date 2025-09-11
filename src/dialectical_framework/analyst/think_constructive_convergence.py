from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.analyst.domain.rationale import Rationale
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class ThinkConstructiveConvergence(StrategicConsultant):
    @prompt_template(
        """
        MESSAGES:
        {wheel_construction}
        
        USER:
        <instructions>
        Identify the most actionable intermediate transition step that transforms the negative/exaggerated side of {from_alias}, i.e. {from_minus_alias}, to the positive/constructive side of the {to_alias}, i.e. {to_plus_alias}:
        
        This step should be:
        - Concrete and immediately implementable
        - Bridge the gap between opposing or contrasting elements
        - Create momentum toward synthesis and balance
        - Address the root tension that causes the negative aspect
        
        1. Start with the negative (-) or neutral state of {from_alias}, i.e. {from_minus_alias} or {from_alias}
        2. To reach {to_plus_alias} identify 
            - **Action**: What specific step to take (1-2 sentences)
            - **Mechanism**: How this step transforms the negative into positive (1 sentence)
            - **Timing**: When this transition is most effective (1 phrase)
        
        <examples>
            1) T1- (Tyranny) → T2+ (Balance):
            **Action**: Implement transparent priority matrices with employee input
            **Mechanism**: Converts rigid control into collaborative structure
            **Timing**: During planning cycles
        </examples>
        </instructions>
    
        <formatting>
        Output the transition step as a fluent practical, implementable action plan (summarized but not mentioning derived Action, Mechanism, and Timing) that someone could take immediately to facilitate the transformation. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
        </formatting>
        """
    )
    def prompt(
        self, text: str, focus: WheelSegment, next_ws: WheelSegment
    ) -> Messages.Type:
        # TODO: do we want to include transitions that are already present in the wheel?
        return {
            "computed_fields": {
                "wheel_construction": ReverseEngineer.wheel(
                    text=text, wheel=self._wheel
                ),
                "from_alias": focus.t.alias,
                "from_minus_alias": focus.t_minus.alias,
                "to_alias": next_ws.t.alias,
                "to_plus_alias": next_ws.t_plus.alias,
            }
        }

    @with_langfuse()
    @use_brain(response_model=str)
    async def constructive_convergence(
        self, focus: WheelSegment, next_ws: WheelSegment
    ):
        return self.prompt(self._text, focus=focus, next_ws=next_ws)

    async def think(self, focus: WheelSegment) -> TransitionSegmentToSegment:
        current_index = self._wheel.index_of(focus)
        next_index = (current_index + 1) % self._wheel.degree
        next_ws = self._wheel.wheel_segment_at(next_index)

        return TransitionSegmentToSegment(
            predicate=Predicate.CONSTRUCTIVELY_CONVERGES_TO,
            source_aliases=[focus.t_minus.alias, focus.t.alias],
            target_aliases=[next_ws.t_plus.alias],
            source=focus,
            target=next_ws,
            rationales=[Rationale(
                text=await self.constructive_convergence(focus=focus, next_ws=next_ws)
            )],
        )
