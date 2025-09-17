from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework import Transition
from dialectical_framework.ai_dto.action_plan_dto import ActionPlanDto
from dialectical_framework.ai_dto.transition_summary_dto import TransitionSummaryDto
from dialectical_framework.analyst.domain.rationale import Rationale
from dialectical_framework.analyst.domain.transition_segment_to_segment import \
    TransitionSegmentToSegment
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.synthesist.domain.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
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
        3. Estimate the numeric probability (0 to 1) of this transition happening
        
        <examples>
            T1- (Tyranny) → T2+ (Balance):
            **Action**: Implement transparent priority matrices with employee input
            **Mechanism**: Converts rigid control into collaborative structure
            **Timing**: During planning cycles
            Probability: 0.3
        </examples>
        </instructions>
    
        <formatting>
        Output the transition step as a fluent practical, implementable action plan (summarized but not mentioning derived Action, Mechanism, and Timing) that someone could take immediately to facilitate the transformation. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
        Probability should be a number between 0 and 1.
        </formatting>
        """
    )
    def prompt_constructive_convergence(
        self, text: str, focus: WheelSegment, next_ws: WheelSegment
    ) -> Messages.Type:
        return {
            "computed_fields": {
                "wheel_construction": ReverseEngineer.till_wheel_without_convergent_transitions(
                    text=text, wheel=self._wheel
                ),
                "from_alias": focus.t.alias,
                "from_minus_alias": focus.t_minus.alias,
                "to_alias": next_ws.t.alias,
                "to_plus_alias": next_ws.t_plus.alias,
            }
        }

    @prompt_template(
        """
        MESSAGES:
        {think_constructive_convergence}
        
        ASSISTANT:
        {transition_info}
        
        USER:
        Let's summarize it into a One-liner and Action phrase.
        
        # 1. One liner:
        Your task is to produce one ultra-short one-liner (max ~12 words) that:
        - Captures the essence of the transformation.
        - Uses active, simple language.
        - Focuses on what to do, not the background.
        
        <examples_one_liner>
            Exploitation → Cultural Transformation
            One-liner: Tie business goals to customer value, engagement, and leadership behaviors.
            
            Micromanagement → Engagement
            One-liner: Shift from control to supportive weekly coaching.
        </examples_one_liner>
        
        # 2. Action phrase:
        Your task is to produce a super-compressed action phrase (max 5–8 words) that:
        - States the key shift or action.
        - Avoids background/context — just the transformation.
 
        <examples_action_phrase>
            Exploitation → Cultural Transformation
            Action phrase: Link profit to values and people.
            
            Micromanagement → Engagement
            Action phrase: Coach, don’t control.
            
            Burnout → Stability
            Action phrase: Improve workflows via safe forums.
        </examples_action_phrase>
 
        <formatting>
        One-liner: [one-liner text]
        Action phrase: [action phrase text]
        </formatting>
        """
    )
    def prompt_summarize(self, text: str, *, transition: TransitionSegmentToSegment) -> Messages.Type:
        return {
            "computed_fields": {
                "think_constructive_convergence": self.prompt_constructive_convergence(text, focus=transition.source, next_ws=transition.target),
                "transition_info": self._transition_info(transition),

            }
        }

    def _transition_info(self, transition: Transition, r: Rationale = None) -> str:
        if r is None:
            rationale = transition.best_rationale
        else:
            rationale = r

        str_pieces = [
            f"{', '.join(transition.source_aliases)} → {', '.join(transition.target_aliases)}",
            f"Advice: {rationale.text if rationale else 'N/A'}",
        ]
        transition_str = "\n".join(str_pieces)

        aliases = [*transition.source_aliases] + [*transition.target_aliases]
        deck = DialecticalComponentsDeck(dialectical_components=[
            transition.source.t, transition.source.t_minus, transition.source.t_plus,
            transition.target.t, transition.target.t_plus, transition.target.t_minus
        ])
        for a in aliases:
            transition_str = dc_replace(transition_str, a, f"{a} ({deck.get_by_alias(a).statement})")
        return transition_str

    @with_langfuse()
    @use_brain(response_model=ActionPlanDto)
    async def constructive_convergence(
        self, focus: WheelSegment, next_ws: WheelSegment
    ) -> ActionPlanDto:
        return self.prompt_constructive_convergence(self._text, focus=focus, next_ws=next_ws)

    # TODO: use a fast and cheap model for this
    @with_langfuse()
    @use_brain(response_model=TransitionSummaryDto)
    async def summarize(self, transition: TransitionSegmentToSegment):
        return self.prompt_summarize(self._text, transition=transition)

    async def think(self, focus: WheelSegment) -> TransitionSegmentToSegment:
        current_index = self._wheel.index_of(focus)
        next_index = (current_index + 1) % self._wheel.degree
        next_ws = self._wheel.wheel_segment_at(next_index)

        action_plan_dto = await self.constructive_convergence(focus=focus, next_ws=next_ws)
        rationale = Rationale(
            text=action_plan_dto.action_plan,
            # TODO: is it ok to use self-assigned probability here? It somewhat contradicts the t-cycle probability, which overall should be the same for the spiral, no?
            probability=action_plan_dto.probability,
        )

        transition = self._wheel.spiral.graph.get_transition(
            [focus.t_minus.alias, focus.t.alias],
                        [next_ws.t_plus.alias]
        )
        if transition is None:
            transition = TransitionSegmentToSegment(
                predicate=Predicate.CONSTRUCTIVELY_CONVERGES_TO,
                source_aliases=[focus.t_minus.alias, focus.t.alias],
                target_aliases=[next_ws.t_plus.alias],
                source=focus,
                target=next_ws,
                rationales=[rationale],
            )
        else:
            transition.rationales.append(rationale)
        summary = await self.summarize(transition=transition)

        rationale.summary = summary.one_liner
        rationale.headline = summary.action_phrase

        return transition
