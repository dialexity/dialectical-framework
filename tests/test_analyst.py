from typing import List

import pytest
from langfuse.decorators import observe
from mirascope import prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.synthesist.thought_mapper import ThoughtMapper
from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.analyst.decorator_action_reflection import DecoratorActionReflection
from dialectical_framework.analyst.decorator_reciprocal_solution import DecoratorReciprocalSolution
from dialectical_framework.synthesist.reverse_engineer import ReverseEngineer
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.wheel import Wheel
from dialectical_framework.wisdom_unit import WisdomUnit

user_message = "Putin started the war, Ukraine will not surrender and will finally win!"

# Examples
example_wu1 = WisdomUnit(
    t_minus=DialecticalComponent.from_str("T1-","Destructive aggression"),
    t=DialecticalComponent.from_str("T1","Putin initiates war"),
    t_plus=DialecticalComponent.from_str("T1+","Strategic power projection"),
    a_plus=DialecticalComponent.from_str("A1+","Mutual understanding"),
    a=DialecticalComponent.from_str("A1","Peace negotiations"),
    a_minus=DialecticalComponent.from_str("A1-","Passive submission"),
)
example_wu2 = WisdomUnit(
    t_minus=DialecticalComponent.from_str("T2-","Endless conflict and destruction"),
    t=DialecticalComponent.from_str("T2","Ukraine resists invasion"),
    t_plus=DialecticalComponent.from_str("T2+","Liberation and sovereignty protected"),
    a_plus=DialecticalComponent.from_str("A2+","Immediate peace achieved"),
    a=DialecticalComponent.from_str("A2","Ukraine surrenders to invasion"),
    a_minus=DialecticalComponent.from_str("A2-","Freedom and independence lost"),
)
example_wu3 = WisdomUnit(
    t_minus=DialecticalComponent.from_str("T3-","Military resources drain rapidly"),
    t=DialecticalComponent.from_str("T3","Russian offensive weakens"),
    t_plus=DialecticalComponent.from_str("T3+","Ukrainian victory approaches"),
    a_plus=DialecticalComponent.from_str("A3+","Strategic military strength maintained"),
    a=DialecticalComponent.from_str("A3","Russian military dominance persists"),
    a_minus=DialecticalComponent.from_str("A3-","Total defeat inevitable"),
)
example_wu4 = WisdomUnit(
    t_minus=DialecticalComponent.from_str("T4-","Vengeance intensifies"),
    t=DialecticalComponent.from_str("T4","Ukrainian victory approaches"),
    t_plus=DialecticalComponent.from_str("T4+","Freedom restored"),
    a_plus=DialecticalComponent.from_str("A4+","Stability maintained"),
    a=DialecticalComponent.from_str("A4","Russian dominance persists"),
    a_minus=DialecticalComponent.from_str("A4-","Oppression deepens"),
)

wbc = ConfigWheelBuilder(component_length=7)
factory = WheelBuilder(
    config=wbc,
    text=user_message,
)


@pytest.mark.asyncio
@observe()
async def test_reverse_engineering():
    tm: ThoughtMapper = ThoughtMapper(
        user_message,
        config=wbc,
    )
    t_cycles = await tm.arrange([
        example_wu1.t.statement,
        example_wu2.t.statement,
    ])
    ta_cycles = await tm.arrange([example_wu1, example_wu2])
    w = Wheel([example_wu1, example_wu2],
              t_cycle=t_cycles[0],
              ta_cycle=ta_cycles[0]
              )

    provider, model = wbc.brain.specification()
    @with_langfuse()
    @llm.call(provider=provider, model=model)
    @prompt_template(
    """
    MESSAGES:
    {wheel_construction}
    
    USER:
    Summarize the whole analysis
    """)
    def summarize():
        return {
            "computed_fields": {
                "wheel_construction" : ReverseEngineer.wheel(w, text=user_message),
            }
        }

    # Call and get the result
    result = summarize()
    print("\n")
    print(result)


