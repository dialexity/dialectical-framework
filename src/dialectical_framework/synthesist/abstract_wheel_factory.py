from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, get_origin, get_args, Type

from dialectical_framework.synthesist.abstract_wheel_strategy import AbstractWheelStrategy
from dialectical_framework.synthesist.wheel2 import Wheel2

# It's important to use TypeVar so that Pydantic doesn't strip the extra fields
Wheel = TypeVar("Wheel", bound=Wheel2)
WheelStrategy = TypeVar("WheelStrategy", bound=AbstractWheelStrategy)

class AbstractWheelFactory(ABC, Generic[WheelStrategy, Wheel]):
    def __init__(self, strategy: WheelStrategy = None):
        if strategy is None:
            # Dynamically determine the strategy class using reflection
            strategy_cls = self._get_strategy_cls()
            self._strategy = strategy_cls()
        else:
            self._strategy = strategy

    def _get_strategy_cls(self) -> Type[AbstractWheelStrategy]:
        """
        Raises:
            TypeError: If the strategy class cannot be determined.
        """
        if hasattr(self, '__orig_bases__'):
            # Iterate through the base classes to find the generic type arguments
            for base in self.__orig_bases__:
                origin_args = get_args(base)
                if origin_args:
                    strategy_cls = origin_args[0]  # The first type argument is the strategy
                    if issubclass(strategy_cls, AbstractWheelStrategy):
                        return strategy_cls
        raise TypeError("Cannot determine the strategy class dynamically.")

    @property
    def strategy(self) -> WheelStrategy:
        return self._strategy


    async def generate(self, input_text: str) -> Wheel:
        """
        Subclasses must implement basic generation of a wheel from a given input text.
        """
        self.strategy.text = input_text
        wheel = await self.strategy.expand()

        try:
            for _ in range(len(wheel.__class__.__pydantic_fields__) - 1):
                wheel = await self.strategy.expand(wheel)
        except StopIteration:
            pass

        return wheel

    @abstractmethod
    async def redefine(self, input_text: str, original: Wheel, **modified_dialectical_components) -> Wheel: ...
    """
    Subclasses must implement the regeneration/adjustments of a wheel, provided that some components have been modified.
    The modifications are provided dialectical component names and their new values.
    Names are the fields of the BasicWheel class.
    
    @return: a copy of the original wheel with the modified components.
    """