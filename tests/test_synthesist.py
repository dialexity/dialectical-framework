import pytest
from dependency_injector import providers
from langfuse.decorators import observe
from pydantic import BaseModel

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.reason_blind import ReasonBlind
from dialectical_framework.synthesist.reason_conversational import \
    ReasonConversational
from dialectical_framework.synthesist.reason_fast import ReasonFast
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.wisdom_unit import WisdomUnit
from tests.test_analyst import user_message


@pytest.mark.asyncio
@observe()
async def test_simple_wheel():
    factory = DialecticalReasoning.create_wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1

    print("\n")
    print(wheels[0])

@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("number_of_thoughts", [
    2,
    3,
    4,
])
async def test_bigger_wheel(number_of_thoughts):
    factory = DialecticalReasoning.create_wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None] * number_of_thoughts)
    assert wheels[0].order == number_of_thoughts
    assert wheels[0].cycle is not None
    print("\n")
    print(wheels[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoner_cls", [
    ReasonFastAndSimple,
    ReasonFast,
    ReasonBlind,
    ReasonConversational,
    ReasonFastPolarizedConflict,
])
async def test_reasoner_find_thesis(di_container, reasoner_cls):
    with di_container.override_providers(
            polarity_reasoner=providers.Singleton(
                reasoner_cls,
            )
    ):
        reasoner = di_container.polarity_reasoner()
        reasoner.load(text=user_message)
        thesis = await reasoner.find_thesis()
        assert thesis is not None
        print("\n")
        print(thesis)

@pytest.mark.asyncio
@pytest.mark.parametrize("reasoner_cls", [
    ReasonFastAndSimple,
    ReasonFast,
    ReasonBlind,
    ReasonConversational,
    ReasonFastPolarizedConflict,
])
async def test_reasoner_find_antithesis(di_container, reasoner_cls):
    with di_container.override_providers(
            polarity_reasoner=providers.Singleton(
                reasoner_cls,
            )
    ):
        reasoner = di_container.polarity_reasoner()
        reasoner.load(text=user_message)
        antithesis = await reasoner.find_antithesis("Putin starts war")
        assert antithesis is not None
        print("\n")
        print(antithesis)

@pytest.mark.asyncio
@pytest.mark.parametrize("reasoner_cls", [
    ReasonFastAndSimple,
    ReasonFast,
    ReasonBlind,
    ReasonConversational,
    ReasonFastPolarizedConflict,
])
async def test_reasoner(di_container, reasoner_cls):
    with di_container.override_providers(
            polarity_reasoner=providers.Singleton(
                ReasonBlind,
            )
    ):
        reasoner = di_container.polarity_reasoner()
        reasoner.load(text=user_message)
        wu: BaseModel = await reasoner.think()
        assert wu.is_complete()
        print("\n")
        print(wu)

@pytest.mark.asyncio
async def test_redefine(di_container):
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
    reasoner = di_container.polarity_reasoner
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