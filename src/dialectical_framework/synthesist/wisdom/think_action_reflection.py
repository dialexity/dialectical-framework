from __future__ import annotations

import asyncio

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.reciprocal_solution_dto import ReciprocalSolutionDto
from dialectical_framework.synthesist.wisdom.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

from dialectical_framework.graph.wheel_segment import WheelSegment
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.transformation import (
    Transformation,
    POSITION_AC,
    POSITION_RE,
    POSITION_AC_PLUS,
    POSITION_AC_MINUS,
    POSITION_RE_PLUS,
    POSITION_RE_MINUS,
)
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.rationale import Rationale

# Mapping from Transformation position to (WU source position, WU target position)
# Each Transformation position is a Transition showing how to navigate the T-A tension
POSITION_TO_WU_MAPPING: dict[str, tuple[str, str]] = {
    POSITION_AC: ('t', 'a'),           # T → A
    POSITION_RE: ('a', 't'),           # A → T
    POSITION_AC_PLUS: ('t_minus', 'a_plus'),   # T- → A+
    POSITION_AC_MINUS: ('t_plus', 'a_minus'),  # T+ → A-
    POSITION_RE_PLUS: ('a_minus', 't_plus'),   # A- → T+
    POSITION_RE_MINUS: ('a_plus', 't_minus'),  # A+ → T-
}


class ThinkActionReflection(StrategicConsultant, SettingsAware):
    @prompt_template(
        """
        USER:
        <context>{text}</context>

        USER:
        Previous Dialectical Analysis:
        {dialectical_analysis}

        USER:
        <instructions>
        Given the initial context and the previous dialectical analysis, identify the transition steps Ac and Re that transform T and A into each other as follows:
        1) Ac must transform T into A
        2) Ac+ must transform T- and/or T into A+
        3) Ac- must transform T+ and/or T into A-
        4) Re must transform A into T
        5) Re+ must transform A- and/or A into T+
        6) Re- must transform A+ and/or A into T-
        7) Re+ must oppose/contradict Ac-
        8) Re- must oppose/contradict Ac+
        </instructions>

        <formatting>
        Output each transition step within {component_length} word(s), the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
        </formatting>
        """
    )
    def ac_re_prompt(self, text: str, focus: WisdomUnit) -> "Messages.Type":
        # Use strip_index mode to avoid LLM responding with indexed aliases (Ac1, Re2+)
        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": f"{focus:strip_index}",
                "component_length": self.settings.component_length,
            }
        }

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
        Output Linear Action and Dialectical Reflection as a fluent text (not mentioning it's actually a Linear Action or Dialectical Reflection) that could be useful for someone who provided the initial context. Compose the problem statement in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
        </formatting>
        """
    )
    def reciprocal_solution_prompt(self, text: str, focus: WisdomUnit) -> "Messages.Type":
        # Use strip_index mode to avoid LLM responding with indexed aliases (Ac1, Re2+)
        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": f"{focus:strip_index}",
                "component_length": self.settings.component_length,
            }
        }

    @with_langfuse()
    @use_brain(
        response_model=ReciprocalSolutionDto,
    )
    async def reciprocal_solution(self, focus: WisdomUnit):
        return self.reciprocal_solution_prompt(self._text, focus=focus)

    @with_langfuse()
    @use_brain(response_model=DialecticalComponentsDeckDto)
    async def action_reflection(self, focus: WisdomUnit):
        return self.ac_re_prompt(self._text, focus=focus)

    async def think(self, focus: WheelSegment) -> Transformation:
        """
        Calculate action-reflection transformation for a wisdom unit.

        Creates a Transformation with 6 positions (Ac, Re, Ac+, Ac-, Re+, Re-)
        that captures how the WisdomUnit's T-A tension can be navigated.

        Args:
            focus: The wheel segment identifying the WU to process

        Returns:
            The created Transformation
        """
        wu = self._wheel.wisdom_unit_at(focus)

        # Run LLM calls in parallel
        dc_deck_dto: DialecticalComponentsDeckDto
        reciprocal_sol_dto: ReciprocalSolutionDto
        dc_deck_dto, reciprocal_sol_dto = await asyncio.gather(
            self.action_reflection(focus=wu),
            self.reciprocal_solution(focus=wu)
        )

        # Get the current wu's human friendly index
        human_friendly_index = wu.get_human_friendly_index()

        # Create Transformation with 6 positions (no separate ac_re_wu)
        transformation = Transformation(intent="action_reflection")
        transformation.set_wisdom_unit(wu)
        transformation.save()  # HEAD state - no hash yet

        # Get WU components for Transition source/target
        wu_components = {
            't': wu.t.get()[0] if wu.t.get() else None,
            'a': wu.a.get()[0] if wu.a.get() else None,
            't_plus': wu.t_plus.get()[0] if wu.t_plus.get() else None,
            't_minus': wu.t_minus.get()[0] if wu.t_minus.get() else None,
            'a_plus': wu.a_plus.get()[0] if wu.a_plus.get() else None,
            'a_minus': wu.a_minus.get()[0] if wu.a_minus.get() else None,
        }

        # Create Transitions from LLM-generated descriptions
        for dto in dc_deck_dto.dialectical_components:
            # Normalize to base alias (strip any index from LLM response)
            dto.set_human_friendly_index(0)  # "Ac1" → "Ac", "Re2+" → "Re+"

            # Get the position from alias - now direct mapping (no translation needed)
            position = dto.alias  # "Ac", "Ac+", "Re-", etc.

            # Get source/target from WU based on position mapping
            if position not in POSITION_TO_WU_MAPPING:
                continue  # Skip unknown positions

            source_pos, target_pos = POSITION_TO_WU_MAPPING[position]
            source = wu_components.get(source_pos)
            target = wu_components.get(target_pos)

            if not source or not target:
                continue  # Skip if WU doesn't have required components

            # Create Transition for this position
            transition = Transition()
            transition.set_source(source)
            transition.set_target(target)
            transition.commit()

            # Attach LLM-generated text as Rationale on the Transition
            trans_rationale = Rationale(text=dto.statement)
            trans_rationale.set_explanation_target(transition)
            trans_rationale.commit()

            # Restore human-friendly index for alias
            if human_friendly_index is not None:
                dto.set_human_friendly_index(human_friendly_index)

            # Connect Transition to Transformation position
            manager = transformation.get_relationship_manager_by_position(position)
            rel_class = Transformation.get_relationship_class_for_position(position)
            manager.connect(transition, relationship=rel_class(alias=dto.alias))

        # Commit transformation now that transitions are connected
        transformation.commit()

        # Create rationale for the transformation (problem framing)
        rationale = Rationale(text=reciprocal_sol_dto.problem)
        rationale.set_explanation_target(transformation)
        rationale.commit()

        return transformation
