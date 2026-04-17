import pytest
from langfuse.decorators import observe

from dialectical_framework.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.enums.causality_preset import CausalityPreset
# Graph-native imports
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as GraphDialecticalComponent
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.perspective import Perspective as GraphPerspective

user_message = "Putin started the war, Ukraine will not surrender and will finally win!"


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
    """Test causality sequencer with graph-native Perspectives.

    Workflow:
    1. BuildWheels skill creates Cycles and Wheels from Perspectives in a Nexus
    2. Estimation attaches AI-generated Rationale and Estimation nodes
    """
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.relationships.polarity_relationship import (
        HasPolarityRelationship, TPlusRelationship, TMinusRelationship,
        APlusRelationship, AMinusRelationship,
    )
    from dialectical_framework.agents.explorer.skills.build_wheels import BuildWheels
    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.scope_context import scope

    def create_pp(index: int) -> GraphPerspective:
        """Create a complete Perspective with Polarity and poles."""
        # Create T and A
        t = GraphDialecticalComponent(
            statement=f"Thesis {index}", meaning=f"thesis:test:{index}"
        )
        t.commit()
        a = GraphDialecticalComponent(
            statement=f"Antithesis {index}", meaning=f"antithesis:test:{index}"
        )
        a.commit()

        # Create Polarity
        polarity = Polarity(intent="test")
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()

        # Create PP
        pp = GraphPerspective(intent="test")
        pp.save()
        pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

        # Create poles
        t_plus = GraphDialecticalComponent(
            statement=f"T+ benefit {index}", meaning=f"thesis:positive:{index}"
        )
        t_plus.commit()
        t_minus = GraphDialecticalComponent(
            statement=f"T- drawback {index}", meaning=f"thesis:negative:{index}"
        )
        t_minus.commit()
        a_plus = GraphDialecticalComponent(
            statement=f"A+ benefit {index}", meaning=f"antithesis:positive:{index}"
        )
        a_plus.commit()
        a_minus = GraphDialecticalComponent(
            statement=f"A- drawback {index}", meaning=f"antithesis:negative:{index}"
        )
        a_minus.commit()

        pp.t_plus.connect(
            t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9)
        )
        pp.t_minus.connect(
            t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9)
        )
        pp.a_plus.connect(
            a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9)
        )
        pp.a_minus.connect(
            a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9)
        )

        pp.commit()
        return pp

    # Create scope
    case_node = Case()
    case_node.commit()

    with scope(case_node.case_id):
        # Create two Perspectives
        pp1 = create_pp(1)
        pp2 = create_pp(2)

        # Create Nexus and use BuildWheels to create and estimate cycles
        nexus = Nexus(case_id=case_node.case_id, preset=CausalityPreset.BALANCED)
        nexus.commit()

        skill = BuildWheels(
            nexus_hash=nexus.hash,
            perspective_hashes=[pp1.hash, pp2.hash],
        )
        result = await skill.execute()

        cycles = result.new_cycles

        # Assertions
        assert len(cycles) > 0, "Should generate at least one cycle"
        assert all(isinstance(cycle, Cycle) for cycle in cycles), "All should be Cycle objects"
        assert all(cycle.is_committed for cycle in cycles), "All cycles should be committed"

        # Verify Rationale and Estimation nodes were created on cycles
        rationale_probs = []
        for cycle in cycles:
            rationales = list(cycle.rationales.all())
            assert len(rationales) > 0, "Cycle should have rationale after estimate()"
            rat, _ = rationales[0]
            # Get ProbabilityEstimation provided by this rationale
            for est, _ in rat.provided_estimations.all():
                if isinstance(est, ProbabilityEstimation):
                    rationale_probs.append(est.value)
                    break

        # Verify probability normalization
        total_prob = sum(rationale_probs)
        assert abs(total_prob - 1.0) < 0.01, f"Total probability should be ~1.0, got {total_prob}"

        print("\n=== Generated Cycles (committed with estimations) ===")
        for i, cycle in enumerate(cycles, 1):
            print(f"\nCycle {i}:")
            rationales = list(cycle.rationales.all())
            if rationales:
                rat, _ = rationales[0]
                print(f"  Rationale: {rat.summary[:100] if rat.summary else 'N/A'}...")

                # Get probability from estimation
                for est, _ in rat.provided_estimations.all():
                    if isinstance(est, ProbabilityEstimation):
                        print(f"  Probability: {est.value}")
                        break

            print(f"  Perspectives: {cycle.perspective_count}")

