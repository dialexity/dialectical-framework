from __future__ import annotations

from typing import Type, Union, get_args

from dialectical_framework.synthesist.abstract_wheel_factory import AbstractWheelFactory
from dialectical_framework.synthesist.abstract_wheel_strategy import AbstractWheelStrategy
from dialectical_framework.synthesist.factories.wheel2_factory import Wheel2Factory
from dialectical_framework.wheel2 import Wheel2


class WheelGenerator:
    _factory_registry: dict[Type[Wheel2], Type[AbstractWheelFactory]] = {
        Wheel2: Wheel2Factory,
    }

    @staticmethod
    def instance(chosen_strategy: Union[Type[Wheel2], Type[AbstractWheelStrategy], AbstractWheelStrategy]) -> AbstractWheelFactory:
        wheel_type = None
        if issubclass(chosen_strategy, Wheel2):
            wheel_type = chosen_strategy

        if issubclass(chosen_strategy, AbstractWheelStrategy):
            chosen_strategy = chosen_strategy()

        if isinstance(chosen_strategy, AbstractWheelStrategy):
            if hasattr(chosen_strategy, '__orig_bases__'):
                # Iterate through the base classes to find the generic type arguments
                for base in chosen_strategy.__orig_bases__:
                    origin_args = get_args(base)
                    if origin_args:
                        wheel_cls = origin_args[0]  # The first type argument is the strategy
                        if issubclass(wheel_cls, Wheel2):
                            wheel_type = wheel_cls
                            break
        else:
            chosen_strategy = None

        # Ensure the wheel type is registered
        if wheel_type is not None and wheel_type not in WheelGenerator._factory_registry:
            raise ValueError(f"Wheel type for '{wheel_type.__name__}' doesn't have a registered factory.")
        elif wheel_type is None:
            raise ValueError("Wheel type is not found.")

        factory = WheelGenerator._factory_registry[wheel_type]
        return factory(chosen_strategy)