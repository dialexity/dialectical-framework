import asyncio
from math import factorial
from typing import List

from langfuse.decorators import observe

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.factories.multiple_concepts import MultipleConcepts
from dialectical_framework.synthesist.factories.two_concepts import TwoConcepts
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig

user_message = "Putin started the war, Ukraine will not surrender and will finally win!"


@observe()
def test_thought_mapping():
    nr_of_thoughts = 3
    reasoner = ThoughtMapping(user_message)
    cycles: List[Cycle] = asyncio.run(reasoner.extract(nr_of_thoughts))
    assert len(cycles) == factorial(nr_of_thoughts - 1)
    print("\n")
    for cycle in cycles:
        assert len(cycle.dialectical_components) == nr_of_thoughts
        print(cycle.__str__())

@observe()
def test_wheel_2():
    wbc = WheelBuilderConfig(component_length=7)
    factory = TwoConcepts()
    wheel = asyncio.run(factory.build(user_message, wbc))
    assert len(wheel.wisdom_units) == 2
    print("\n")
    print(wheel)

@observe()
def test_wheel_3():
    number_of_thoughts = 3
    wbc = WheelBuilderConfig(component_length=7)
    factory = MultipleConcepts(number_of_thoughts)
    wheel = asyncio.run(factory.build(user_message, wbc))
    assert len(wheel.wisdom_units) == number_of_thoughts
    print("\n")
    print(wheel)

@observe()
def test_wheel_4():
    number_of_thoughts = 4
    wbc = WheelBuilderConfig(component_length=7)
    factory = MultipleConcepts(number_of_thoughts)
    wheel = asyncio.run(factory.build(user_message, wbc))
    assert len(wheel.wisdom_units) == number_of_thoughts
    print("\n")
    print(wheel)