from __future__ import annotations

from typing import Type, TypeVar, Tuple

from dialectical_framework.synthesist.basic_wheel import BasicWheel
from dialectical_framework.synthesist.strategies.wheel2_semantic_contextualized_strategy import \
    Wheel2SemanticContextualizedStrategy
from dialectical_framework.synthesist.strategies.wheel2_simple_semantic_strategy import Wheel2SimpleSemanticStrategy
from dialectical_framework.synthesist.factories.wheel2_factory import Wheel2Factory

Wheel = TypeVar("Wheel", bound="BasicWheel")
WheelFactory = TypeVar("WheelFactory", bound="AbstractWheelFactory")
WheelStrategy = TypeVar("WheelStrategy", bound="AbstractWheelStrategy")

class WheelGenerator:
    _factory_registry: dict[Type[Wheel], Tuple[Type[WheelFactory], Type[WheelStrategy]]] = {
        BasicWheel: (Wheel2Factory, Wheel2SimpleSemanticStrategy)
        # BasicWheel: (Wheel2Factory, Wheel2SemanticContextualizedStrategy)
    }

    @staticmethod
    def instance(wheel_type: Type[Wheel]) -> WheelFactory:
        # Ensure the wheel type is registered
        if wheel_type not in WheelGenerator._factory_registry:
            raise ValueError(f"Wheel type '{wheel_type.__name__}' doesn't have a registered factory.")
        factory, strategy = WheelGenerator._factory_registry[wheel_type]
        return factory(strategy())