from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.basic_wheel import BasicWheel
from dialectical_framework.synthesist.wheel_generator import WheelGenerator

user_message = "Love"

def test_wheel_generator():
    factory = WheelGenerator.instance(BasicWheel)
    half_wheel: BaseModel = factory.generate(user_message)
    assert all(v is not None for v in half_wheel.model_dump(exclude_none=False).values())
    print(half_wheel)

def test_wheel_redefine():
    # Precalculated by gpt-4o
    half_wheel = BasicWheel(
        t_minus=DialecticalComponent.from_str('Mental Preoccupation'),
        t=DialecticalComponent.from_str('Love'),
        t_plus=DialecticalComponent.from_str('Emotional Stability'),
        a_minus=DialecticalComponent.from_str('Emotional Volatility'),
        a=DialecticalComponent.from_str('Hate or Indifference'),
        a_plus=DialecticalComponent.from_str('Respect')
    )

    factory = WheelGenerator.instance(BasicWheel)
    redefined_half_wheel = factory.redefine(
        user_message,
        half_wheel,
        t_minus='Mental Preoccupation',
        t='Love',
        t_plus='Emotional Stability',
        a_minus='Emotional Volatility',
        a='Hate or Indifference',
        a_plus='Respect'
    )
    assert all(v is not None for v in half_wheel.model_dump(exclude_none=False).values())
    print(redefined_half_wheel)