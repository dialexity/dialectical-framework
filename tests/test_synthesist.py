from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.basic_wheel import BasicWheel
from dialectical_framework.synthesist.wheel_generator import WheelGenerator

user_message = "Love"

def test_wheel_generator():
    factory = WheelGenerator.instance(BasicWheel)
    wheel2: BaseModel = factory.generate(user_message)
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(wheel2)

def test_wheel_redefine():
    # Precalculated by gpt-4o
    wheel2 = BasicWheel(
        t_minus=DialecticalComponent.from_str('Mental Preoccupation'),
        t=DialecticalComponent.from_str('Love'),
        t_plus=DialecticalComponent.from_str('Compassionate Connection'),
        a_minus=DialecticalComponent.from_str('Nihilistic Detachment'),
        a=DialecticalComponent.from_str('Indifference'),
        a_plus=DialecticalComponent.from_str('Mindful Detachment')
    )

    # Redefine every component of the wheel, to make it an extreme test
    factory = WheelGenerator.instance(BasicWheel)
    redefined_wheel2 = factory.redefine(
        user_message,
        wheel2,
        t_minus='Mental Preoccupation',
        t='Love',
        t_plus='Compassionate Connection',
        a_minus='Nihilistic Detachment',
        a='Indifference',
        a_plus='Mindful Detachment'
    )
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(redefined_wheel2)