from abc import ABC, abstractmethod

from dialectical_framework.brain import Brain
from dialectical_framework.config import Config
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.transition import Transition
from dialectical_framework.wheel import Wheel
from dialectical_framework.wheel_segment import WheelSegment


class StrategicConsultant(ABC, HasBrain):
    def __init__(
        self,
        *,
        text: str,
        brain: Brain,
        config: Config,
        wheel: Wheel,
    ):
        self._brain = brain
        self._text = text
        self._wheel = wheel
        self._config = config
        self._transition = None

    @property
    def config(self) -> Config:
        return self._config

    @abstractmethod
    async def think(self, focus: WheelSegment) -> Transition: ...

    """
    The main method of the class. It should return a Transition to the next WisdomUnit.
    This Transition must be saved into the current instance. 
    """
