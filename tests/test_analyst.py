import pytest
from langfuse.decorators import observe

from dialectical_framework.analyst.decorator_action_reflection import DecoratorActionReflection
from dialectical_framework.analyst.decorator_discrete_spiral import DecoratorDiscreteSpiral
from dialectical_framework.analyst.decorator_discrete_spiral_audited import DecoratorDiscreteSpiralAudited
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit
from dialectical_framework.utils.dw_report import dw_report

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

@pytest.mark.asyncio
@observe()
async def test_full_blown_wheel():
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory1 = DecoratorDiscreteSpiralAudited(DecoratorDiscreteSpiral(DecoratorActionReflection(builder=factory)))
    wheels = await factory1.build_wheel_permutations(theses=[None, None])
    assert wheels[0].order == 2
    await factory1.calculate_transitions(wheels[0])
    assert wheels[0].score > 0

    print(dw_report(wheels))

@pytest.mark.asyncio
@observe()
async def test_wheel_spiral():
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory1 = DecoratorDiscreteSpiral(builder=factory)
    wheels = await factory1.build_wheel_permutations(theses=[None, None])
    assert wheels[0].order == 2

    await factory1.calculate_transitions(wheels[0])
    await factory1.calculate_syntheses(wheels[0], 1)

    print(dw_report(wheels))

@pytest.mark.asyncio
@observe()
async def test_wheel_acre():
    factory = DialecticalReasoning.wheel_builder(text=user_message)
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
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory3 = DecoratorActionReflection(builder=factory)
    wheels = await factory3.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1
    assert wheels[0].cycle is not None

    await factory3.calculate_transitions(wheels[0])

    print("\n")
    print(wheels[0])


@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("number_of_thoughts", [
    1,
    2,
    3,
    4,
])
async def test_find_theses(number_of_thoughts):
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    theses_deck = await factory.extractor.extract_multiple_theses(count=number_of_thoughts)
    theses = [dc.statement for dc in theses_deck.dialectical_components]
    print("\n".join(theses))


@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("given,expected_count", [
    # Single polarity - both empty
    ([(None, None)], 1),
    # Single polarity - thesis provided
    ([("Love", None)], 1),
    # # Single polarity - antithesis provided
    ([(None, "Hate")], 1),
    # # Single polarity - both provided
    ([("Love", "Hate")], 1),
    # # Multiple polarities - mixed
    ([("Love", None), (None, "Home")], 2),
    # # Multiple polarities - all empty
    ([(None, None), (None, None)], 2),
    # # Multiple polarities - various combinations
    ([("Love", None), (None, "Home"), ("Peace", "War"), (None, None)], 4),
])
async def test_find_polarities(given, expected_count):
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    polarities = await factory.extractor.extract_polarities(given=given)

    assert len(polarities) == expected_count

    print("\n")
    # Print results
    for t, a in polarities:
        print(t)
        print(a)
        print("\n")

    # Verify all components exist and have correct aliases
    for i, (t, a) in enumerate(polarities):
        assert t is not None and a is not None
        # Check aliases: T/A for single, T1/A1, T2/A2, etc. for multiple
        if expected_count == 1:
            assert t.alias == "T"
            assert a.alias == "A"
        else:
            assert t.alias == f"T{i + 1}"
            assert a.alias == f"A{i + 1}"
        # Verify index: 0 for single, 1-based for multiple
        expected_idx = 0 if expected_count == 1 else i + 1
        assert t.get_human_friendly_index() == expected_idx
        assert a.get_human_friendly_index() == expected_idx