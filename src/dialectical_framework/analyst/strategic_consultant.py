from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Optional, List

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment

from dialectical_framework.brain import Brain
from dialectical_framework.protocols.has_brain import HasBrain


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
