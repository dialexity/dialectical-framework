from mirascope import Messages, prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_box import DialecticalComponentsBox
from dialectical_framework.synthesist.strategic_consulting import StrategicConsulting
from dialectical_framework.transition import Transition
from dialectical_framework.wisdom_unit import WisdomUnit


class ThinkActionReflection(StrategicConsulting):
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
    def prompt(self, text: str) -> Messages.Type:
        wu_formatted = []
        for f, a in self._wisdom_unit.field_to_alias.items():
            dc = getattr(self._wisdom_unit, f)
            if isinstance(dc, DialecticalComponent):
                dc_formatted = f"{a} = {dc.statement}"
                if dc.explanation:
                    dc_formatted += f". Explanation: {dc.explanation}"
                wu_formatted.append(dc_formatted)
        dialectical_analysis = "\n\n".join(wu_formatted)

        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": dialectical_analysis,
                "component_length": self._component_length,
            }
        }

    @with_langfuse()
    async def action_reflection(self):
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallbck to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=DialecticalComponentsBox,
        )
        async def _action_reflection_call() -> DialecticalComponentsBox:
            return self.prompt(self._text)

        return await _action_reflection_call()

    async def think(self, action: str | DialecticalComponent = None) -> Transition:
        wu = WisdomUnit()

        # TODO: take provided action into account, now it's ignored

        dc: DialecticalComponentsBox = await self.action_reflection()
        for d in dc.dialectical_components:
            alias = self._translate_to_canonical_alias(d.alias)
            # TODO: we have canonical alias pointing to a component with some fancy alias. Is it ok?
            setattr(wu, alias, d)

        self._transition = Transition(
            action_reflection=wu
        )

        return self._transition

