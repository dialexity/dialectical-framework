import inspect

from mirascope import Messages, prompt_template

from config import Config
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.reasoner_fast_and_simple import ReasonerFastAndSimple
from dialectical_framework.wisdom_unit import WisdomUnit, ALIAS_T, ALIAS_T_PLUS, ALIAS_T_MINUS, ALIAS_A, ALIAS_A_PLUS, \
    ALIAS_A_MINUS

ALIAS_AC = "Ac"
ALIAS_AC_PLUS = "Ac+"
ALIAS_AC_MINUS = "Ac-"
ALIAS_RE = "Re"
ALIAS_RE_PLUS = "Re+"
ALIAS_RE_MINUS = "Re-"

class ReasonerFastAndSimpleActionReflection(ReasonerFastAndSimple):
    def __init__(self, text: str, *, ai_model: str = Config.MODEL, ai_provider: str | None = Config.PROVIDER, component_length = 4, wisdom_unit: WisdomUnit) -> None:
        super().__init__(text, ai_model=ai_model, ai_provider=ai_provider, component_length=component_length)
        self._wisdom_unit = wisdom_unit
    @prompt_template()
    def prompt_wu(self, text: str) -> Messages.Type:
        component_length = self._component_length

        wu_formatted = []
        for f, a in self._wisdom_unit.field_to_alias.items():
            dc = getattr(self._wisdom_unit, f)
            if isinstance(dc, DialecticalComponent):
                dc_formatted = f"{a} = {dc.statement}"
                if dc.explanation:
                    dc_formatted += f". Explanation: {dc.explanation}"
                wu_formatted.append(dc_formatted)
        dialectical_analysis = "\n\n".join(wu_formatted)

        messages = [
            Messages.User(inspect.cleandoc(
                f""""<context>
                {text}
                </context>"""
            )),
            Messages.User(inspect.cleandoc(
                f""""<context>
                Previous Dialectical Analysis:
                {dialectical_analysis}
                </context>"""
            )),
            Messages.User(inspect.cleandoc(
            f"""
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
            Output each transition step within {component_length} words, the shorter, the better. Compose the explanations how they were derived in the passive voice. Don't mention any special denotations such as "T", "T+", "A-", "Ac", "Re", etc.
            </formatting>
            """
            ))
        ]

        return {
            "messages" : messages,
            # For tracking/logging purposes, because they're injected directly
            "computed_fields": {
                "text": text,
                "dialectical_analysis": dialectical_analysis,
                "component_length": component_length,
            }
        }

    async def generate(self, action: str | DialecticalComponent = None) -> WisdomUnit:
        wu = WisdomUnit()

        if action is not None:
            if isinstance(action, DialecticalComponent):
                if action.alias != ALIAS_AC:
                    raise ValueError(
                        f"The thesis cannot be a dialectical component with alias '{action.alias}'"
                    )
                wu.t = action
            else:
                wu.t = DialecticalComponent.from_str(
                    ALIAS_AC, action, "Provided as string"
                )

        await self._fill_with_reason(wu)

        self._wisdom_unit = wu
        return self._wisdom_unit

    def _translate_to_canonical_alias(self, alias: str) -> str:
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

        return super()._translate_to_canonical_alias(alias)

