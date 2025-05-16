from abc import ABC, abstractmethod

from config import Config
from dialectical_framework.brain import Brain
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.transition import Transition, ALIAS_AC, ALIAS_AC_PLUS, ALIAS_AC_MINUS, ALIAS_RE, \
    ALIAS_RE_PLUS, ALIAS_RE_MINUS
from dialectical_framework.wisdom_unit import WisdomUnit, ALIAS_T, ALIAS_T_PLUS, ALIAS_T_MINUS, ALIAS_A, ALIAS_A_PLUS, \
    ALIAS_A_MINUS


class StrategicConsulting(ABC):
    def __init__(
        self,
        text: str,
        *,
        component_length=4,
        wisdom_unit: WisdomUnit
    ):
        # TODO: one wisdom unit isn't enough, it should be actually based on the wheel, not on the wisdom unit
        self._text = text
        self._wisdom_unit = wisdom_unit

        self._component_length = component_length

        # Default brain
        self._brain = Brain(ai_model=Config.MODEL, ai_provider=Config.PROVIDER)

        self._transition = None

    @abstractmethod
    async def think(self, action: str | DialecticalComponent = None) -> Transition: ...
    """
    The main method of the class. It should return a Transition to the next WisdomUnit.
    This Transition must be saved into the current instance. 
    """

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