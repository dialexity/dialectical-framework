from typing import Callable, cast

from mirascope import llm, prompt_template
from mirascope.integrations.langfuse import with_langfuse
from mirascope.llm import CallResponse

from config import Config
from dialectical_framework.validator.check import Check


def is_yes_parser(resp: CallResponse) -> bool:
    return "YES" in resp.content[:3].upper()


@prompt_template(
"""
DIALECTICAL OPPOSITION:

A dialectical opposition presents the conceptual or functional antithesis of the original statement that creates direct opposition, while potentially still allowing their mutual coexistence. For instance, Love vs. Hate or Indifference; Science vs. Superstition, Faith/Belief; Human-caused Global Warming vs. Natural Cycles.

Can the statement "{antithesis}" be considered a valid dialectical opposition of statement "{thesis}"?

Start answering with YES or NO. If NO, then provide a correct example. Explain your answer.
"""
)
def is_valid_opposition(antithesis: str, thesis: str) -> bool: ...


@prompt_template(
"""
CONTRADICTORY/SEMANTIC OPPOSITION:

A contradictory/semantic opposition presents a direct semantic opposition and/or contradiction to the original statement that excludes their mutual coexistence. For instance, Happiness vs. Unhappiness; Truthfulness vs. Lie/Deceptiveness; Dependence vs. Independence

Can the statement "{opposition}" be considered as a contradictory/semantic opposition of "{statement}"?

Start answering with YES or NO. If NO, then provide a correct example. Explain your answer.
"""
)
def is_strict_opposition(opposition: str, statement: str) -> bool: ...


@prompt_template(
"""
Can the statement "{negative_side}" be considered as an exaggerated (overdeveloped, negative) side or outcome of the statement "{statement}"?

Start answering with YES or NO. If NO, then provide a correct example. Explain your answer.
"""
)
def is_negative_side(negative_side: str, statement: str) -> bool: ...


@prompt_template(
"""
Can the statement "{positive_side}" be considered as a positive (constructive and balanced) side of the statement "{statement}"?

Start answering with YES or NO. If NO, then provide a correct example. Explain your answer.
"""
)
def is_positive_side(positive_side: str, statement: str) -> bool: ...


@with_langfuse()
@llm.call(provider=Config.PROVIDER, model=Config.MODEL, response_model=Check)
def check(func: Callable[[str, str], bool], statement1: str, statement2: str) -> Check:
    return cast(Check, func(statement1, statement2))