@pytest.mark.asyncio
@observe()
async def test_wheel_acre():
    factory2 = DecoratorActionReflection(builder=factory)
    wheels = await factory2.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1
    assert wheels[0].cycle is not None

    await factory2.calculate_transitions(wheels[0])

    print("\n")
    print(wheels[0])

@pytest.mark.asyncio
@observe()
async def test_wheel_acre_reciprocal():
    factory3 = DecoratorReciprocalSolution(DecoratorActionReflection(builder=factory))
    wheels = await factory3.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1
    assert wheels[0].cycle is not None

    await factory3.calculate_transitions(wheels[0])

    print("\n")
    print(wheels[0])

@pytest.mark.asyncio
@observe()
async def test_factory_loading():
    tm: ThoughtMapper = ThoughtMapper(
        user_message,
        config=wbc,
    )
    t_cycles = await tm.arrange([
        example_wu1.t.statement,
        example_wu2.t.statement,
        example_wu3.t.statement,
        example_wu4.t.statement,
    ])
    ta_cycles = await tm.arrange([example_wu1, example_wu2, example_wu3, example_wu4])
    w = Wheel([example_wu1, example_wu2, example_wu3, example_wu4],
              t_cycle=t_cycles[0],
              ta_cycle=ta_cycles[0]
              )
    wb = WheelBuilder.load(
        text=user_message,
        config=wbc,
        wheels=[w]
    )

    assert len(wb.wheel_permutations) == 1
    assert len(wb.wheel_permutations[0].wisdom_units) == 4
    print("\n")
    print(wb.wheel_permutations[0])

@pytest.mark.asyncio
@observe()
async def test_wheel_redefine():
    tm: ThoughtMapper = ThoughtMapper(
        user_message,
        config=wbc,
    )
    t_cycles = await tm.arrange([
        example_wu1.t.statement,
        example_wu2.t.statement,
        example_wu3.t.statement,
        example_wu4.t.statement,
    ])
    ta_cycles = await tm.arrange([example_wu1, example_wu2, example_wu3, example_wu4])
    w = Wheel([example_wu1, example_wu2, example_wu3, example_wu4],
              t_cycle=t_cycles[0],
              ta_cycle=ta_cycles[0]
              )
    wb = WheelBuilder.load(
        text=user_message,
        config=wbc,
        wheels=[w]
    )

    print("\n")
    print(wb.wheel_permutations[0])
    print("\n")

    wheels = await wb.redefine({"T1": "Putin starts war", "T2+": "Keeping sovereignty"})
    print("\n")
    print("\n\n".join([w.__str__() for w in wheels]))


@pytest.mark.asyncio
@observe()
async def test_thought_mapping():
    nr_of_thoughts = 3
    reasoner = ThoughtMapper(user_message)
    cycles: List[Cycle] = await reasoner.map(nr_of_thoughts)
    print("\n")
    for cycle in cycles:
        assert len(cycle.dialectical_components) == nr_of_thoughts
        print(cycle.pretty(skip_dialectical_component_explanation=True))

@pytest.mark.asyncio
@observe()
async def test_wheel_2():
    wheels = await factory.build_wheel_permutations(theses=["", None])
    assert len(wheels[0].wisdom_units) == 2
    assert wheels[0].cycle is not None
    print("\n")
    print(wheels[0])

@pytest.mark.asyncio
@observe()
async def test_wheel_3():
    number_of_thoughts = 3
    wheels = await factory.build_wheel_permutations(theses=[None] * number_of_thoughts)
    assert len(wheels[0].wisdom_units) == number_of_thoughts
    assert wheels[0].cycle is not None
    print("\n")
    print("\n\n".join(str(wheel) for wheel in wheels))

@pytest.mark.asyncio
@observe()
async def test_wheel_4():
    number_of_thoughts = 4
    wheels = await factory.build_wheel_permutations(theses=[None] * number_of_thoughts)
    assert len(wheels[0].wisdom_units) == number_of_thoughts
    assert wheels[0].cycle is not None
    print("\n")
    print("\n\n".join(str(wheel) for wheel in wheels))