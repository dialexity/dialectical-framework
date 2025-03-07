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



if __name__ == "__main__":
    # user_message = "I'm in love with you, what else can I say..."
    user_message = "Love"
    factory = WheelGenerator.instance(BasicWheel)
    # half_wheel = factory.generate(user_message)
    # print(half_wheel)
    # print("\n=========================================================\n")
    half_wheel = BasicWheel(
        t_minus=DialecticalComponent.from_str("Blind obsession consumes and destroys rational thought and personal autonomy."),
        t=DialecticalComponent.from_str('Love governs human emotional experience.'),
        t_plus=DialecticalComponent.from_str('Compassionate understanding nurtures authentic connections and emotional growth.'),
        a_minus=DialecticalComponent.from_str('Paralyzing terror annihilates all capacity for rational response and emotional equilibrium.'),
        a=DialecticalComponent.from_str('Fear controls human emotional responses.'),
        a_plus=DialecticalComponent.from_str('Authentic emotional awareness cultivates deep understanding and meaningful connections.')
    )
    redefined_half_wheel = factory.redefine(user_message, half_wheel, a="Love is bad")
    print(redefined_half_wheel)
