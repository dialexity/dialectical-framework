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

# import litellm
# litellm._turn_on_debug()

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
@pytest.mark.parametrize("number_of_thoughts", [
    2,
    # 3,
])
async def test_full_blown_wheel(number_of_thoughts):
    """
    Full-blown test with all decorators: Action-Reflection, Spiral, and Audited Spiral.
    This test includes synthesis calculation.
    """
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory1 = DecoratorDiscreteSpiralAudited(DecoratorDiscreteSpiral(DecoratorActionReflection(builder=factory)))
    wheels = await factory1.build_wheel_permutations(theses=[None]*number_of_thoughts)

    assert len(wheels) > 0, "Should generate at least one wheel"
    wheel = wheels[0]

    # Verify structure
    assert wheel.polarity_count == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom units, got {wheel.polarity_count}"

    # Verify cycles exist
    t_cycle_result = wheel.t_cycle.get()
    assert t_cycle_result is not None, "T-cycle should exist"

    ta_cycle_result = wheel.ta_cycle.get()
    assert ta_cycle_result is not None, "TA-cycle should exist"

    # Calculate transitions (spiral will be created during this step)
    await factory1.calculate_transitions(wheel)

    # Verify spiral was created
    spiral_result = wheel.spiral.get()
    assert spiral_result is not None, "Spiral MUST be created by DecoratorDiscreteSpiral"

    # Get wisdom units
    wu_list = [wu for wu, _ in wheel.wisdom_units.all()]
    assert len(wu_list) == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom units, got {len(wu_list)}"

    # Verify transformations exist (Action-Reflection)
    for wu in wu_list:
        transformation_result = wu.transformation.get()
        assert transformation_result is not None, f"WisdomUnit {wu.uid} should have transformation"
        transformation, _ = transformation_result

        # Verify ac_re exists
        ac_re_result = transformation.ac_re.get()
        assert ac_re_result is not None, "Transformation should have ac_re WisdomUnit"

        # Verify transitions exist
        transitions = [t for t, _ in transformation.transitions.all()]
        assert len(transitions) == 2, f"Transformation should have 2 transitions, got {len(transitions)}"

    # Calculate syntheses for all wisdom units
    print("\n=== Calculating Syntheses ===")
    for i, wu in enumerate(wu_list):
        print(f"Calculating synthesis for WisdomUnit {i+1}/{len(wu_list)}")
        await factory1.calculate_syntheses(wheel=wheel, at=wu)

        # Verify synthesis was created
        synthesis_list = [s for s, _ in wu.synthesis.all()]
        assert len(synthesis_list) >= 1, f"WisdomUnit {i+1} should have at least one synthesis"

        # Verify S+ and S- exist
        for synthesis in synthesis_list:
            s_plus_result = synthesis.s_plus.get()
            s_minus_result = synthesis.s_minus.get()
            assert s_plus_result is not None, "Synthesis should have S+ component"
            assert s_minus_result is not None, "Synthesis should have S- component"

    # Calculate score (optional, but useful to verify scoring works)
    # Note: Scoring requires TaroRank setup
    # assert wheel.score is not None, "Wheel should have a score"

    print("\n" + "="*80)
    print(f"FULL BLOWN WHEEL (with {number_of_thoughts} thoughts: Action-Reflection, Spiral, Audit, and Syntheses)")
    print("="*80)
    print(f"{wheel:scores}")

    # Print each wisdom unit with full details (including synthesis and rationales)
    # Use polar_pairs_ordered to get wisdom units in ta_cycle order with correct polarity
    for i, pair in enumerate(wheel.polar_pairs_ordered):
        print(f"\n{'='*80}")
        print(f"WisdomUnit {i+1} - Full Details (Polarity: {pair.polarity})")
        print(f"{'='*80}")
        print(f"{pair:full:compact}")

