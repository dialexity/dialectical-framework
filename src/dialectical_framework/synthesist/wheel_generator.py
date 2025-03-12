from __future__ import annotations

from typing import Type, TypeVar

from dialectical_framework.synthesist.base_wheel import BaseWheel
from dialectical_framework.synthesist.factories.wheel2_base_factory import Wheel2BaseFactory
from dialectical_framework.synthesist.factories.wheel2_focused_conversation_factory import \
    Wheel2FocusedConversationFactory

Wheel = TypeVar("Wheel", bound="BasicWheel")
WheelFactory = TypeVar("WheelFactory", bound="AbstractWheelFactory")

class WheelGenerator:
    _factory_registry: dict[Type[Wheel], Type[WheelFactory]] = {
        BaseWheel: Wheel2BaseFactory,
        # BaseWheel: Wheel2FocusedConversationFactory,
    }

    @staticmethod
    def instance(wheel_type: Type[Wheel]) -> WheelFactory:
        # Ensure the wheel type is registered
        if wheel_type not in WheelGenerator._factory_registry:
            raise ValueError(f"Wheel type '{wheel_type.__name__}' doesn't have a registered factory.")
        factory = WheelGenerator._factory_registry[wheel_type]
        return factory()