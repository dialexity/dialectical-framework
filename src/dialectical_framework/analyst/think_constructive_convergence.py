from __future__ import annotations

from typing import TYPE_CHECKING

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.action_plan_dto import ActionPlanDto
from dialectical_framework.ai_dto.transition_summary_dto import TransitionSummaryDto
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.utils.dc_replace import dc_replace
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.rationale import Rationale
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.graph.nodes.transition import Transition as GraphTransition
from dialectical_framework.graph.nodes.rationale import Rationale as GraphRationale


class ThinkConstructiveConvergence(StrategicConsultant, SettingsAware):
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
            T1- (Tyranny) → T2+ (Balance):
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
    def prompt_constructive_convergence(
        self, text: str, focus: WheelSegment, next_ws: WheelSegment
    ) -> "Messages.Type":
        # Get aliases from graph-native components
        focus_t_result = focus.t.get()
        focus_t_minus_result = focus.t_minus.get()
        next_ws_t_result = next_ws.t.get()
        next_ws_t_plus_result = next_ws.t_plus.get()

        # Extract aliases from PolarityRelationship
        from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship

        from_alias = None
        if focus_t_result:
            _, rel = focus_t_result
            if isinstance(rel, PolarityRelationship):
                from_alias = rel.alias

        from_minus_alias = None
        if focus_t_minus_result:
            _, rel = focus_t_minus_result
            if isinstance(rel, PolarityRelationship):
                from_minus_alias = rel.alias

        to_alias = None
        if next_ws_t_result:
            _, rel = next_ws_t_result
            if isinstance(rel, PolarityRelationship):
                to_alias = rel.alias

        to_plus_alias = None
        if next_ws_t_plus_result:
            _, rel = next_ws_t_plus_result
            if isinstance(rel, PolarityRelationship):
                to_plus_alias = rel.alias

        return {
            "computed_fields": {
                "wheel_construction": ReverseEngineer.till_wheel_without_convergent_transitions(
                    text=text, wheel=self._wheel
                ),
                "from_alias": from_alias or "T",
                "from_minus_alias": from_minus_alias or "T-",
                "to_alias": to_alias or "T",
                "to_plus_alias": to_plus_alias or "T+",
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

        # 3. Haiku:
        Your task is to produce a haiku (max 3 lines) that:
        - Captures the essence of the transformation.
        - Uses active, simple language.
        - Focuses on what to do, not the background.
        - Easy to memorize.

        <examples_action_phrase>
            Exploitation → Cultural Transformation
            Action phrase: Link profit to values and people.

            Micromanagement → Engagement
            Action phrase: Coach, don't control.

            Burnout → Stability
            Action phrase: Improve workflows via safe forums.
        </examples_action_phrase>

        <formatting>
        One-liner: [one-liner text]
        Action phrase: [action phrase text]
        Haiku: [haiku text]
        </formatting>
        """
    )
    def prompt_summarize(self, text: str, *, transition: Transition) -> "Messages.Type":
        # Extract segments from transition using wheel context
        wheel = self._wheel
        focus = transition.get_source_wheel_segment(wheel=wheel)
        next_ws = transition.get_target_wheel_segment(wheel=wheel)

        if not focus or not next_ws:
            raise ValueError(f"Cannot extract wheel segments from transition {transition.uid}")

        return {
            "computed_fields": {
                "think_constructive_convergence": self.prompt_constructive_convergence(text, focus=focus, next_ws=next_ws),
                "transition_info": self._transition_info(transition),

            }
        }

    @staticmethod
    def _transition_info(transition: Transition, r: Rationale | None = None) -> str:
        """
        Get human-readable transition information with aliases.

        Args:
            transition: The transition to get info from
            r: Optional specific rationale to use. If None, uses best rationale from transition.

        Returns:
            Formatted string with source → target (using aliases) and advice
        """
        # Get rationale - either provided or best from transition
        rationale = r if r is not None else transition.best_rationale

        # Get source and target components from transition
        source_result = transition.source.get()
        target_result = transition.target.get()

        if not source_result or not target_result:
            raise ValueError(
                f"Transition {transition.uid} is missing required relationships. "
                f"Source: {source_result is not None}, Target: {target_result is not None}"
            )

        source_comp, _ = source_result
        target_comp, _ = target_result

        # Get aliases from wheel segments
        source_segment = transition.get_source_wheel_segment()
        target_segment = transition.get_target_wheel_segment()

        if source_segment and target_segment:
            source_label = source_comp.get_alias(source_segment.wisdom_unit)
            target_label = target_comp.get_alias(target_segment.wisdom_unit)
        else:
            # Fallback if segments not found (shouldn't happen normally)
            source_label = source_comp.statement
            target_label = target_comp.statement

        str_pieces = [
            f"{source_label} → {target_label}",
            f"Advice: {rationale.text if rationale else 'N/A'}",
        ]

        return "\n".join(str_pieces)

    @with_langfuse()
    @use_brain(response_model=ActionPlanDto)
    async def constructive_convergence(
        self, focus: WheelSegment, next_ws: WheelSegment
    ) -> ActionPlanDto:
        return self.prompt_constructive_convergence(self._text, focus=focus, next_ws=next_ws)

    # TODO: use a fast and cheap model for this
    @with_langfuse()
    @use_brain(response_model=TransitionSummaryDto)
    async def summarize(self, transition: Transition):
        return self.prompt_summarize(self._text, transition=transition)

    async def think(self, focus: WheelSegment) -> list[Transition]:
        # Get the next segment in ta_cycle order
        next_ws = self._wheel.get_next_segment(focus)

        # noinspection PyArgumentList
        action_plan_dto = await self.constructive_convergence(focus=focus, next_ws=next_ws)

        # Get representative components for spiral transition (minus → plus)
        focus_t_minus_result = focus.t_minus.get()
        next_ws_t_plus_result = next_ws.t_plus.get()

        if not focus_t_minus_result or not next_ws_t_plus_result:
            # Missing required components - shouldn't happen for complete segments
            raise ValueError(
                f"Missing required components for spiral transition. "
                f"Focus segment {focus.side} T-: {focus_t_minus_result is not None}, "
                f"Next segment {next_ws.side} T+: {next_ws_t_plus_result is not None}"
            )

        source_comp, _ = focus_t_minus_result
        target_comp, _ = next_ws_t_plus_result

        # Query spiral for existing transition with same source/target components
        spiral_result = self._wheel.spiral.get()
        transition = None
        if spiral_result:
            spiral = spiral_result[0]
            spiral_transitions = [t for t, _ in spiral.transitions.all()]

            # Check for duplicate using shared helper
            transition = self.find_duplicate_transition(spiral_transitions, source_comp, target_comp)

        # Create rationale
        rationale = GraphRationale(
            text=action_plan_dto.action_plan,
        )
        rationale.save()

        if transition is None:
            # Create new transition
            transition = GraphTransition()
            transition.save()

            # Connect representative components (minus → plus)
            transition.source.connect(source_comp)
            transition.target.connect(target_comp)

            # Connect rationale to transition
            transition.rationales.connect(rationale)

            # Connect transition to spiral
            if spiral_result:
                spiral = spiral_result[0]
                spiral.transitions.connect(transition)
        else:
            # Add rationale to existing transition
            transition.rationales.connect(rationale)

        # noinspection PyArgumentList
        summary = await self.summarize(transition=transition)

        # Update rationale properties
        rationale.summary = summary.one_liner
        rationale.headline = summary.action_phrase
        rationale.save()

        # Return the transition we worked on (created or updated)
        return [transition]
