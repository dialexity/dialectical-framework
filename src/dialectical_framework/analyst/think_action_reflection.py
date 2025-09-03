from typing import List

from mirascope import Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.ai_dto.dialectical_components_deck_dto import DialecticalComponentsDeckDto
from dialectical_framework.ai_dto.dto_mapper import map_from_dto, map_list_from_dto
from dialectical_framework.analyst.strategic_consultant import \
    StrategicConsultant
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.enums.dialectical_reasoning_mode import \
    DialecticalReasoningMode
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.symmetrical_transition import (
    ALIAS_AC, ALIAS_AC_MINUS, ALIAS_AC_PLUS, ALIAS_RE, ALIAS_RE_MINUS,
    ALIAS_RE_PLUS, SymmetricalTransition)
from dialectical_framework.enums.predicate import Predicate
from dialectical_framework.utils.use_brain import use_brain
from dialectical_framework.wheel_segment import (ALIAS_T, ALIAS_T_MINUS,
                                                 ALIAS_T_PLUS, WheelSegment)
from dialectical_framework.wisdom_unit import (ALIAS_A, ALIAS_A_MINUS,
                                               ALIAS_A_PLUS, WisdomUnit)


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
    @use_brain(response_model=DialecticalComponentsDeckDto)
    async def action_reflection(self, focus: WisdomUnit):
        return self.prompt(self._text, focus=focus)

    async def think(self, focus: WheelSegment) -> SymmetricalTransition:
        wu = self._wheel.wisdom_unit_at(focus)

        ac_re_wu = WisdomUnit(reasoning_mode=DialecticalReasoningMode.ACTION_REFLECTION)
        dc_deck_dto: DialecticalComponentsDeckDto = await self.action_reflection(focus=wu)
        dialectical_components: List[DialecticalComponent] = map_list_from_dto(dc_deck_dto.dialectical_components, DialecticalComponent)
        for dc in dialectical_components:
            alias = self._translate_to_canonical_alias(dc.alias)
            setattr(ac_re_wu, alias, dc)

        self._transition = SymmetricalTransition(
            action_reflection=ac_re_wu,
            source_aliases=[wu.t.alias],
            target_aliases=[wu.a.alias],
            opposite_source_aliases=[wu.a.alias],
            opposite_target_aliases=[wu.t.alias],
            source=wu.extract_segment_t(),
            target=wu.extract_segment_a(),
            predicate=Predicate.TRANSFORMS_TO,
        )

        return self._transition

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
