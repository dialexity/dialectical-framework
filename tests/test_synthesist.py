import pytest
from dependency_injector import providers
from langfuse.decorators import observe

from dialectical_framework.domain.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.polarity.polarity_reasoner import PolarityReasoner
from dialectical_framework.synthesist.polarity.reason_fast import ReasonFast
from dialectical_framework.synthesist.polarity.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.polarity.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
from dialectical_framework.domain.wisdom_unit import WisdomUnit
from tests.test_analyst import user_message

# Graph-native imports
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as GraphDialecticalComponent
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit as GraphWisdomUnit


@pytest.mark.asyncio
@observe()
async def test_simple_wheel():
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None])
    assert wheels[0].order == 1
    print("\n")
    print(wheels[0])

@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("number_of_thoughts", [
    4,
    3,
    2,
])
async def test_bigger_wheel(number_of_thoughts):
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None] * number_of_thoughts)
    if number_of_thoughts == 2:
        assert len(wheels) == 2
    elif number_of_thoughts == 3:
        assert len(wheels) == 4
    elif number_of_thoughts == 4:
        assert len(wheels) == 8
    assert wheels[0].cycle is not None
    assert sum([w.cycle.probability for w in wheels]) == 1
    assert wheels[0].order == number_of_thoughts
    print("\n")
    print(wheels[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("reasoner_cls", [
    PolarityReasoner,
    ReasonFastAndSimple,
    ReasonFast,
    ReasonFastPolarizedConflict,
])
async def test_reasoner(di_container, reasoner_cls):
    with di_container.override_providers(
            polarity_reasoner=providers.Singleton(
                reasoner_cls,
            )
    ):
        reasoner = di_container.polarity_reasoner()
        reasoner.reload(text=user_message)
        wu = await reasoner.think()
        assert wu.is_complete()
        print("\n")
        print(wu)

@pytest.mark.asyncio
async def test_redefine(di_container):
    """Test redefine with graph-native models - simple modification test."""
    # Create graph-native components with simple, clear dialectical opposites
    t_minus = GraphDialecticalComponent(statement="Recklessness")
    t_minus.save()

    t = GraphDialecticalComponent(statement="Courage")
    t.save()

    t_plus = GraphDialecticalComponent(statement="Wisdom")
    t_plus.save()

    a_minus = GraphDialecticalComponent(statement="Paralysis")
    a_minus.save()

    a = GraphDialecticalComponent(statement="Fear")
    a.save()

    a_plus = GraphDialecticalComponent(statement="Prudence")
    a_plus.save()

    # Create graph-native WisdomUnit
    wu = GraphWisdomUnit(reasoning_mode="general_concepts")
    wu.save()

    # Connect components with aliases
    wu.t_minus.connect(t_minus, properties={'alias': 'T-'})
    wu.t.connect(t, properties={'alias': 'T'})
    wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
    wu.a_minus.connect(a_minus, properties={'alias': 'A-'})
    wu.a.connect(a, properties={'alias': 'A'})
    wu.a_plus.connect(a_plus, properties={'alias': 'A+'})

    # Test redefine - pass same values to test reconstruction without modification
    # This verifies the redefine mechanism works with graph-native models
    reasoner = di_container.polarity_reasoner()
    redefined_wu = await reasoner.redefine(
        original=wu,
        t="Courage",  # Same as original - tests reconstruction
        a="Fear",  # Same as original
    )

    # Basic assertions
    assert redefined_wu.is_complete()

    # redefine creates a new WU, doesn't mutate original
    assert wu.uid != redefined_wu.uid

    # Verify all positions are set
    assert redefined_wu.t.count() == 1
    assert redefined_wu.t_plus.count() == 1
    assert redefined_wu.t_minus.count() == 1
    assert redefined_wu.a.count() == 1
    assert redefined_wu.a_plus.count() == 1
    assert redefined_wu.a_minus.count() == 1

    print("\n")
    print("=== Original Graph-Native WisdomUnit ===")
    print(wu.pretty())
    print("\n")
    print("=== Redefined Graph-Native WisdomUnit ===")
    print(redefined_wu.pretty())