import pytest
from dependency_injector import providers
from langfuse.decorators import observe

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
# Graph-native imports
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as GraphDialecticalComponent
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit as GraphWisdomUnit
from dialectical_framework.synthesist.polarity.polarity_reasoner import PolarityReasoner
from dialectical_framework.synthesist.polarity.reason_fast import ReasonFast
from dialectical_framework.synthesist.polarity.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.polarity.reason_fast_polarized_conflict import ReasonFastPolarizedConflict
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
    # 4,
    # 3,
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

    # Graph-native: use ta_cycle instead of cycle
    ta_cycle_result = wheels[0].ta_cycle.get()
    assert ta_cycle_result is not None

    # Graph-native: get cycle and access probability
    cycle_probs = []
    for w in wheels:
        ta_cycle_result = w.ta_cycle.get()
        if ta_cycle_result:
            cycle_obj, _ = ta_cycle_result
            if cycle_obj.probability is not None:
                cycle_probs.append(cycle_obj.probability)

    # Probabilities should sum to 1
    if cycle_probs:
        assert abs(sum(cycle_probs) - 1.0) < 0.01  # Allow small floating point error

    # Graph-native: use polarity_count instead of order
    for wheel in wheels:
        assert wheel.polarity_count == number_of_thoughts
        print("\n")
        print(wheel)


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

    # Test redefine with same values - should return original (optimization)
    reasoner = di_container.polarity_reasoner()
    redefined_wu = await reasoner.redefine(
        original=wu,
        t="Courage",  # Same as original - tests optimization
        a="Fear",  # Same as original
    )

    # Basic assertions
    assert redefined_wu.is_complete()

    # Optimization: redefine with same values returns original WU (same UID)
    assert wu.uid == redefined_wu.uid, "Should return original WU when nothing changes"

    # Test redefine with different value - should create new WU
    redefined_wu2 = await reasoner.redefine(
        original=wu,
        t="Bravery",  # Different from original - should create new WU
        a="Fear",
    )

    assert redefined_wu2.is_complete()
    assert wu.uid != redefined_wu2.uid, "Should create new WU when components change"

    # Verify all positions are set in the new WU
    assert redefined_wu2.t.count() == 1
    assert redefined_wu2.t_plus.count() == 1
    assert redefined_wu2.t_minus.count() == 1
    assert redefined_wu2.a.count() == 1
    assert redefined_wu2.a_plus.count() == 1
    assert redefined_wu2.a_minus.count() == 1

    print("\n")
    print("=== Original Graph-Native WisdomUnit ===")
    print(wu.pretty())
    print("\n")
    print("=== Redefined with Same Values (Same UID) ===")
    print(redefined_wu.pretty())
    print("\n")
    print("=== Redefined with Different Values (New UID) ===")
    print(redefined_wu2.pretty())

@pytest.mark.asyncio
async def test_causality_sequencer(di_container):
    """Test causality sequencer with graph-native WisdomUnits."""
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.synthesist.causality.causality_sequencer_balanced import \
        CausalitySequencerBalanced

    # Create graph-native components
    t1 = GraphDialecticalComponent(statement="Remote work increases flexibility")
    t1.save()
    a1 = GraphDialecticalComponent(statement="Remote work reduces collaboration")
    a1.save()

    t2 = GraphDialecticalComponent(statement="Async communication enables focus")
    t2.save()
    a2 = GraphDialecticalComponent(statement="Async communication creates delays")
    a2.save()

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
    sequencer = CausalitySequencerBalanced(text="Remote work and async communication")

    # Arrange WisdomUnits into cycles
    cycles = await sequencer.arrange([wu1, wu2])

    # Assertions
    assert len(cycles) > 0, "Should generate at least one cycle"
    assert all(isinstance(cycle, Cycle) for cycle in cycles), "All should be Cycle objects"

    # Verify each cycle has rationale with normalized probability
    rationale_probs = []
    for cycle in cycles:
        rationales = list(cycle.rationales.all())
        assert len(rationales) > 0, "Each cycle should have at least one rationale"
        rat, _ = rationales[0]
        rationale_probs.append(rat.probability or 0.0)

    # Verify probability normalization on rationales (not cycle.probability which is TaroRank-computed)
    total_prob = sum(rationale_probs)
    assert abs(total_prob - 1.0) < 0.01, f"Total rationale probability should be ~1.0, got {total_prob}"

    print("\n=== Generated Cycles ===")
    for i, cycle in enumerate(cycles, 1):
        print(f"\nCycle {i}:")
        rationales = list(cycle.rationales.all())
        if rationales:
            rat, _ = rationales[0]
            print(f"  Rationale Probability: {rat.probability}")
            print(f"  Rationale Relevance: {rat.relevance}")
            # Note: cycle.dialectical_components is already a list
            print(f"  Components: {len(cycle.dialectical_components) if cycle.dialectical_components else 0}")
            print(f"  Reasoning: {rat.text[:100] if rat.text else 'N/A'}...")

            # Verify transition probabilities were set
            transitions = [trans for trans, _ in cycle.transitions.all()]
            if transitions:
                trans_probs = [t.probability for t in transitions if t.probability is not None]
                if trans_probs:
                    product = 1.0
                    for p in trans_probs:
                        product *= p
                    print(f"  Transition probabilities: {trans_probs}")
                    print(f"  Product: {product:.6f}, Cycle P: {rat.probability}")