@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("number_of_thoughts", [
    2,
    3,
])
async def test_wheel_spiral(number_of_thoughts):
    """
    Test with DiscreteSpiral decorator only (no Action-Reflection, no Synthesis).
    Verifies that cycles and spiral are created correctly.
    """
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    factory1 = DecoratorDiscreteSpiral(builder=factory)
    wheels = await factory1.build_wheel_permutations(theses=[None]*number_of_thoughts)

    assert len(wheels) > 0, "Should generate at least one wheel"
    wheel = wheels[0]

    # Verify structure
    assert wheel.polarity_count == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom units, got {wheel.polarity_count}"

    # Verify cycles exist
    t_cycle_result = wheel.t_cycle.get()
    assert t_cycle_result is not None, "T-cycle should exist"

    ta_cycle_result = wheel.ta_cycle.get()
    assert ta_cycle_result is not None, "TA-cycle should exist"

    # Calculate transitions (spiral will be created during this step)
    await factory1.calculate_transitions(wheel=wheel)

    # Get wisdom units
    wu_list = [wu for wu, _ in wheel.wisdom_units.all()]
    assert len(wu_list) == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom units, got {len(wu_list)}"

    # Verify spiral was created (MUST exist after calculate_transitions)
    spiral_result = wheel.spiral.get()
    assert spiral_result is not None, "Spiral MUST be created by DecoratorDiscreteSpiral.calculate_transitions()"

    spiral_obj, _ = spiral_result
    spiral_transitions = [t for t, _ in spiral_obj.transitions.all()]
    expected_transitions = number_of_thoughts * 2  # 2 segments per wisdom unit
    assert len(spiral_transitions) == expected_transitions, f"Spiral should have exactly {expected_transitions} transitions, got {len(spiral_transitions)}"
    print(f"\n✓ Spiral created with {len(spiral_transitions)} transitions")

    # Verify each transition has rationale
    for trans in spiral_transitions:
        rationales = [r for r, _ in trans.rationales.all()]
        assert len(rationales) >= 1, "Each spiral transition should have at least one rationale"

    # NO SYNTHESIS CALCULATION - that's only for test_full_blown_wheel

    print("\n" + "="*80)
    print(f"WHEEL WITH SPIRAL (with {number_of_thoughts} thoughts: no Action-Reflection, no Synthesis)")
    print("="*80)
    print(str(wheel))

@pytest.mark.asyncio
@observe()
@pytest.mark.parametrize("number_of_thoughts", [
    1,
    2,
])
async def test_wheel_acre(number_of_thoughts, request):
    # Use request fixture to access di_container (works with @observe decorator)
    di_container = request.getfixturevalue('di_container')

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
    assert len(
        wu_list) == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom unit(s), got {len(wu_list)}"
    first_wu = wu_list[0]

    # Check transformation was created (Action-Reflection)
    transformation_result = first_wu.transformation.get()
    assert transformation_result is not None, "Transformation should be created by DecoratorActionReflection"
    transformation, _ = transformation_result

    # Verify ac_re wisdom unit exists
    ac_re_result = transformation.ac_re.get()
    assert ac_re_result is not None, "Transformation should have ac_re WisdomUnit attached"
    ac_re_wu, _ = ac_re_result

    # Verify all 6 components exist in ac_re
    from dialectical_framework.graph.nodes.wisdom_unit import (
        POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
        POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS
    )
    for pos_name, pos in [("T/Ac", POSITION_T), ("T+/Ac+", POSITION_T_PLUS), ("T-/Ac-", POSITION_T_MINUS),
                           ("A/Re", POSITION_A), ("A+/Re+", POSITION_A_PLUS), ("A-/Re-", POSITION_A_MINUS)]:
        manager = ac_re_wu.get_relationship_manager_by_position(pos)
        result = manager.get()
        assert result is not None, f"AC/RE WisdomUnit missing component at position {pos_name}"

    print(f"\n✓ AC/RE WisdomUnit has all 6 components attached")

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

    # Store old ac_re ID before calling calculate_transitions again
    old_ac_re_id = ac_re_wu._id

    # Call calculate_transitions AGAIN to test duplicate detection AND ac_re replacement
    await factory2.calculate_transitions(wheel)

    # Verify still exactly 2 transitions (no duplicates created)
    transitions_after = [t for t, _ in transformation.transitions.all()]
    assert len(transitions_after) == 2, f"Should still have exactly 2 transitions after second call, got {len(transitions_after)}"

    # Verify rationale count increased (new rationales added to existing transitions)
    for trans in transitions_after:
        new_count = len([r for r, _ in trans.rationales.all()])
        old_count = initial_rationale_counts[trans._id]
        assert new_count > old_count, f"Transition should have more rationales after second call: {old_count} → {new_count}"

    # Verify NEW ac_re was created and connected (replace logic)
    new_ac_re_result = transformation.ac_re.get()
    assert new_ac_re_result is not None, "Transformation should have new ac_re after second call"
    new_ac_re_wu, _ = new_ac_re_result
    assert new_ac_re_wu._id != old_ac_re_id, "Should have NEW ac_re (different ID)"

    # Verify old ac_re was DELETED (not orphaned)
    db = di_container.graph_db()
    old_ac_re_check = list(db.execute_and_fetch(
        "MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": old_ac_re_id}
    ))
    assert len(old_ac_re_check) == 0, f"Old ac_re should be DELETED (not orphaned), but still exists: {old_ac_re_id}"

    print("\n✓ Old ac_re was properly deleted (not orphaned) when calculate_transitions called twice")

    print("\n" + "="*80)
    print(f"ACTION-REFLECTION WHEEL (with {number_of_thoughts} thought(s))")
    print("="*80)
    print(str(wheel))
