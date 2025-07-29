from typing import List

import pytest
from langfuse.decorators import observe
from mirascope import prompt_template, llm
from mirascope.integrations.langfuse import with_langfuse

from dialectical_framework.analyst.decorator_discrete_spiral import DecoratorDiscreteSpiral
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
    t_minus=DialecticalComponent(alias="T1-", statement="Destructive aggression"),
    t=DialecticalComponent(alias="T1", statement="Putin initiates war"),
    t_plus=DialecticalComponent(alias="T1+", statement="Strategic power projection"),
    a_plus=DialecticalComponent(alias="A1+", statement="Mutual understanding"),
    a=DialecticalComponent(alias="A1", statement="Peace negotiations"),
    a_minus=DialecticalComponent(alias="A1-", statement="Passive submission"),
)
example_wu2 = WisdomUnit(
    t_minus=DialecticalComponent(alias="T2-", statement="Endless conflict and destruction"),
    t=DialecticalComponent(alias="T2", statement="Ukraine resists invasion"),
    t_plus=DialecticalComponent(alias="T2+", statement="Liberation and sovereignty protected"),
    a_plus=DialecticalComponent(alias="A2+", statement="Immediate peace achieved"),
    a=DialecticalComponent(alias="A2", statement="Ukraine surrenders to invasion"),
    a_minus=DialecticalComponent(alias="A2-", statement="Freedom and independence lost"),
)
example_wu3 = WisdomUnit(
    t_minus=DialecticalComponent(alias="T3-", statement="Military resources drain rapidly"),
    t=DialecticalComponent(alias="T3", statement="Russian offensive weakens"),
    t_plus=DialecticalComponent(alias="T3+", statement="Ukrainian victory approaches"),
    a_plus=DialecticalComponent(alias="A3+", statement="Strategic military strength maintained"),
    a=DialecticalComponent(alias="A3", statement="Russian military dominance persists"),
    a_minus=DialecticalComponent(alias="A3-", statement="Total defeat inevitable"),
)
example_wu4 = WisdomUnit(
    t_minus=DialecticalComponent(alias="T4-", statement="Vengeance intensifies"),
    t=DialecticalComponent(alias="T4", statement="Ukrainian victory approaches"),
    t_plus=DialecticalComponent(alias="T4+", statement="Freedom restored"),
    a_plus=DialecticalComponent(alias="A4+", statement="Stability maintained"),
    a=DialecticalComponent(alias="A4", statement="Russian dominance persists"),
    a_minus=DialecticalComponent(alias="A4-", statement="Oppression deepens"),
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
async def test_wheel_spiral():
    factory1 = DecoratorDiscreteSpiral(builder=factory)
    wheels = await factory1.build_wheel_permutations(theses=[None, None])
    assert wheels[0].order == 2

    await factory1.calculate_transitions(wheels[0])
    await factory1.calculate_syntheses(wheels[0], 1)

    print("\n")
    print(wheels[0])
    print(wheels[0].wisdom_units[1].synthesis)

@pytest.mark.asyncio
@observe()
async def test_wheel_acre():
    factory2 = DecoratorActionReflection(builder=factory)
    wheels = await factory2.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1
    assert wheels[0].cycle is not None

    await factory2.calculate_transitions(wheels[0])
    await factory2.calculate_syntheses(wheels[0])

    print("\n")
    print(wheels[0])
    print(wheels[0].wisdom_units[0].synthesis)

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