@pytest.mark.asyncio
async def test_redefine_is_dirty_optimization():
    """Test that redefine preserves wheels when no modifications made (Feature #2)."""
    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None, None])

    original_wheel_uid = wheels[0].hash
    original_pp_uids = [pp.hash for pp in wheels[0]._perspectives]  # perspectives is a list property

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
    pps = sorted(wheels[0]._perspectives, key=lambda pp: pp.get_human_friendly_index())
    original_t1_statement = pps[0].get_component("T").statement if pps[0].get_component("T") else None

    if original_t1_statement:
        # Pass the same statement - should return original PP
        new_wheels2 = await factory.redefine(modified_statement_per_alias={"T1": original_t1_statement})

        # Wheel should be preserved (second-level optimization)
        assert new_wheels2[0].hash == original_wheel_uid, "Redefine with same statement should preserve original wheel"

        # PP should be the same (returned original)
        new_pp_uids = [pp.hash for pp in new_wheels2[0]._perspectives]
        assert new_pp_uids == original_pp_uids, "PPs should be unchanged when statement is identical"

        print("\n=== Second-level is_dirty optimization test passed ===")
        print(f"Redefined with same statement: {original_t1_statement[:50]}...")
        print(f"PP UIDs unchanged: {new_pp_uids[0] == original_pp_uids[0]}")
        print("Wheel and PPs were preserved without recalculating cycles")

@pytest.mark.asyncio
async def test_selective_synthesis():
    """Test synthesizing specific PPs only (Feature #3).

    Note: Synthesis requires a Transformation target. Perspectives need to have
    their transformations calculated before synthesis can be created.
    This test creates proper Transformations with their own Transitions.
    """
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition

    factory = DialecticalReasoning.wheel_builder(text=user_message)
    wheels = await factory.build_wheel_permutations(theses=[None, None])
    wheel = wheels[0]

    pps = wheel._perspectives  # perspectives is already a list property
    assert len(pps) == 2, "Should have 2 PPs"

    # Create a Transformation for the first PP so synthesis has a target
    pp = pps[0]
    transformation = Transformation()
    transformation.set_perspective(pp)
    transformation.save()

    # Create dedicated transitions for the Transformation
    # Transformation needs transitions through the PP's T-/A+ path (action-reflection)
    # Use position accessors instead of alias lookup (aliases may include index like "T1-")
    t_minus_result = pp.t_minus.get()
    a_plus_result = pp.a_plus.get()
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

        # Synthesize only first PP (now has a transformation)
        syntheses = await factory.calculate_syntheses(wheel=wheel, at=pp)

        assert len(syntheses) == 1, "Should create synthesis for 1 PP only"

        # Verify synthesis was created with S+/S- components
        synthesis = syntheses[0]
        assert synthesis.s_plus.get() is not None, "Synthesis should have S+ component"
        assert synthesis.s_minus.get() is not None, "Synthesis should have S- component"

        # Verify wheel was rescored after synthesis
        assert wheel.score is not None, "Wheel should be rescored after synthesis"

        print("\n=== Selective synthesis test passed ===")
        print(f"Created {len(syntheses)} synthesis for 1 PP")
        print(f"Synthesis S+: {synthesis.s_plus.get()[0].statement if synthesis.s_plus.get() else 'None'}")
        print(f"Synthesis S-: {synthesis.s_minus.get()[0].statement if synthesis.s_minus.get() else 'None'}")
        print(f"Wheel score after synthesis: {wheel.score}")
    else:
        # PP doesn't have T-/A+ components (incomplete PP) - skip synthesis test
        pytest.skip("PP missing T- or A+ components required for Transformation")
