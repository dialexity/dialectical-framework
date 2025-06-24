from abc import ABC, abstractmethod

from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.transition import Transition
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class StrategicConsultant(ABC):
    def __init__(
        self,
        text: str,
        *,
        config: ConfigWheelBuilder = None,
        wheel: Wheel,
    ):
        # TODO: one wisdom unit isn't enough, it should be actually based on the wheel, not on the wisdom unit
        self._text = text
        self._wheel = wheel

        if config is None:
            config = ConfigWheelBuilder(
                component_length=4
            )

        self._component_length = config.component_length
        self._brain = config.brain

        self._transition = None

    @abstractmethod
    async def think(self, focus: WheelSegment) -> Transition: ...
    """
    The main method of the class. It should return a Transition to the next WisdomUnit.
    This Transition must be saved into the current instance. 
    """