import pytest
from langfuse.decorators import observe

from dialectical_framework.synthesist.wisdom.decorator_action_reflection import DecoratorActionReflection
from dialectical_framework.synthesist.wisdom.decorator_discrete_spiral import DecoratorDiscreteSpiral
from dialectical_framework.synthesist.wisdom.decorator_discrete_spiral_audited import DecoratorDiscreteSpiralAudited
from dialectical_framework.dialectical_reasoning import DialecticalReasoning

user_message = "Putin started the war, Ukraine will not surrender and will finally win!"


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

    # Verify cycle exists (new architecture: Wheel belongs to Cycle)
    cycle_result = wheel.cycle.get()
    assert cycle_result is not None, "Wheel should belong to a Cycle"

    # Verify Nexus exists (via cycle)
    cycle_obj, _ = cycle_result
    nexus = cycle_obj.get_nexus()
    assert nexus is not None, "Cycle should belong to a Nexus"

    # ============================================================================
    # ARCHITECTURE VERIFICATION: Cycle vs Wheel structure (per graph.md)
    # - Cycle (t_cycle) = thesis-only ordering (T1 → T2)
    # - Wheel = detailed arrangement with all positions (T1 → T2 → A1 → A2)
    # ============================================================================

    # Verify t_cycle contains ONLY thesis components (T positions)
    t_cycle_transitions = cycle_obj.transitions
    t_cycle_component_count = len(t_cycle_transitions)
    assert t_cycle_component_count == number_of_thoughts, (
        f"t_cycle should have exactly {number_of_thoughts} transitions (thesis-only), "
        f"got {t_cycle_component_count}. "
        f"If you see {number_of_thoughts * 2} transitions, the t_cycle incorrectly includes antithesis components!"
    )

    # Verify t_cycle transitions only connect thesis (T) components, not antithesis (A)
    for trans in t_cycle_transitions:
        source_result = trans.source.get()
        target_result = trans.target.get()
        assert source_result is not None, "t_cycle transition should have source"
        assert target_result is not None, "t_cycle transition should have target"

        source_comp, _ = source_result

        # Check that source component is from T position (not A position)
        wu_list_pre = wheel.wisdom_units
        for wu in wu_list_pre:
            t_result = wu.t.get()
            if t_result and t_result[0].hash == source_comp.hash:
                # Source is a T component - good
                break
            a_result = wu.a.get()
            if a_result and a_result[0].hash == source_comp.hash:
                raise AssertionError(
                    f"t_cycle contains antithesis component! "
                    f"Component '{source_comp.statement[:50]}...' is at A position. "
                    f"t_cycle should only contain thesis (T) components per graph.md architecture."
                )

    # Verify Wheel has MORE transitions than t_cycle (detailed arrangement)
    wheel_transitions = wheel.transitions
    wheel_transition_count = len(wheel_transitions)
    expected_wheel_transitions = number_of_thoughts * 2  # T1, T2, A1, A2 for 2 WUs
    assert wheel_transition_count == expected_wheel_transitions, (
        f"Wheel should have {expected_wheel_transitions} transitions (all T and A positions), "
        f"got {wheel_transition_count}"
    )

    print(f"\n✓ Architecture verified: t_cycle has {t_cycle_component_count} transitions (thesis-only), "
          f"Wheel has {wheel_transition_count} transitions (detailed)")

    # ============================================================================
    # SCORING VERIFICATION: t_cycle must have AI-assessed rationales
    # - Rationale should exist with reasoning from AI
    # - RelevanceEstimation should reflect AI's probability assessment
    # - P/R should NOT both be 1.0 (that indicates missing AI assessment)
    # ============================================================================

    # Verify t_cycle has rationales (AI assessment)
    t_cycle_rationales = list(cycle_obj.rationales.all())
    assert len(t_cycle_rationales) > 0, (
        "t_cycle should have at least one rationale with AI assessment. "
        "Missing rationale indicates _normalize() didn't connect the rationale properly."
    )

    rationale, _ = t_cycle_rationales[0]
    assert rationale.text is not None and len(rationale.text) > 10, (
        f"t_cycle rationale should have meaningful AI-generated text, got: '{rationale.text}'"
    )

    # Verify rationale provides RelevanceEstimation (AI's probability assessment stored as R)
    # In the new model, estimations target the cycle and the rationale provides them
    from dialectical_framework.graph.nodes.estimation import RelevanceEstimation
    rationale_provided = list(rationale.provided_estimations.all())
    relevance_estimations = [
        est for est, _ in rationale_provided
        if isinstance(est, RelevanceEstimation)
    ]
    assert len(relevance_estimations) > 0, (
        "t_cycle rationale should provide RelevanceEstimation (AI's probability assessment). "
        "Missing estimation indicates _normalize() didn't call upsert_estimation correctly with source."
    )

    ai_relevance = relevance_estimations[0].value
    print(f"✓ t_cycle rationale provides AI relevance estimate: {ai_relevance:.3f}")

    # Warn if AI returned very high probability (might indicate prompt issues)
    if ai_relevance >= 0.95:
        print(f"⚠ WARNING: AI returned very high relevance ({ai_relevance:.3f}) - "
              f"this may indicate the AI isn't critically assessing the cycle")

    # Calculate transitions (spiral will be created during this step)
    await factory1.calculate_transitions(wheel)

    # Verify spiral was created
    spiral_result = wheel.spiral.get()
    assert spiral_result is not None, "Spiral MUST be created by DecoratorDiscreteSpiral"

    # Get wisdom units
    wu_list = wheel.wisdom_units
    assert len(wu_list) == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom units, got {len(wu_list)}"

    # Verify transformations exist (Action-Reflection)
    for wu in wu_list:
        transformation_result = wu.transformations.get()
        assert transformation_result is not None, f"WisdomUnit {wu.hash} should have transformation"
        transformation, _ = transformation_result

        # Verify 6 positions exist on Transformation (Ac, Re, Ac+, Ac-, Re+, Re-)
        from dialectical_framework.graph.nodes.transformation import (
            POSITION_AC, POSITION_RE, POSITION_AC_PLUS, POSITION_AC_MINUS,
            POSITION_RE_PLUS, POSITION_RE_MINUS
        )
        for pos in [POSITION_AC, POSITION_RE, POSITION_AC_PLUS, POSITION_AC_MINUS,
                    POSITION_RE_PLUS, POSITION_RE_MINUS]:
            manager = transformation.get_relationship_manager_by_position(pos)
            result = manager.get()
            assert result is not None, f"Transformation should have transition at position {pos}"

    # Calculate syntheses for all wisdom units
    print("\n=== Calculating Syntheses ===")
    for i, wu in enumerate(wu_list):
        print(f"Calculating synthesis for WisdomUnit {i+1}/{len(wu_list)}")
        await factory1.calculate_syntheses(wheel=wheel, at=wu)

        # Verify synthesis was created (connected to WU directly)
        synthesis_list = [s for s, _ in wu.synthesis.all()]
        assert len(synthesis_list) >= 1, f"WisdomUnit {i+1} should have at least one synthesis"

        # Verify S+ and S- exist
        for synthesis in synthesis_list:
            s_plus_result = synthesis.s_plus.get()
            s_minus_result = synthesis.s_minus.get()
            assert s_plus_result is not None, "Synthesis should have S+ component"
            assert s_minus_result is not None, "Synthesis should have S- component"

    # Score the wheel after all modifications are complete
    # This calculates scores for wheel → cycles → transitions → rationales
    factory1.scorer.calculate_score(wheel, force=True)

    print("\n" + "="*80)
    print(f"FULL BLOWN WHEEL (with {number_of_thoughts} thoughts: Action-Reflection, Spiral, Audit, and Syntheses)")
    print("="*80)
    print(f"{wheel:scores}")

    # Print each wisdom unit with full details (including synthesis and rationales)
    # Use polar_pairs to get wisdom units in ta_cycle order with correct polarity
    for i, pair in enumerate(wheel.polar_pairs):
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

    # Verify cycle exists (new architecture: Wheel belongs to Cycle)
    cycle_result = wheel.cycle.get()
    assert cycle_result is not None, "Wheel should belong to a Cycle"

    # Verify Nexus exists (via cycle)
    cycle_obj, _ = cycle_result
    nexus = cycle_obj.get_nexus()
    assert nexus is not None, "Cycle should belong to a Nexus"

    # Calculate transitions (spiral will be created during this step)
    await factory1.calculate_transitions(wheel=wheel)

    # Get wisdom units
    wu_list = wheel.wisdom_units
    assert len(wu_list) == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom units, got {len(wu_list)}"

    # Verify spiral was created (MUST exist after calculate_transitions)
    spiral_result = wheel.spiral.get()
    assert spiral_result is not None, "Spiral MUST be created by DecoratorDiscreteSpiral.calculate_transitions()"

    spiral_obj, _ = spiral_result
    spiral_transitions = spiral_obj.transitions
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

    # Check that cycle exists (new architecture: Wheel belongs to Cycle)
    cycle_result = wheel.cycle.get()
    assert cycle_result is not None, "Wheel should belong to a Cycle"

    # Verify Nexus exists (via cycle)
    cycle_obj, _ = cycle_result
    nexus = cycle_obj.get_nexus()
    assert nexus is not None, "Cycle should belong to a Nexus"

    # First call to calculate_transitions
    await factory2.calculate_transitions(wheel)

    # Get first wisdom unit
    wu_list = wheel.wisdom_units
    assert len(
        wu_list) == number_of_thoughts, f"Should have exactly {number_of_thoughts} wisdom unit(s), got {len(wu_list)}"
    first_wu = wu_list[0]

    # Check transformation was created (Action-Reflection)
    transformation_result = first_wu.transformations.get()
    assert transformation_result is not None, "Transformation should be created by DecoratorActionReflection"
    transformation, _ = transformation_result

    # Verify all 6 positions exist on Transformation (Ac, Re, Ac+, Ac-, Re+, Re-)
    from dialectical_framework.graph.nodes.transformation import (
        POSITION_AC, POSITION_RE, POSITION_AC_PLUS, POSITION_AC_MINUS,
        POSITION_RE_PLUS, POSITION_RE_MINUS
    )
    for pos_name, pos in [("Ac", POSITION_AC), ("Re", POSITION_RE),
                          ("Ac+", POSITION_AC_PLUS), ("Ac-", POSITION_AC_MINUS),
                          ("Re+", POSITION_RE_PLUS), ("Re-", POSITION_RE_MINUS)]:
        manager = transformation.get_relationship_manager_by_position(pos)
        result = manager.get()
        assert result is not None, f"Transformation missing component at position {pos_name}"

    print(f"\n✓ Transformation has all 6 positions (Ac, Re, Ac+, Ac-, Re+, Re-)")

    # Store initial transformation count
    initial_transformation_count = first_wu.transformations.count()
    old_transformation_id = transformation._id

    # Call calculate_transitions AGAIN - should detect duplicate and return existing
    await factory2.calculate_transitions(wheel)

    # Verify same transformation is returned (duplicate detection)
    transformation_count_after = first_wu.transformations.count()
    assert transformation_count_after == initial_transformation_count, (
        f"Calling calculate_transitions again should return existing transformation, "
        f"not create new one. Before: {initial_transformation_count}, After: {transformation_count_after}"
    )

    # Get the transformation again to verify it's the same one
    transformation_after_result = first_wu.transformations.get()
    assert transformation_after_result is not None, "Should still have transformation"
    transformation_after, _ = transformation_after_result
    assert transformation_after._id == old_transformation_id, (
        "Should return same transformation (duplicate detection)"
    )

    print("\n✓ Duplicate transformation detection works correctly")

    print("\n" + "="*80)
    print(f"ACTION-REFLECTION WHEEL (with {number_of_thoughts} thought(s))")
    print("="*80)
    print(str(wheel))
