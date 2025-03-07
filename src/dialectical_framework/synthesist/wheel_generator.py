from __future__ import annotations

from typing import Type, TypeVar

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.basic_wheel import BasicWheel
from dialectical_framework.synthesist.wheel_factories.abstract_wheel_factory import AbstractWheelFactory
from dialectical_framework.synthesist.wheel_factories.basic_wheel_factory import BasicWheelFactory

BasicWheelWithSubTypes = TypeVar("BasicWheelWithSubTypes", bound="BasicWheel")
WheelFactory = TypeVar("WheelFactory", bound="AbstractWheelFactory")

class WheelGenerator:
    _factory_registry: dict[Type[BasicWheelWithSubTypes], Type[WheelFactory]] = {
        BasicWheel: BasicWheelFactory
    }

    @staticmethod
    def instance(wheel_type: Type[BasicWheelWithSubTypes]) -> AbstractWheelFactory:
        # Ensure the wheel type is registered
        if wheel_type not in WheelGenerator._factory_registry:
            raise ValueError(f"Wheel type '{wheel_type.__name__}' doesn't have a registered factory.")
        factory = WheelGenerator._factory_registry[wheel_type]
        return factory()