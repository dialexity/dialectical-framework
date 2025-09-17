import asyncio
from typing import List

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework import TransitionSegmentToSegment, Transformation, Rationale
from dialectical_framework.ai_dto.dialectical_components_deck_dto import \
    DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.dto_mapper import map_list_from_dto
from dialectical_framework.ai_dto.reciprocal_solution_dto import ReciprocalSolutionDto
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.directed_graph import DirectedGraph
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.synthesist.domain.wheel_segment import (ALIAS_T, ALIAS_T_MINUS,
                                                                   ALIAS_T_PLUS, WheelSegment)
from dialectical_framework.synthesist.domain.wisdom_unit import (ALIAS_A, ALIAS_A_MINUS,
                                                                 ALIAS_A_PLUS, WisdomUnit)


ALIAS_AC = "Ac"
ALIAS_AC_PLUS = "Ac+"
ALIAS_AC_MINUS = "Ac-"
ALIAS_RE = "Re"
ALIAS_RE_PLUS = "Re+"
ALIAS_RE_MINUS = "Re-"

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
    def ac_re_prompt(self, text: str, focus: WisdomUnit) -> Messages.Type:
        # TODO: do we want to include the whole wheel reengineered? Also transitions so far?
        wu = focus.model_copy(deep=True)
        wu.add_indexes_to_aliases(0)
        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": wu.pretty(),
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

        Step 3. Estimate the numeric probabilities (0 to 1) of Linear Action (Ac) and Dialectical Reflection (Re) happening.
        
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
            Linear Action Probability: 0.4

            Dialectical Reflection: Liquid staking derivatives for immediate utility (25%) combined with guaranteed exit rights (75%) - complements the linear action.
            Dialectical Reflection Probability: 0.6
        </example>
        </instructions>

        <formatting>
        Output Linear Action and Dialectical Reflection as a fluent text (not mentioning it's actually a Linear Action or Dialectical Reflection) that could be useful for someone who provided the initial context. Compose the problem statement in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
        Probabilities should be numbers between 0 and 1.
        </formatting>
        """
    )
    def reciprocal_solution_prompt(self, text: str, focus: WisdomUnit) -> Messages.Type:
        # TODO: do we want to include the whole wheel reengineered? Also transitions so far?
        wu = focus.model_copy(deep=True)
        wu.add_indexes_to_aliases(0)
        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": wu.pretty(),
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

    async def think(self, focus: WheelSegment) -> List[TransitionSegmentToSegment]:
        wu = self._wheel.wisdom_unit_at(focus)

        async_reasoning_threads = [
            self.action_reflection(focus=wu),
            self.reciprocal_solution(focus=wu)
        ]

        dc_deck_dto: DialecticalComponentsDeckDto
        reciprocal_sol_dto: ReciprocalSolutionDto
        dc_deck_dto, reciprocal_sol_dto  = await asyncio.gather(*async_reasoning_threads)

        ac_re_wu = WisdomUnit(
            reasoning_mode=DialecticalReasoningMode.ACTION_REFLECTION,
            rationales=[Rationale(text=reciprocal_sol_dto.problem)]
        )
        dialectical_components: list[DialecticalComponent] = map_list_from_dto(dc_deck_dto.dialectical_components, DialecticalComponent)
        for dc in dialectical_components:
            alias = self._translate_to_canonical_alias(dc.alias)
            setattr(ac_re_wu, alias, dc)

        graph = DirectedGraph[TransitionSegmentToSegment]()
        graph.add_transition(
            TransitionSegmentToSegment(
                predicate=Predicate.TRANSFORMS_TO,
                source_aliases=[wu.t_minus.alias, wu.t.alias],
                target_aliases=[wu.a_plus.alias],
                source=wu.extract_segment_t(),
                target=wu.extract_segment_a(),
                rationales=[
                    Rationale(
                        text=reciprocal_sol_dto.linear_action,
                        # TODO: is it ok to use self-assigned probability here? It somewhat contradicts the t-cycle probability, which overall should be the same for the spiral, no?
                        probability=reciprocal_sol_dto.linear_action_probability,
                    )
                ],
            )
        )
        graph.add_transition(
            TransitionSegmentToSegment(
                predicate=Predicate.TRANSFORMS_TO,
                source_aliases=[wu.a_minus.alias, wu.a.alias],
                target_aliases=[wu.t_plus.alias],
                source=wu.extract_segment_a(),
                target=wu.extract_segment_t(),
                rationales=[
                    Rationale(
                        text=reciprocal_sol_dto.dialectical_reflection,
                        # TODO: is it ok to use self-assigned probability here? It somewhat contradicts the t-cycle probability, which overall should be the same for the spiral, no?
                        probability=reciprocal_sol_dto.dialectical_reflection_probability,
                    )
                ],
            )
        )

        # TODO: maybe we should rather merge if there was a transformation already (e.g. as a separate rationale?)
        wu.transformation = Transformation(
            ac_re=ac_re_wu,
            graph=graph
        )

        # We return empty, because we're not merging anything, and we're sure there will be nothing to do with the result
        return []

    @staticmethod
    def _translate_to_canonical_alias(alias: str) -> str:
        if alias == ALIAS_AC:
            return ALIAS_T

        if alias == ALIAS_AC_PLUS:
            return ALIAS_T_PLUS

        if alias == ALIAS_AC_MINUS:
            return ALIAS_T_MINUS

        if alias == ALIAS_RE:
            return ALIAS_A

        if alias == ALIAS_RE_PLUS:
            return ALIAS_A_PLUS

        if alias == ALIAS_RE_MINUS:
            return ALIAS_A_MINUS

        return alias
