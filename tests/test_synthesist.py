import asyncio
from datetime import datetime

from langfuse.decorators import langfuse_context
from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.abstract_wheel_factory import AbstractWheelFactory
from dialectical_framework.synthesist.strategies.wheel2_conversation_strategy import Wheel2ConversationStrategy
from dialectical_framework.synthesist.wheel2 import Wheel2
from dialectical_framework.synthesist.wheel_generator import WheelGenerator

user_message = "There she goes, just walking down the street, singing doo-wah-diddy-diddy-dum-diddy-do."

def test_wheel_generator_with_validation():
    factory: AbstractWheelFactory = WheelGenerator.instance(Wheel2)
    wheel2: Wheel2 = asyncio.run(factory.generate(user_message))
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(wheel2)
    print("\n")
    # Redefine everything is a hacky way to validate everything
    redefined_wheel2 = asyncio.run(factory.redefine(
        user_message,
        wheel2,
        t_minus=wheel2.t_minus.statement,
        t=wheel2.t.statement,
        t_plus=wheel2.t_plus.statement,
        a_minus=wheel2.a_minus.statement,
        a=wheel2.a.statement,
        a_plus=wheel2.a_plus.statement
    ))
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(redefined_wheel2)

def test_wheel_generator():
    langfuse_context.update_current_trace(
        session_id=f"test {datetime.now()}",
        user_id="test",
    )
    factory: AbstractWheelFactory = WheelGenerator.instance(Wheel2)
    wheel2: BaseModel = asyncio.run(factory.generate(user_message))
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(wheel2)

def test_wheel_generator_conv_strategy():
    langfuse_context.update_current_trace(
        session_id=f"test {datetime.now()}",
        user_id="test",
    )
    factory: AbstractWheelFactory = WheelGenerator.instance(Wheel2ConversationStrategy)
    wheel2: BaseModel = asyncio.run(factory.generate(user_message))
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(wheel2)

def test_wheel_redefine():
    # Precalculated
    wheel2 = Wheel2(
        t_minus=DialecticalComponent.from_str('T-', 'Mental Preoccupation'),
        t=DialecticalComponent.from_str('T', 'Love'),
        t_plus=DialecticalComponent.from_str('T+', 'Compassionate Connection'),
        a_minus=DialecticalComponent.from_str('A-', 'Nihilistic Detachment'),
        a=DialecticalComponent.from_str('A', 'Indifference'),
        a_plus=DialecticalComponent.from_str('A+', 'Mindful Detachment')
    )

    # Redefine every component of the wheel, to make it an extreme test
    factory: AbstractWheelFactory = WheelGenerator.instance(Wheel2)
    redefined_wheel2 = asyncio.run(factory.redefine(
        user_message,
        wheel2,
        t_minus='Mental Preoccupation',
        t='Love',
        t_plus='Compassionate Connection',
        a_minus='Nihilistic Detachment',
        a='Indifference',
        a_plus='Mindful Detachment'
    ))
    assert all(v is not None for v in wheel2.model_dump(exclude_none=False).values())
    print("\n")
    print(redefined_wheel2)