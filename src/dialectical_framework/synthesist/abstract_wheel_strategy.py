from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar, Generic

from dialectical_framework.synthesist.wheel2 import Wheel2

# It's important to use TypeVar so that Pydantic doesn't strip the extra fields
Wheel = TypeVar("Wheel", bound=Wheel2)

class AbstractWheelStrategy(Generic[Wheel], ABC):
    def __init__(self, text: str = None):
        self.text = text

    @abstractmethod
    async def expand(self, wheel: Wheel = None) -> Wheel: ...
    """
    Raises:
        ValueError - When the text is not provided to the strategy
        StopIteration - When the wheel is already fully expanded
    """