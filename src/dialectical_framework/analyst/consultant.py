from abc import ABC, abstractmethod
from typing import Optional

from dialectical_framework.analyst.domain.transition import Transition
from dialectical_framework.brain import Brain
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.synthesist.domain.wheel import Wheel


class Consultant(ABC, HasBrain):
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
    async def rationalize(self, transition: Transition) -> Transition: ...
    """
    The main method of the class. It should return an enriched Transition with the new rationale.
    """
