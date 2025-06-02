from abc import ABC, abstractmethod

from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.utils.config import Config
from dialectical_framework.brain import Brain
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.symmetrical_transition import SymmetricalTransition, ALIAS_AC, ALIAS_AC_PLUS, ALIAS_AC_MINUS, ALIAS_RE, \
    ALIAS_RE_PLUS, ALIAS_RE_MINUS
from dialectical_framework.wisdom_unit import WisdomUnit, ALIAS_A, ALIAS_A_PLUS, \
    ALIAS_A_MINUS
from dialectical_framework.wheel_segment import ALIAS_T, ALIAS_T_PLUS, ALIAS_T_MINUS


class StrategicConsulting(ABC):
    def __init__(
        self,
        text: str,
        *,
        config: WheelBuilderConfig = None,
        wisdom_unit: WisdomUnit
    ):
        # TODO: one wisdom unit isn't enough, it should be actually based on the wheel, not on the wisdom unit
        self._text = text
        self._wisdom_unit = wisdom_unit

        if config is None:
            config = WheelBuilderConfig(
                component_length=4
            )

        self._component_length = config.component_length
        self._brain = config.brain

        self._transition = None

    @abstractmethod
    async def think(self, action: str | DialecticalComponent = None) -> SymmetricalTransition: ...
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