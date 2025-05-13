import inspect

from mirascope import Messages, prompt_template

from config import Config
from dialectical_framework.synthesist.reasoner_fast import ReasonerFast


class ReasonerFastAndSimple(ReasonerFast):
    def __init__(self, text: str, *, ai_model: str = Config.MODEL, ai_provider: str | None = Config.PROVIDER, component_length = 4) -> None:
        super().__init__(text, ai_model=ai_model, ai_provider=ai_provider)
        self._component_length = component_length

    @prompt_template()
    def prompt_wu(self, text: str) -> Messages.Type:
        component_length = self._component_length
        messages = [
            Messages.User(inspect.cleandoc(
                f"""<context>
                {text}
                </context>"""
            )),
            Messages.User(inspect.cleandoc(f"""
            # Dialectical Analysis

            <instructions>
            In the given context, identify the most important single thesis (idea, concept) T.

            Identify its semantic/functional antithesis (A), such that positive/constructive side of thesis (T+) should oppose/contradict the negative/exaggerated side of antithesis (A-), while negative/exaggerated side of thesis (T-) should oppose/contradict the positive/constructive side of antithesis (A+). 

            For example:
            T = Love
            T+ = Happiness (positive aspect of Love)
            T- = Fixation (negative aspect of Love)
            A = Indifference (antithesis of Love)
            A+ = Objectivity (positive aspect of Indifference, contradicts Fixation)
            A- = Misery (negative aspect of Indifference, contradicts Happiness).
            </instructions>

            <formatting>
            Output the dialectical components within {component_length} words, the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", etc.
            </formatting>
            """))

        ]
        return {
            "messages" : messages,
            # For tracking/logging purposes, because they're injected directly
            "computed_fields" : {
                "text" : text,
                "component_length" : component_length,
            }
        }