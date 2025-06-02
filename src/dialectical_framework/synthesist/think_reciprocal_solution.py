from mirascope import Messages, prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.reciprocal_solution import ReciprocalSolution
from dialectical_framework.synthesist.strategic_consulting import StrategicConsulting
from dialectical_framework.symmetrical_transition import SymmetricalTransition


class ThinkReciprocalSolution(StrategicConsulting):
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
    Output Linear Action and Dialectical Reflection as a fluent text that could be useful for someone who provided the initial context. Compose the problem statement in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
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
    async def reciprocal_solution(self):
        overridden_ai_provider, overridden_ai_model = self._brain.specification()
        if overridden_ai_provider == "bedrock":
            # TODO: with Mirascope v2 async should be possible with bedrock, so we should get rid of fallback to litellm
            # Issue: https://github.com/boto/botocore/issues/458, fallback to "litellm"
            overridden_ai_provider, overridden_ai_model = self._brain.modified_specification(ai_provider="litellm")

        @llm.call(
            provider=overridden_ai_provider,
            model=overridden_ai_model,
            response_model=ReciprocalSolution,
        )
        def _reciprocal_solution_call() -> ReciprocalSolution:
            return self.prompt(self._text)

        return _reciprocal_solution_call()

    async def think(self, action: str | DialecticalComponent = None) -> SymmetricalTransition:
        # TODO: take provided action into account, now it's ignored

        s: ReciprocalSolution = await self.reciprocal_solution()
        self._transition = SymmetricalTransition(
            reciprocal_solution=s
        )

        return self._transition

