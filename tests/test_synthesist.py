import asyncio

from langfuse.decorators import observe
from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_blind import ReasonBlind
from dialectical_framework.synthesist.reason_conversational import \
    ReasonConversational
from dialectical_framework.synthesist.reason_fast import ReasonFast
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.synthesist.think_action_reflection import ThinkActionReflection
from dialectical_framework.synthesist.think_reciprocal_solution import ThinkReciprocalSolution
from dialectical_framework.wheel import Wheel
from dialectical_framework.wisdom_unit import WisdomUnit

user_message = "There she goes, just walking down the street, singing doo-wah-diddy-diddy-dum-diddy-do."


@observe()
def test_reasoner_find_thesis():
    reasoner = ReasonBlind(user_message)
    thesis = asyncio.run(reasoner.find_thesis())
    assert thesis is not None
    print("\n")
    print(thesis)

@observe()
def test_reasoner_find_antithesis():
    reasoner = ReasonBlind(user_message)
    antithesis = asyncio.run(reasoner.find_antithesis("Putin starts war"))
    assert antithesis is not None
    print("\n")
    print(antithesis)

@observe()
def test_blind_reasoner():
    reasoner = ReasonBlind(user_message)
    wu: BaseModel = asyncio.run(reasoner.think())
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_blind_reasoner_with_validation():
    reasoner = ReasonBlind(user_message)
    wu: WisdomUnit = asyncio.run(reasoner.think())
    assert wu.is_complete()
    print("\n")
    print(wu)
    print("\n")
    # Redefine everything is a hacky way to validate everything
    redefined_wu = asyncio.run(
        reasoner.redefine(
            t_minus=wu.t_minus.statement,
            t=wu.t.statement,
            t_plus=wu.t_plus.statement,
            a_minus=wu.a_minus.statement,
            a=wu.a.statement,
            a_plus=wu.a_plus.statement,
        )
    )
    assert wu.is_complete()
    print("\n")
    print(redefined_wu)


@observe()
def test_conversational_reasoner():
    reasoner = ReasonConversational(user_message)
    wu: BaseModel = asyncio.run(reasoner.think())
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = asyncio.run(reasoner.think())
    assert wu.is_complete()
    print("\n")
    print(wu)

@observe()
def test_fast_and_simple_reasoner():
    wbc = WheelBuilderConfig(component_length=1)
    reasoner = ReasonFastAndSimple(user_message, config=wbc)
    wu: BaseModel = asyncio.run(reasoner.think())
    assert wu.is_complete()
    print("\n")
    print(wu)

@observe()
def test_fast_polarized_conflict_reasoner():
    wbc = WheelBuilderConfig(component_length=2)
    reasoner = ReasonFastPolarizedConflict(user_message, config=wbc)
    wu: BaseModel = asyncio.run(reasoner.think())
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner_with_a_given_thesis():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = asyncio.run(reasoner.think(thesis="Life is good!"))
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner_with_a_given_wrong_thesis():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = asyncio.run(
        reasoner.think(thesis="She is standing in the corner")
    )
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner_with_a_given_nonsense_thesis():
    reasoner = ReasonFast(user_message)
    wu: BaseModel = asyncio.run(
        reasoner.think(thesis="Lithuania is a place to live")
    )
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_ac_re():
    # Precalculated
    wu = WisdomUnit(
        t_minus=DialecticalComponent.from_str("T-", "Mental Preoccupation"),
        t=DialecticalComponent.from_str("T", "Love"),
        t_plus=DialecticalComponent.from_str("T+", "Compassionate Connection"),
        a_minus=DialecticalComponent.from_str("A-", "Nihilistic Detachment"),
        a=DialecticalComponent.from_str("A", "Indifference"),
        a_plus=DialecticalComponent.from_str("A+", "Mindful Detachment"),
    )

    reasoner = ThinkActionReflection(user_message, wisdom_unit=wu)
    transition = asyncio.run(reasoner.think())
    assert transition.action_reflection.is_complete()
    wheel = Wheel(wu)
    wheel.add_transition(0, transition)
    print("\n")
    print(wheel)


@observe()
def test_reciprocal_solution():
    # Precalculated
    wu = WisdomUnit(
        t_minus=DialecticalComponent.from_str("T-", "Mental Preoccupation"),
        t=DialecticalComponent.from_str("T", "Love"),
        t_plus=DialecticalComponent.from_str("T+", "Compassionate Connection"),
        a_minus=DialecticalComponent.from_str("A-", "Nihilistic Detachment"),
        a=DialecticalComponent.from_str("A", "Indifference"),
        a_plus=DialecticalComponent.from_str("A+", "Mindful Detachment"),
    )

    reasoner = ThinkReciprocalSolution(user_message, wisdom_unit=wu)
    transition = asyncio.run(reasoner.think())
    assert not transition.action_reflection
    assert transition.reciprocal_solution
    print("\n")
    print(transition)

@observe()
def test_redefine():
    # Precalculated
    wu = WisdomUnit(
        t_minus=DialecticalComponent.from_str("T-", "Mental Preoccupation"),
        t=DialecticalComponent.from_str("T", "Love"),
        t_plus=DialecticalComponent.from_str("T+", "Compassionate Connection"),
        a_minus=DialecticalComponent.from_str("A-", "Nihilistic Detachment"),
        a=DialecticalComponent.from_str("A", "Indifference"),
        a_plus=DialecticalComponent.from_str("A+", "Mindful Detachment"),
    )

    # Redefine every component of the wisdom unit to make it an extreme test
    reasoner = ReasonBlind(user_message)
    redefined_wu = asyncio.run(
        reasoner.redefine(
            original=wu,
            t_minus="Mental Preoccupation",
            t="Love",
            t_plus="Compassionate Connection",
            a_minus="Nihilistic Detachment",
            a="Indifference",
            a_plus="Mindful Detachment",
        )
    )
    assert wu.is_complete()
    print("\n")
    print(redefined_wu)
