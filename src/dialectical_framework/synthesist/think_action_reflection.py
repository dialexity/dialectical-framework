
from mirascope import Messages, prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.symmetrical_transition import SymmetricalTransition, ALIAS_AC, ALIAS_AC_PLUS, ALIAS_AC_MINUS, \
    ALIAS_RE, ALIAS_RE_PLUS, ALIAS_RE_MINUS
from dialectical_framework.synthesist.strategic_consultant import StrategicConsultant
from dialectical_framework.transition import Predicate
from dialectical_framework.wheel_segment import ALIAS_T, ALIAS_T_PLUS, ALIAS_T_MINUS, WheelSegment
from dialectical_framework.wisdom_unit import WisdomUnit, ALIAS_A, ALIAS_A_PLUS, ALIAS_A_MINUS, DialecticalReasoningMode


class ThinkActionReflection(StrategicConsultant):
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
                "component_length": self._component_length,
            }
        }

    @with_langfuse()
    async def action_reflection(self, focus: WisdomUnit):
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponentsDeck,
        )
        def _action_reflection_call() -> DialecticalComponentsDeck:
            return self.prompt(self._text, focus=focus)

        return _action_reflection_call()

    async def think(self, focus: WheelSegment) -> SymmetricalTransition:
        wu = self._wheel.wisdom_unit_at(focus)

        ac_re_wu = WisdomUnit(reasoning_mode=DialecticalReasoningMode.ACTION_REFLECTION)
        dc: DialecticalComponentsDeck = await self.action_reflection(focus=wu)
        for d in dc.dialectical_components:
            alias = self._translate_to_canonical_alias(d.alias)
            setattr(ac_re_wu, alias, d)

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

