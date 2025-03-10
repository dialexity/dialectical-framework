from abc import ABC, abstractmethod
from typing import TypeVar, Generic

Wheel = TypeVar("Wheel", bound="BasicWheel")
WheelStrategy = TypeVar("WheelStrategy", bound="AbstractWheelStrategy")

class AbstractWheelFactory(ABC):
    def __init__(self, strategy: WheelStrategy):
        self._strategy = strategy

    @property
    def strategy(self) -> WheelStrategy:
        return self._strategy


    @abstractmethod
    async def generate(self, input_text: str) -> Wheel: ...
    """
    Subclasses must implement basic generation of a wheel from a given input text.
    """

    @abstractmethod
    async def redefine(self, input_text: str, original: Wheel, **modified_dialectical_components) -> Wheel: ...
    """
    Subclasses must implement the regeneration/adjustments of a wheel, provided that some components have been modified.
    The modifications are provided dialectical component names and their new values.
    Names are the fields of the BasicWheel class.
    
    @return: a copy of the original wheel with the modified components.
    """