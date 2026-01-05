import pytest
from langfuse.decorators import observe

from dialectical_framework.analyst.decorator_action_reflection import DecoratorActionReflection
from dialectical_framework.analyst.decorator_discrete_spiral import DecoratorDiscreteSpiral
from dialectical_framework.analyst.decorator_discrete_spiral_audited import DecoratorDiscreteSpiralAudited
from dialectical_framework.domain.dialectical_component import DialecticalComponent
from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.domain.wisdom_unit import WisdomUnit
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

    print(str(wheels[0]))

@pytest.mark.asyncio
@observe()
async def test_wheel_spiral():
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory1 = DecoratorDiscreteSpiral(builder=factory)
    wheels = await factory1.build_wheel_permutations(theses=[None, None])
    assert wheels[0].polarity_count == 2  # Graph-native uses polarity_count instead of order

    await factory1.calculate_transitions(wheel=wheels[0])

    # Get first wisdom unit for synthesis
    wu_list = [wu for wu, _ in wheels[0].wisdom_units.all()]
    await factory1.calculate_syntheses(wheel=wheels[0], at=wu_list[0] if wu_list else None)

    # print(dw_report(wheels))
    print(str(wheels[0]))

@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("number_of_thoughts", [
    1,
    # 2,
])
async def test_wheel_acre(number_of_thoughts):
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory2 = DecoratorActionReflection(builder=factory)
    wheels = await factory2.build_wheel_permutations(theses=[None]*number_of_thoughts)
    assert len(wheels) > 0
    wheel = wheels[0]

    # Check that cycles exist (graph-native)
    t_cycle_result = wheel.t_cycle.get()
    assert t_cycle_result is not None, "T-cycle should exist"

    ta_cycle_result = wheel.ta_cycle.get()
    assert ta_cycle_result is not None, "TA-cycle should exist"

    # First call to calculate_transitions
    await factory2.calculate_transitions(wheel)

    # Get first wisdom unit
    wu_list = [wu for wu, _ in wheel.wisdom_units.all()]
    assert len(wu_list) > 0, "Should have at least one wisdom unit"
    first_wu = wu_list[0]

    # Check transformation was created (Action-Reflection)
    transformation_result = first_wu.transformation.get()
    assert transformation_result is not None, "Transformation should be created by DecoratorActionReflection"
    transformation, _ = transformation_result

    # Verify exactly 2 transitions (T- → A+, A- → T+)
    transitions = [t for t, _ in transformation.transitions.all()]
    assert len(transitions) == 2, f"Transformation should have exactly 2 transitions, got {len(transitions)}"

    # Verify transition source/target components
    t_minus_result = first_wu.t_minus.get()
    a_plus_result = first_wu.a_plus.get()
    a_minus_result = first_wu.a_minus.get()
    t_plus_result = first_wu.t_plus.get()

    assert t_minus_result, "T- component should exist"
    assert a_plus_result, "A+ component should exist"
    assert a_minus_result, "A- component should exist"
    assert t_plus_result, "T+ component should exist"

    t_minus_comp, _ = t_minus_result
    a_plus_comp, _ = a_plus_result
    a_minus_comp, _ = a_minus_result
    t_plus_comp, _ = t_plus_result

    # Check that transitions connect correct components
    transition_pairs = []
    for trans in transitions:
        source_result = trans.source.get()
        target_result = trans.target.get()
        assert source_result, "Transition should have source"
        assert target_result, "Transition should have target"

        source_comp, _ = source_result
        target_comp, _ = target_result
        transition_pairs.append((source_comp._id, target_comp._id))

    # Should have T- → A+ and A- → T+
    expected_pairs = {
        (t_minus_comp._id, a_plus_comp._id),
        (a_minus_comp._id, t_plus_comp._id)
    }
    assert set(transition_pairs) == expected_pairs, "Transitions should connect T- → A+ and A- → T+"

    # Check that each transition has at least one rationale
    for trans in transitions:
        rationales = [r for r, _ in trans.rationales.all()]
        assert len(rationales) >= 1, "Each transition should have at least one rationale"

    # Store initial rationale counts
    initial_rationale_counts = {trans._id: len([r for r, _ in trans.rationales.all()]) for trans in transitions}

    # Call calculate_transitions AGAIN to test duplicate detection
    await factory2.calculate_transitions(wheel)

    # Verify still exactly 2 transitions (no duplicates created)
    transitions_after = [t for t, _ in transformation.transitions.all()]
    assert len(transitions_after) == 2, f"Should still have exactly 2 transitions after second call, got {len(transitions_after)}"

    # Verify rationale count increased (new rationales added to existing transitions)
    for trans in transitions_after:
        new_count = len([r for r, _ in trans.rationales.all()])
        old_count = initial_rationale_counts[trans._id]
        assert new_count > old_count, f"Transition should have more rationales after second call: {old_count} → {new_count}"

    print("\n")
    print(str(wheel))
    print("\n")
    print("\n")
    for wu in wheel.polar_pairs_ordered:
        print(f"{wu:verbse}")