@pytest.mark.asyncio
async def test_redefine_is_dirty_optimization():
    """Test that redefine preserves wheels when no modifications made (Feature #2)."""
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None, None])

    original_wheel_uid = wheels[0].uid
    original_wu_uids = [wu.uid for wu, _ in wheels[0].wisdom_units.all()]

    # Test 1: Empty dict - should preserve originals (first-level optimization)
    new_wheels = await factory.redefine(modified_statement_per_alias={})

    assert new_wheels[0].uid == original_wheel_uid, "Empty redefine should preserve original wheel"
    assert len(new_wheels) == len(wheels), "Should return same number of wheels"

    print("\n=== First-level is_dirty optimization test passed ===")
    print(f"Original wheel UID: {original_wheel_uid}")
    print(f"Returned wheel UID: {new_wheels[0].uid}")
    print("Wheels were preserved without calling redefine()")

    # Test 2: Redefine with same statements - should preserve originals (second-level optimization)
    # Get original statements
    wus = sorted([wu for wu, _ in wheels[0].wisdom_units.all()], key=lambda wu: wu.get_human_friendly_index())
    original_t1_statement = wus[0].get_component("T").statement if wus[0].get_component("T") else None

    if original_t1_statement:
        # Pass the same statement - reasoner should return original WU
        new_wheels2 = await factory.redefine(modified_statement_per_alias={"T1": original_t1_statement})

        # Wheel should be preserved (second-level optimization)
        assert new_wheels2[0].uid == original_wheel_uid, "Redefine with same statement should preserve original wheel"

        # WU should be the same (reasoner returned original)
        new_wu_uids = [wu.uid for wu, _ in new_wheels2[0].wisdom_units.all()]
        assert new_wu_uids == original_wu_uids, "WUs should be unchanged when statement is identical"

        print("\n=== Second-level is_dirty optimization test passed ===")
        print(f"Redefined with same statement: {original_t1_statement[:50]}...")
        print(f"WU UIDs unchanged: {new_wu_uids[0] == original_wu_uids[0]}")
        print("Wheel and WUs were preserved without recalculating cycles")

@pytest.mark.asyncio
async def test_selective_synthesis():
    """Test synthesizing specific WUs only (Feature #3)."""
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None, None])
    wheel = wheels[0]

    wus = [wu for wu, _ in wheel.wisdom_units.all()]
    assert len(wus) == 2, "Should have 2 WUs"

    # Synthesize only first WU
    syntheses = await factory.calculate_syntheses(wheel=wheel, at=wus[0])

    assert len(syntheses) == 1, "Should create synthesis for 1 WU only"

    # Verify synthesis is connected to the correct WU
    synthesis = syntheses[0]
    wu_result = synthesis.wisdom_unit.get()
    assert wu_result is not None, "Synthesis should be connected to WU"
    connected_wu, _ = wu_result
    assert connected_wu.uid == wus[0].uid, "Synthesis should be connected to first WU"

    # Verify wheel was rescored after synthesis
    assert wheel.score is not None, "Wheel should be rescored after synthesis"

    print("\n=== Selective synthesis test passed ===")
    print(f"Created {len(syntheses)} synthesis for 1 WU")
    print(f"Synthesis connected to WU: {connected_wu.uid}")
    print(f"Wheel score after synthesis: {wheel.score}")