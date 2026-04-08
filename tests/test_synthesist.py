import pytest
from langfuse.decorators import observe

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
# Graph-native imports
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as GraphDialecticalComponent
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit as GraphWisdomUnit
from tests.test_analyst import user_message


@pytest.mark.asyncio
@observe()
async def test_simple_wheel():
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None])
    assert wheels[0].polarity_count == 1  # Graph-native uses polarity_count instead of order

    # Verify eager scoring (Feature #1)
    assert wheels[0].score is not None, "Wheel should be scored after build"

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

    # Graph-native: get cycle relationship
    cycle_result = wheels[0].cycle.get()
    assert cycle_result is not None

    # Graph-native: get probability estimations from rationales
    # (not wheel.probability which is TaroRank-computed and may be overwritten)
    from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation
    rationale_probs = []
    for w in wheels:
        rationales = list(w.rationales.all())
        if rationales:
            rat, _ = rationales[0]
            # Get ProbabilityEstimation provided by this rationale
            for est, _ in rat.provided_estimations.all():
                if isinstance(est, ProbabilityEstimation):
                    rationale_probs.append(est.value)
                    break

    # Rationale-provided probabilities should sum to 1 (normalized across competing arrangements)
    if rationale_probs:
        assert abs(sum(rationale_probs) - 1.0) < 0.01, f"Rationale probabilities should sum to 1.0, got {sum(rationale_probs)}"

    # Graph-native: use polarity_count instead of order
    for wheel in wheels:
        assert wheel.polarity_count == number_of_thoughts
        print("\n")
        print(wheel)


@pytest.mark.asyncio
async def test_causality_sequencer(di_container):
    """Test causality sequencer with graph-native WisdomUnits.

    Workflow:
    1. build_wheels() - creates saved (uncommitted) structures
    2. Connect to parent Cycle and commit
    3. estimate() - attaches AI-generated Rationale and Estimation nodes
    """
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation
    from dialectical_framework.synthesist.causality.causality_sequencer_balanced import \
        CausalitySequencerBalanced

    # Create graph-native components
    t1 = GraphDialecticalComponent(statement="Remote work increases flexibility")
    t1.commit()
    a1 = GraphDialecticalComponent(statement="Remote work reduces collaboration")
    a1.commit()

    t2 = GraphDialecticalComponent(statement="Async communication enables focus")
    t2.commit()
    a2 = GraphDialecticalComponent(statement="Async communication creates delays")
    a2.commit()

    # Create two graph-native WisdomUnits
    wu1 = GraphWisdomUnit(reasoning_mode="work_context")
    wu1.save()
    wu1.t.connect(t1, properties={'alias': 'T1'})
    wu1.a.connect(a1, properties={'alias': 'A1'})

    wu2 = GraphWisdomUnit(reasoning_mode="communication_context")
    wu2.save()
    wu2.t.connect(t2, properties={'alias': 'T2'})
    wu2.a.connect(a2, properties={'alias': 'A2'})

    # Test causality sequencer (DI will inject brain and settings automatically)
    sequencer = CausalitySequencerBalanced()

    # Commit WisdomUnits first
    wu1.commit()
    wu2.commit()

    # Use arrange() to create Cycles and Wheels from WisdomUnits
    # In the new model, arrange takes a list of WisdomUnits directly
    cycles = sequencer.arrange([wu1, wu2], intent="preset:balanced")

    # Commit Cycles and Wheels
    for cycle in cycles:
        cycle.commit()
        for wheel, _ in cycle.wheels.all():
            wheel.commit()

    # Get wheels from the first cycle
    wheels = [w for w, _ in cycles[0].wheels.all()]

    # Assertions
    assert len(cycles) > 0, "Should generate at least one cycle"
    assert len(wheels) > 0, "Should generate at least one wheel"
    assert all(isinstance(wheel, Wheel) for wheel in wheels), "All should be Wheel objects"
    assert all(wheel.is_committed for wheel in wheels), "All wheels should be committed"

    # Attach AI estimations (creates Rationale + Estimation nodes directly)
    await sequencer.estimate(wheels)

    # Verify Rationale and Estimation nodes were created
    rationale_probs = []
    for wheel in wheels:
        rationales = list(wheel.rationales.all())
        assert len(rationales) > 0, "Wheel should have rationale after estimate()"
        rat, _ = rationales[0]
        # Get ProbabilityEstimation provided by this rationale
        for est, _ in rat.provided_estimations.all():
            if isinstance(est, ProbabilityEstimation):
                rationale_probs.append(est.value)
                break

    # Verify probability normalization
    total_prob = sum(rationale_probs)
    assert abs(total_prob - 1.0) < 0.01, f"Total probability should be ~1.0, got {total_prob}"

    print("\n=== Generated Wheels (committed with estimations) ===")
    for i, wheel in enumerate(wheels, 1):
        print(f"\nWheel {i}:")
        rationales = list(wheel.rationales.all())
        if rationales:
            rat, _ = rationales[0]
            print(f"  Rationale: {rat.summary[:100] if rat.summary else 'N/A'}...")

            # Get probability from estimation
            for est, _ in rat.provided_estimations.all():
                if isinstance(est, ProbabilityEstimation):
                    print(f"  Probability: {est.value}")
                    break

        print(f"  Components: {len(wheel.dialectical_components) if wheel.dialectical_components else 0}")

        # Verify transition probabilities were set
        transitions = wheel.transitions
        if transitions:
            trans_probs = [t.probability for t in transitions if t.probability is not None]
            if trans_probs:
                product = 1.0
                for p in trans_probs:
                    product *= p
                print(f"  Transition probabilities: {trans_probs}")
                print(f"  Product: {product:.6f}")

