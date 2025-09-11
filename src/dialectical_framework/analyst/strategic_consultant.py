from abc import ABC, abstractmethod
from typing import Optional, List

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.brain import Brain
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.synthesist.domain.wheel import Wheel
from dialectical_framework.synthesist.domain.wheel_segment import WheelSegment


class StrategicConsultant(ABC, HasBrain):
    def __init__(
        self,
        *,
        text: str,
        wheel: Wheel,
        brain: Optional[Brain] = None,
    ):
        self._text = text
        self._wheel = wheel
        self._brain = brain

    @property
    def brain(self) -> Brain:
        return super().brain if self._brain is None else self._brain

    @abstractmethod
    async def think(self, focus: WheelSegment) -> Transition | List[Transition]: ...
    """
    The main method of the class. It should return a Transition to the next WisdomUnit.
    This Transition must be saved into the current instance. 
    """
