from __future__ import annotations

import asyncio
from typing import List, Tuple

from gqlalchemy import Relationship
from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.reciprocal_solution_dto import ReciprocalSolutionDto
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

from dialectical_framework.graph.wheel_segment import WheelSegment
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
    POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS,
    WisdomUnit
)
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.rationale import Rationale


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
        # TODO: do we want to include the whole wheel reengineered? Also transitions so far?
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
        # TODO: do we want to include the whole wheel reengineered? Also transitions so far?
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

    async def think(self, focus: WheelSegment) -> list[Transition]:
        wu = self._wheel.wisdom_unit_at(focus)

        async_reasoning_threads = [
            self.action_reflection(focus=wu),
            self.reciprocal_solution(focus=wu)
        ]

        dc_deck_dto: DialecticalComponentsDeckDto
        reciprocal_sol_dto: ReciprocalSolutionDto
        dc_deck_dto, reciprocal_sol_dto  = await asyncio.gather(*async_reasoning_threads)

        # Create rationale for the AC/RE wisdom unit
        problem_rationale = Rationale(text=reciprocal_sol_dto.problem)
        problem_rationale.save()

        # Create AC/RE wisdom unit
        ac_re_wu = WisdomUnit(
            reasoning_mode=DialecticalReasoningMode.ACTION_REFLECTION,
        )
        ac_re_wu.save()

        # Connect rationale to wisdom unit
        ac_re_wu.rationales.connect(problem_rationale)

        # Get the current wu's human friendly index
        human_friendly_index = wu.get_human_friendly_index()

        # Convert DTOs to graph-native components and connect to ac_re wisdom unit
        # We iterate over DTOs (which have alias) and convert each one
        for dto in dc_deck_dto.dialectical_components:
            # Normalize to base alias (strip any index from LLM response)
            dto.set_human_friendly_index(0)  # "Ac1" → "Ac", "Re2+" → "Re+"

            # Translate AC/RE alias to canonical T/A position
            position = self._translate_alias_to_position(dto.alias)

            if human_friendly_index is not None:
                dto.set_human_friendly_index(human_friendly_index)  # Apply correct index

            # Convert DTO to graph-native component
            from dialectical_framework.ai_dto.graph_mapper import component_from_dto
            component = component_from_dto(dto)

            # Get the relationship manager for this position and connect component
            manager = ac_re_wu.get_relationship_manager_by_position(position)
            # Use the correct relationship class for this position
            rel_class = WisdomUnit.get_relationship_class_for_position(position)
            manager.connect(component, relationship=rel_class(alias=dto.alias))

        # Get components for transitions
        wu_t_minus_result = wu.t_minus.get()
        wu_a_plus_result = wu.a_plus.get()
        wu_a_minus_result = wu.a_minus.get()
        wu_t_plus_result = wu.t_plus.get()

        if not (wu_t_minus_result and wu_a_plus_result and wu_a_minus_result and wu_t_plus_result):
            # Missing required components - this shouldn't happen for a complete WU
            raise ValueError(
                f"WisdomUnit {wu.uid} is missing required components for transformation. "
                f"Has T-: {wu_t_minus_result is not None}, A+: {wu_a_plus_result is not None}, "
                f"A-: {wu_a_minus_result is not None}, T+: {wu_t_plus_result is not None}"
            )

        t_minus_comp, _ = wu_t_minus_result
        a_plus_comp, _ = wu_a_plus_result
        a_minus_comp, _ = wu_a_minus_result
        t_plus_comp, _ = wu_t_plus_result

        # Check if transformation already exists
        transformation_result: Tuple[Transformation, Relationship] = wu.transformation.get()

        if transformation_result:
            # Transformation exists - check for duplicates before creating new rationales
            transformation = transformation_result[0]
            existing_transitions = [t for t, _ in transformation.transitions.all()]

            transitions_updated = []

            # Transition 1: T- → A+
            duplicate1 = self.find_duplicate_transition(existing_transitions, t_minus_comp, a_plus_comp)
            if duplicate1:
                # Create and add rationale to existing transition
                rationale1 = Rationale(text=reciprocal_sol_dto.linear_action)
                rationale1.save()
                duplicate1.rationales.connect(rationale1)
                transitions_updated.append(duplicate1)
            # If no duplicate, transformation already has 2 transitions (cardinality 2,2), skip

            # Transition 2: A- → T+
            duplicate2 = self.find_duplicate_transition(existing_transitions, a_minus_comp, t_plus_comp)
            if duplicate2:
                # Create and add rationale to existing transition
                rationale2 = Rationale(text=reciprocal_sol_dto.dialectical_reflection)
                rationale2.save()
                duplicate2.rationales.connect(rationale2)
                transitions_updated.append(duplicate2)
            # If no duplicate, transformation already has 2 transitions (cardinality 2,2), skip

            # Return the transitions we updated with new rationales
            return transitions_updated
        else:
            # No transformation exists - create new transformation with transitions
            # Transition 1: T- → A+
            rationale1 = Rationale(text=reciprocal_sol_dto.linear_action)
            rationale1.save()

            transition1 = Transition()
            transition1.save()
            transition1.source.connect(t_minus_comp)
            transition1.target.connect(a_plus_comp)
            transition1.rationales.connect(rationale1)

            # Transition 2: A- → T+
            rationale2 = Rationale(text=reciprocal_sol_dto.dialectical_reflection)
            rationale2.save()

            transition2 = Transition()
            transition2.save()
            transition2.source.connect(a_minus_comp)
            transition2.target.connect(t_plus_comp)
            transition2.rationales.connect(rationale2)

            # Create transformation
            transformation = Transformation()
            transformation.save()

            # Connect ac_re wisdom unit to transformation
            transformation.ac_re.connect(ac_re_wu)

            # Connect transformation to wisdom unit
            wu.transformation.connect(transformation)

            # Connect transitions to transformation
            transformation.transitions.connect(transition1)
            transformation.transitions.connect(transition2)

            # Return newly created transitions
            return [transition1, transition2]


    @staticmethod
    def _translate_alias_to_position(alias: str) -> str:
        """
        Translate Action-Reflection aliases to canonical WisdomUnit position strings.

        Maps AC/RE aliases to position constants:
        - Ac → T, Ac+ → T+, Ac- → T-
        - Re → A, Re+ → A+, Re- → A-

        Args:
            alias: Action-Reflection alias (Ac, Ac+, Ac-, Re, Re+, Re-)
                  Should be normalized (no numeric index) before calling

        Returns:
            WisdomUnit position string (T, T+, T-, A, A+, A-) for use with get_relationship_manager_by_position()
        """
        if alias == "Ac":
            return POSITION_T

        if alias == "Ac+":
            return POSITION_T_PLUS

        if alias == "Ac-":
            return POSITION_T_MINUS

        if alias == "Re":
            return POSITION_A

        if alias == "Re+":
            return POSITION_A_PLUS

        if alias == "Re-":
            return POSITION_A_MINUS

        return alias
