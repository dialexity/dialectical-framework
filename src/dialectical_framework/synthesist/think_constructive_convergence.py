from mirascope import Messages, prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.synthesist.factories.reverse_engineering import ReverseEngineering
from dialectical_framework.synthesist.strategic_consultant import StrategicConsultant
from dialectical_framework.transition_segment_to_segment import TransitionSegmentToSegment
from dialectical_framework.wheel_segment import WheelSegment


class ThinkConstructiveConvergence(StrategicConsultant):
    @prompt_template(
    """
    MESSAGES:
    {wheel_construction}
    
    USER:
    <instructions>
    Identify practical transition steps that show how to transform the negative/exaggerated side of {from_alias} to the positive/constructive side of the {to_alias}.
    
    1. Start with the negative (-) or neutral state of {from_alias}, i.e. {from_minus_alias} or {from_alias}
    2. Identify concrete steps (in 2-3 words each) to reach {to_plus_alias}
    </instructions>

    <formatting>
    Output the transition steps as a markdown bullet list. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
    </formatting>
    """)
    def prompt(self, text: str, focus: WheelSegment, next_ws: WheelSegment) -> Messages.Type:
        # TODO: do we want to include transitions that are already present in the wheel?
        return {
            "computed_fields": {
                "wheel_construction": ReverseEngineering.wheel(text=text, wheel=self._wheel),
                "from_alias": focus.t.alias,
                "from_minus_alias": focus.t_minus.alias,
                "to_alias": next_ws.t.alias,
                "to_plus_alias": next_ws.t_plus.alias,
            }
        }

    @with_langfuse()
    async def constructive_convergence(self, focus: WheelSegment, next_ws: WheelSegment):
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=str,
        )
        def _constructive_convergence() -> str:
            return self.prompt(self._text, focus=focus, next_ws=next_ws)

        return _constructive_convergence()

    async def think(self, focus: WheelSegment) -> TransitionSegmentToSegment:
        current_index = self._wheel.index_of(focus)
        next_index = (current_index + 1) % self._wheel.degree
        next_ws = self._wheel.wheel_segment_at(next_index)
        
        self._transition = TransitionSegmentToSegment(
            predicate="constructively_converges_to",
            source_aliases=[focus.t_minus.alias, focus.t.alias],
            target_aliases=[next_ws.t_plus.alias],
            source=focus,
            target=next_ws,
            text=await self.constructive_convergence(focus=focus, next_ws=next_ws),
        )

        return self._transition