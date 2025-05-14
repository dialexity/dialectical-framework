import asyncio

from langfuse.decorators import observe
from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.reasoner_blind import ReasonerBlind
from dialectical_framework.synthesist.reasoner_conversational import \
    ReasonerConversational
from dialectical_framework.synthesist.reasoner_fast import ReasonerFast
from dialectical_framework.synthesist.reasoner_fast_and_simple import ReasonerFastAndSimple
from dialectical_framework.synthesist.reasoner_fast_polarized_conflict import ReasonerFastPolarizedConflict
from dialectical_framework.synthesist.think_action_reflection import ThinkActionReflection
from dialectical_framework.wisdom_unit import WisdomUnit

user_message = "There she goes, just walking down the street, singing doo-wah-diddy-diddy-dum-diddy-do."


@observe()
def test_reasoner_find_thesis():
    reasoner = ReasonerBlind(user_message)
    thesis = asyncio.run(reasoner.find_thesis())
    assert thesis is not None
    print("\n")
    print(thesis)


@observe()
def test_blind_reasoner():
    reasoner = ReasonerBlind(user_message)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_blind_reasoner_with_validation():
    reasoner = ReasonerBlind(user_message)
    wu: WisdomUnit = asyncio.run(reasoner.generate())
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
    reasoner = ReasonerConversational(user_message)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner():
    reasoner = ReasonerFast(user_message)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert wu.is_complete()
    print("\n")
    print(wu)

@observe()
def test_fast_and_simple_reasoner():
    reasoner = ReasonerFastAndSimple(user_message, component_length=1)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert wu.is_complete()
    print("\n")
    print(wu)

@observe()
def test_fast_polarized_conflict_reasoner():
    reasoner = ReasonerFastPolarizedConflict(user_message, component_length=2)
    wu: BaseModel = asyncio.run(reasoner.generate())
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner_with_a_given_thesis():
    reasoner = ReasonerFast(user_message)
    wu: BaseModel = asyncio.run(reasoner.generate(thesis="Life is good!"))
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner_with_a_given_wrong_thesis():
    reasoner = ReasonerFast(user_message)
    wu: BaseModel = asyncio.run(
        reasoner.generate(thesis="She is standing in the corner")
    )
    assert wu.is_complete()
    print("\n")
    print(wu)


@observe()
def test_fast_reasoner_with_a_given_nonsense_thesis():
    reasoner = ReasonerFast(user_message)
    wu: BaseModel = asyncio.run(
        reasoner.generate(thesis="Lithuania is a place to live")
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
    reasoner = ReasonerBlind(user_message)
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
