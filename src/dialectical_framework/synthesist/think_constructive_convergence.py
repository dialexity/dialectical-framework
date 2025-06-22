
from mirascope import Messages, prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_components_deck import DialecticalComponentsDeck
from dialectical_framework.symmetrical_transition import SymmetricalTransition
from dialectical_framework.synthesist.strategic_consultant import StrategicConsultant
from dialectical_framework.transition import Transition
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wisdom_unit import WisdomUnit


class ThinkConstructiveConvergence(StrategicConsultant):
    @prompt_template(
    """
    USER:
    <context>{text}</context>
    
    USER:
    Previous Dialectical Analysis:
    {dialectical_analysis}
    
    Circular Causation:
    {circular_causation}
    
    USER:
    <instructions>
    Identify practical transition steps that show how to transform the negative/exaggerated side of {thesis1_alias} to the positive/constructive side of the {thesis2_alias}.
    
    1. Start with the negative (-) or neutral state of {thesis1_alias}, i.e. {thesis1_minus_alias} or {thesis1_alias}
    2. Identify concrete steps (in 2-3 words each) to reach {thesis2_plus_alias}
    </instructions>

    <formatting>
    Output the transition steps as a markdown bullet list. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
    </formatting>
    """
    )
    def prompt(self, text: str) -> Messages.Type:
        return {
            "computed_fields": {
                "text": text,
                "dialectical_analysis": self._wisdom_unit.pretty(),
                "component_length": self._component_length,
            }
        }

    @with_langfuse()
    async def constructive_convergence(self):
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
        )
        def _constructive_convergence() -> str:
            return self.prompt(self._text)

        return _constructive_convergence()

    async def think(self) -> TransitionSegmentToSegment:
        ...