@pytest.mark.asyncio
async def test_redefine_is_dirty_optimization():
    """Test that redefine preserves wheels when no modifications made (Feature #2)."""
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None, None])

    original_wheel_uid = wheels[0].hash
    original_wu_uids = [wu.hash for wu in wheels[0]._wisdom_units]  # wisdom_units is a list property

    # Test 1: Empty dict - should preserve originals (first-level optimization)
    new_wheels = await factory.redefine(modified_statement_per_alias={})

    assert new_wheels[0].hash == original_wheel_uid, "Empty redefine should preserve original wheel"
    assert len(new_wheels) == len(wheels), "Should return same number of wheels"

    print("\n=== First-level is_dirty optimization test passed ===")
    print(f"Original wheel UID: {original_wheel_uid}")
    print(f"Returned wheel UID: {new_wheels[0].hash}")
    print("Wheels were preserved without calling redefine()")

    # Test 2: Redefine with same statements - should preserve originals (second-level optimization)
    # Get original statements
    wus = sorted(wheels[0]._wisdom_units, key=lambda wu: wu.get_human_friendly_index())
    original_t1_statement = wus[0].get_component("T").statement if wus[0].get_component("T") else None

    if original_t1_statement:
        # Pass the same statement - should return original WU
        new_wheels2 = await factory.redefine(modified_statement_per_alias={"T1": original_t1_statement})

        # Wheel should be preserved (second-level optimization)
        assert new_wheels2[0].hash == original_wheel_uid, "Redefine with same statement should preserve original wheel"

        # WU should be the same (returned original)
        new_wu_uids = [wu.hash for wu in new_wheels2[0]._wisdom_units]
        assert new_wu_uids == original_wu_uids, "WUs should be unchanged when statement is identical"

        print("\n=== Second-level is_dirty optimization test passed ===")
        print(f"Redefined with same statement: {original_t1_statement[:50]}...")
        print(f"WU UIDs unchanged: {new_wu_uids[0] == original_wu_uids[0]}")
        print("Wheel and WUs were preserved without recalculating cycles")

@pytest.mark.asyncio
async def test_selective_synthesis():
    """Test synthesizing specific WUs only (Feature #3).

    Note: Synthesis requires a Transformation target. WisdomUnits need to have
    their transformations calculated before synthesis can be created.
    This test creates proper Transformations with their own Transitions.
    """
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition

    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None, None])
    wheel = wheels[0]

    wus = wheel._wisdom_units  # wisdom_units is already a list property
    assert len(wus) == 2, "Should have 2 WUs"

    # Create a Transformation for the first WU so synthesis has a target
    wu = wus[0]
    transformation = Transformation()
    transformation.set_wisdom_unit(wu)
    transformation.save()

    # Create dedicated transitions for the Transformation
    # Transformation needs transitions through the WU's T-/A+ path (action-reflection)
    # Use position accessors instead of alias lookup (aliases may include index like "T1-")
    t_minus_result = wu.t_minus.get()
    a_plus_result = wu.a_plus.get()
    t_minus = t_minus_result[0] if t_minus_result else None
    a_plus = a_plus_result[0] if a_plus_result else None

    if t_minus and a_plus:
        # Create T- → A+ transition
        trans1 = Transition()
        trans1.set_source(t_minus)
        trans1.set_target(a_plus)
        trans1.commit()
        trans1.cycle.connect(transformation)

        # Create A+ → T- transition (closing the loop)
        trans2 = Transition()
        trans2.set_source(a_plus)
        trans2.set_target(t_minus)
        trans2.commit()
        trans2.cycle.connect(transformation)

        transformation.commit()

        # Synthesize only first WU (now has a transformation)
        syntheses = await factory.calculate_syntheses(wheel=wheel, at=wu)

        assert len(syntheses) == 1, "Should create synthesis for 1 WU only"

        # Verify synthesis was created with S+/S- components
        synthesis = syntheses[0]
        assert synthesis.s_plus.get() is not None, "Synthesis should have S+ component"
        assert synthesis.s_minus.get() is not None, "Synthesis should have S- component"

        # Verify wheel was rescored after synthesis
        assert wheel.score is not None, "Wheel should be rescored after synthesis"

        print("\n=== Selective synthesis test passed ===")
        print(f"Created {len(syntheses)} synthesis for 1 WU")
        print(f"Synthesis S+: {synthesis.s_plus.get()[0].statement if synthesis.s_plus.get() else 'None'}")
        print(f"Synthesis S-: {synthesis.s_minus.get()[0].statement if synthesis.s_minus.get() else 'None'}")
        print(f"Wheel score after synthesis: {wheel.score}")
    else:
        # WU doesn't have T-/A+ components (incomplete WU) - skip synthesis test
        pytest.skip("WU missing T- or A+ components required for Transformation")
