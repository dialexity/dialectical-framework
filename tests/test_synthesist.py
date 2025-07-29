import pytest
from langfuse.decorators import observe
from pydantic import BaseModel

from dialectical_framework.cycle import Cycle
from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.analyst.decorator_action_reflection import DecoratorActionReflection
from dialectical_framework.analyst.decorator_discrete_spiral import DecoratorDiscreteSpiral
from dialectical_framework.analyst.decorator_reciprocal_solution import DecoratorReciprocalSolution
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.reason_blind import ReasonBlind
from dialectical_framework.synthesist.reason_conversational import \
    ReasonConversational
from dialectical_framework.synthesist.reason_fast import ReasonFast
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.analyst.think_reciprocal_solution import ThinkReciprocalSolution
from dialectical_framework.synthesist.thought_mapper import ThoughtMapper
from dialectical_framework.wheel import Wheel
from dialectical_framework.wisdom_unit import WisdomUnit
from tests.test_analyst import user_message

wbc = ConfigWheelBuilder(component_length=7)
factory = WheelBuilder(
    config=wbc,
    text=user_message,
)

@pytest.mark.asyncio
@observe()
async def test_build_simple_wheel():
    wheels = await factory.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1

    print("\n")
    print(wheels[0])

@pytest.mark.asyncio
@observe()
async def test_full_blown_wheel():
    factory1 = DecoratorDiscreteSpiral(DecoratorReciprocalSolution(DecoratorActionReflection(builder=factory)))
    wheels = await factory1.build_wheel_permutations(theses=[None, None])
    assert wheels[0].order == 2

    await factory1.calculate_transitions(wheels[0])

    print("\n")
    print(wheels[0])


@pytest.mark.asyncio
@observe()
async def test_reasoner_find_thesis():
    reasoner = ReasonBlind(user_message)
    thesis = await reasoner.find_thesis()
    assert thesis is not None
    print("\n")
    print(thesis)

@pytest.mark.asyncio
@observe()
async def test_reasoner_find_antithesis():
    reasoner = ReasonBlind(user_message)
    antithesis = await reasoner.find_antithesis("Putin starts war")
    assert antithesis is not None
    print("\n")
    print(antithesis)

@pytest.mark.asyncio
@observe()
async def test_blind_reasoner():
    reasoner = ReasonBlind(user_message)
    wu: BaseModel = await reasoner.think()
    assert wu.is_complete()
    print("\n")
    print(wu)


@pytest.mark.asyncio
@observe()
async def test_blind_reasoner_with_validation():
    reasoner = ReasonBlind(user_message)
    wu: WisdomUnit = await reasoner.think()
    assert wu.is_complete()
    print("\n")
    print(wu)
    print("\n")
    # Redefine everything is a hacky way to validate everything
    redefined_wu = await reasoner.redefine(
        t_minus=wu.t_minus.statement,
        t=wu.t.statement,
        t_plus=wu.t_plus.statement,
        a_minus=wu.a_minus.statement,
        a=wu.a.statement,
        a_plus=wu.a_plus.statement,
    )
    assert wu.is_complete()
    print("\n")
    print(redefined_wu)


@pytest.mark.asyncio
@observe()
async def test_conversational_reasoner():
    reasoner = ReasonConversational(user_message)
    wu: BaseModel = await reasoner.think()
    assert wu.is_complete()
    print("\n")
    print(wu)


@pytest.mark.asyncio
@observe()
async def test_fast_reasoner():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = await reasoner.think()
    assert wu.is_complete()
    print("\n")
    print(wu)

@pytest.mark.asyncio
@observe()
async def test_fast_and_simple_reasoner():
    reasoner = ReasonFastAndSimple(user_message, config=wbc)
    wu: BaseModel = await reasoner.think()
    assert wu.is_complete()
    print("\n")
    print(wu)

@pytest.mark.asyncio
@observe()
async def test_fast_polarized_conflict_reasoner():
    reasoner = ReasonFastPolarizedConflict(user_message, config=wbc)
    wu: BaseModel = await reasoner.think()
    assert wu.is_complete()
    print("\n")
    print(wu)


@pytest.mark.asyncio
@observe()
async def test_fast_reasoner_with_a_given_thesis():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = await reasoner.think(thesis="Life is good!")
    assert wu.is_complete()
    print("\n")
    print(wu)


@pytest.mark.asyncio
@observe()
async def test_fast_reasoner_with_a_given_wrong_thesis():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = await reasoner.think(thesis="She is standing in the corner")
    assert wu.is_complete()
    print("\n")
    print(wu)


@pytest.mark.asyncio
@observe()
async def test_fast_reasoner_with_a_given_nonsense_thesis():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = await reasoner.think(thesis="Lithuania is a place to live")
    assert wu.is_complete()
    print("\n")
    print(wu)


@pytest.mark.asyncio
@observe()
async def test_reciprocal_solution():
    # Precalculated
    wu = WisdomUnit(
        t_minus=DialecticalComponent(alias="T-", statement="Mental Preoccupation"),
        t=DialecticalComponent(alias="T", statement="Love"),
        t_plus=DialecticalComponent(alias="T+", statement="Compassionate Connection"),
        a_minus=DialecticalComponent(alias="A-", statement="Nihilistic Detachment"),
        a=DialecticalComponent(alias="A", statement="Indifference"),
        a_plus=DialecticalComponent(alias="A+", statement="Mindful Detachment"),
    )

    reasoner = ThinkReciprocalSolution(user_message, wheel=Wheel(
        wu,
        t_cycle=Cycle(dialectical_components=[wu.t]),
        ta_cycle=Cycle(dialectical_components=[wu.t, wu.a])
    ))
    transition = await reasoner.think(focus=wu)
    assert not transition.action_reflection
    assert transition.reciprocal_solution
    print("\n")
    print(transition)

@pytest.mark.asyncio
@observe()
async def test_redefine():
    # Precalculated
    wu = WisdomUnit(
        t_minus=DialecticalComponent(alias="T-", statement="Mental Preoccupation"),
        t=DialecticalComponent(alias="T", statement="Love"),
        t_plus=DialecticalComponent(alias="T+", statement="Compassionate Connection"),
        a_minus=DialecticalComponent(alias="A-", statement="Nihilistic Detachment"),
        a=DialecticalComponent(alias="A", statement="Indifference"),
        a_plus=DialecticalComponent(alias="A+", statement="Mindful Detachment"),
    )

    # Redefine every component of the wisdom unit to make it an extreme test
    reasoner = ReasonBlind(user_message)
    redefined_wu = await reasoner.redefine(
        original=wu,
        t_minus="Mental Preoccupation",
        t="Love",
        t_plus="Compassionate Connection",
        a_minus="Nihilistic Detachment",
        a="Indifference",
        a_plus="Mindful Detachment",
    )
    assert wu.is_complete()
    print("\n")
    print(redefined_wu)

@pytest.mark.asyncio
@observe()
async def test_find_theses():
    thought_mapper = ThoughtMapper(text=factory.text, config=wbc)
    theses_deck = await thought_mapper.find_theses(
        count=1
    )
    theses = [dc.statement for dc in theses_deck.dialectical_components]
    print("\n".join(theses))