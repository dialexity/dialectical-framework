"""
Test graph structures with dependency injection.

This test demonstrates creating WisdomUnits with dialectical components
using the clean DI-based API (no db parameter needed!).

The graph database (Memgraph or Neo4j) is injected via dependency injection,
and tests automatically use TestMemgraph/TestNeo4j wrappers for safety.

To run these tests, start your graph database first:
    Memgraph: docker-compose -f docker-compose.test.yml up -d
    Neo4j: docker run -p 7687:7687 neo4j:latest

Then run:
    poetry run pytest tests/test_graph.py -v
"""

import pytest

from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.utils.order_transitions import order_transitions


# Module-level autouse fixture for graph tests only
@pytest.fixture(autouse=True)
def cleanup_graph_db(graph_db_available, di_container):
    """
    Auto-cleanup fixture that runs for every test in this module.

    Automatically skips tests if the configured graph database is not available.
    Cleans up test data before and after each test.

    SAFETY: Only deletes nodes labeled with :___DIALEXITY_TEST___
    This allows tests to run safely alongside production data.
    """
    from tests.conftest import cleanup_test_data

    settings = di_container.settings()
    if not graph_db_available:
        pytest.skip(
            f"{settings.graph_db_vendor} is not available. "
            f"Please start the database and try again."
        )

    # Get graph_db from container (already overridden with Test wrapper)
    db = di_container.graph_db()

    # Clear only test data before each test
    cleanup_test_data(db)

    yield  # No need to yield db, tests use DI

    # Cleanup only test data after test
    try:
        cleanup_test_data(db)
    except Exception:
        pass  # Ignore cleanup errors


def test_create_simple_wisdom_unit():
    """Test creating a WisdomUnit with basic components."""

    # Create a wisdom unit
    wu = WisdomUnit(index=1, reasoning_mode="dialectical")
    wu.save()  # Uses injected graph_db

    # Create thesis components
    t = DialecticalComponent(statement="Democracy empowers citizens")
    t_plus = DialecticalComponent(statement="Democracy promotes equality")
    t_minus = DialecticalComponent(statement="Democracy can be inefficient")

    t.save()
    t_plus.save()
    t_minus.save()

    # Create antithesis components
    a = DialecticalComponent(statement="Authority provides order")
    a_plus = DialecticalComponent(statement="Authority ensures security")
    a_minus = DialecticalComponent(statement="Authority restricts freedom")

    a.save()
    a_plus.save()
    a_minus.save()

    # Connect components to wisdom unit with contextual aliases
    wu.t.connect(t, properties={'alias': 'T'})
    wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
    wu.t_minus.connect(t_minus, properties={'alias': 'T-'})

    wu.a.connect(a, properties={'alias': 'A'})
    wu.a_plus.connect(a_plus, properties={'alias': 'A+'})
    wu.a_minus.connect(a_minus, properties={'alias': 'A-'})

    # Verify connections
    t_component = wu.t.get()
    assert t_component is not None
    assert t_component[0].statement == "Democracy empowers citizens"

    a_component = wu.a.get()
    assert a_component is not None
    assert a_component[0].statement == "Authority provides order"

    # Verify cardinality
    assert wu.t.count() == 1
    assert wu.t_plus.count() == 1
    assert wu.t_minus.count() == 1
    assert wu.a.count() == 1
    assert wu.a_plus.count() == 1
    assert wu.a_minus.count() == 1

    # Verify summary
    summary = wu.get_component_summary()
    assert summary['t'] == 1
    assert summary['t_plus'] == 1
    assert summary['t_minus'] == 1
    assert summary['a'] == 1
    assert summary['a_plus'] == 1
    assert summary['a_minus'] == 1

    print("✓ Successfully created WisdomUnit with all required components")


def test_wisdom_unit_validation():
    """Test WisdomUnit cardinality validation."""

    # Create incomplete wisdom unit
    wu = WisdomUnit()
    wu.save()

    # Add only T component
    t = DialecticalComponent(statement="Test thesis")
    t.save()
    wu.t.connect(t, properties={'alias': 'T'})

    # Validate - should fail (missing other required components)
    is_valid, errors = wu.validate_cardinality()  # No db parameter
    assert not is_valid
    assert len(errors) > 0

    print(f"✓ Validation correctly detected missing components: {len(errors)} errors")


def test_component_aliases():
    """Test getting components with their contextual aliases from relationships."""

    wu = WisdomUnit()
    wu.save()

    # Add components with contextual aliases
    t = DialecticalComponent(statement="Thesis 3")
    a = DialecticalComponent(statement="Antithesis 3")

    t.save()
    a.save()

    wu.t.connect(t, properties={'alias': 'T3'})
    wu.a.connect(a, properties={'alias': 'A3'})

    # Get all components with their aliases from relationships
    components_with_aliases = wu.get_all_components_with_aliases()

    assert len(components_with_aliases) == 2
    aliases = [alias for _, alias in components_with_aliases]
    assert 'T3' in aliases
    assert 'A3' in aliases

    # Test get_component_alias convenience method
    t_alias = wu.get_component_alias(t)
    a_alias = wu.get_component_alias(a)

    assert t_alias == 'T3'
    assert a_alias == 'A3'

    # Test with component not in this wisdom unit
    other_comp = DialecticalComponent(statement="Not connected")
    other_comp.save()
    assert wu.get_component_alias(other_comp) is None

    print(f"✓ Component aliases retrieved from relationships: {aliases}")
    print(f"✓ get_component_alias() works correctly: T={t_alias}, A={a_alias}")


def test_cycle_topology_ordered_transitions():
    """Test cycle topology with ordered transitions."""

    # Create a simple 3-component cycle: T1 → T2 → T3 → T1
    t1 = DialecticalComponent(statement="Component 1")
    t2 = DialecticalComponent(statement="Component 2")
    t3 = DialecticalComponent(statement="Component 3")

    t1.save()
    t2.save()
    t3.save()

    # Create transitions
    trans1 = Transition()  # T1 → T2
    trans2 = Transition()  # T2 → T3
    trans3 = Transition()  # T3 → T1

    trans1.save()
    trans2.save()
    trans3.save()

    # Connect transitions to sources and targets
    trans1.source.connect(t1)
    trans1.target.connect(t2)

    trans2.source.connect(t2)
    trans2.target.connect(t3)

    trans3.source.connect(t3)
    trans3.target.connect(t1)

    # Create cycle and connect transitions
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()

    cycle.transitions.connect(trans1)
    cycle.transitions.connect(trans2)
    cycle.transitions.connect(trans3)

    # Test order_transitions utility
    all_transitions = [trans for trans, _ in cycle.transitions.all()]
    ordered = order_transitions(all_transitions)
    assert len(ordered) == 3, f"Expected 3 transitions, got {len(ordered)}"

    # Verify the ordering follows source→target chain
    source_statements = []
    for trans in ordered:
        source_nodes = [src for src, _ in trans.source.all()]
        if source_nodes:
            source_statements.append(source_nodes[0].statement)

    # Check that we have a valid cycle (each source appears once)
    assert len(set(source_statements)) == 3, "Cycle should have 3 unique sources"
    assert set(source_statements) == {"Component 1", "Component 2", "Component 3"}, "Cycle should contain all components"

    print(f"✓ Cycle topology ordered correctly: {' → '.join(source_statements)}")


def test_cycle_dialectical_components():
    """Test dialectical_components property returns correct components."""

    # Create components
    t1 = DialecticalComponent(statement="Thesis 1")
    t2 = DialecticalComponent(statement="Thesis 2")
    t3 = DialecticalComponent(statement="Thesis 3")

    t1.save()
    t2.save()
    t3.save()

    # Create transitions
    trans1 = Transition()
    trans2 = Transition()
    trans3 = Transition()

    trans1.save()
    trans2.save()
    trans3.save()

    trans1.source.connect(t1)
    trans1.target.connect(t2)
    trans2.source.connect(t2)
    trans2.target.connect(t3)
    trans3.source.connect(t3)
    trans3.target.connect(t1)

    # Create cycle
    cycle = Cycle(causality_type=CausalityType.REALISTIC)
    cycle.save()

    cycle.transitions.connect(trans1)
    cycle.transitions.connect(trans2)
    cycle.transitions.connect(trans3)

    # Test dialectical_components property
    components = cycle.dialectical_components
    assert len(components) == 3, f"Expected 3 components, got {len(components)}"

    statements = [comp.statement for comp in components]
    assert set(statements) == {"Thesis 1", "Thesis 2", "Thesis 3"}, f"Expected all thesis statements, got {statements}"

    print(f"✓ Dialectical components extracted correctly: {statements}")


def test_cycle_str_formatting():
    """Test as_str() method with automatic Wheel resolution."""

    # Create a 4-component cycle
    components = []
    for i in range(1, 5):
        comp = DialecticalComponent(statement=f"Component {i}")
        comp.save()
        components.append(comp)

    # Create transitions in cycle
    transitions = []
    for i in range(4):
        trans = Transition()
        trans.save()
        trans.source.connect(components[i])
        trans.target.connect(components[(i + 1) % 4])
        transitions.append(trans)

    # Create cycle
    cycle = Cycle(causality_type=CausalityType.DESIRABLE)
    cycle.save()

    for trans in transitions:
        cycle.transitions.connect(trans)

    # Create Wheel with WisdomUnits
    wheel = Wheel()
    wheel.save()

    # Connect cycle to wheel as T-cycle
    wheel.t_cycle.connect(cycle)

    # Create WisdomUnit and connect components with aliases
    wu = WisdomUnit()
    wu.save()
    wu.wheel.connect(wheel)

    wu.t.connect(components[0], properties={'alias': 'T'})
    wu.t_plus.connect(components[1], properties={'alias': 'T+'})
    wu.t_minus.connect(components[2], properties={'alias': 'T-'})
    wu.a.connect(components[3], properties={'alias': 'A'})

    # Test 1: Automatic Wheel resolution (no parameters needed!)
    cycle_string = cycle.as_str()
    assert "T" in cycle_string
    assert "T+" in cycle_string
    assert "T-" in cycle_string
    assert "A" in cycle_string

    print(f"✓ Cycle string with automatic wheel resolution: {cycle_string}")

    # Test 2: component.get_alias(wisdom_unit) convenience method
    assert components[0].get_alias(wu) == 'T'
    assert components[1].get_alias(wu) == 'T+'
    assert components[2].get_alias(wu) == 'T-'
    assert components[3].get_alias(wu) == 'A'

    print(f"✓ component.get_alias(wisdom_unit) works correctly")

    # Test 3: Fallback when not connected to wheel
    orphan_cycle = Cycle(causality_type=CausalityType.BALANCED)
    orphan_cycle.save()
    orphan_trans = Transition()
    orphan_trans.save()
    orphan_comp = DialecticalComponent(statement="Orphan component")
    orphan_comp.save()
    orphan_trans.source.connect(orphan_comp)
    orphan_trans.target.connect(orphan_comp)
    orphan_cycle.transitions.connect(orphan_trans)

    fallback_string = orphan_cycle.as_str()
    assert "Orphan component" in fallback_string

    print(f"✓ Cycle string fallback to statement preview: {fallback_string}")


def test_cycle_is_same_structure():
    """Test is_same_structure() detects rotational equivalence."""

    # Create first cycle: T1 → T2 → T3 → T1
    t1a = DialecticalComponent(statement="Component 1")
    t2a = DialecticalComponent(statement="Component 2")
    t3a = DialecticalComponent(statement="Component 3")

    t1a.save()
    t2a.save()
    t3a.save()

    trans1a = Transition()
    trans2a = Transition()
    trans3a = Transition()

    trans1a.save()
    trans2a.save()
    trans3a.save()

    trans1a.source.connect(t1a)
    trans1a.target.connect(t2a)
    trans2a.source.connect(t2a)
    trans2a.target.connect(t3a)
    trans3a.source.connect(t3a)
    trans3a.target.connect(t1a)

    cycle1 = Cycle(causality_type=CausalityType.BALANCED)
    cycle1.save()

    cycle1.transitions.connect(trans1a)
    cycle1.transitions.connect(trans2a)
    cycle1.transitions.connect(trans3a)

    # Create second cycle with same components, different starting point: T2 → T3 → T1 → T2
    t1b = DialecticalComponent(statement="Component 1")
    t2b = DialecticalComponent(statement="Component 2")
    t3b = DialecticalComponent(statement="Component 3")

    t1b.save()
    t2b.save()
    t3b.save()

    trans1b = Transition()
    trans2b = Transition()
    trans3b = Transition()

    trans1b.save()
    trans2b.save()
    trans3b.save()

    trans1b.source.connect(t2b)
    trans1b.target.connect(t3b)
    trans2b.source.connect(t3b)
    trans2b.target.connect(t1b)
    trans3b.source.connect(t1b)
    trans3b.target.connect(t2b)

    cycle2 = Cycle(causality_type=CausalityType.BALANCED)
    cycle2.save()

    cycle2.transitions.connect(trans1b)
    cycle2.transitions.connect(trans2b)
    cycle2.transitions.connect(trans3b)

    # Test is_same_structure (should be True - rotational equivalence)
    assert cycle1.is_same_structure(cycle2), "Cycles should be structurally equivalent"

    # Create third cycle with different components: T1 → T2 → T4 → T1
    t4 = DialecticalComponent(statement="Component 4")
    t4.save()

    trans1c = Transition()
    trans2c = Transition()
    trans3c = Transition()

    trans1c.save()
    trans2c.save()
    trans3c.save()

    t1c = DialecticalComponent(statement="Component 1")
    t2c = DialecticalComponent(statement="Component 2")

    t1c.save()
    t2c.save()

    trans1c.source.connect(t1c)
    trans1c.target.connect(t2c)
    trans2c.source.connect(t2c)
    trans2c.target.connect(t4)
    trans3c.source.connect(t4)
    trans3c.target.connect(t1c)

    cycle3 = Cycle(causality_type=CausalityType.BALANCED)
    cycle3.save()

    cycle3.transitions.connect(trans1c)
    cycle3.transitions.connect(trans2c)
    cycle3.transitions.connect(trans3c)

    # Test is_same_structure (should be False - different components)
    assert not cycle1.is_same_structure(cycle3), "Cycles with different components should not be equivalent"

    print("✓ is_same_structure() correctly detects rotational equivalence")


def test_estimation_properties():
    """Test probability and relevance properties on AssessableEntity."""
    import math

    # Create a component
    comp = DialecticalComponent(statement="Test component")
    comp.save()

    # Test 1: No estimations - should return None
    assert comp.probability is None
    assert comp.relevance is None

    # Test 2: Single probability estimation
    prob_est = ProbabilityEstimation(value=0.75)
    prob_est.save()
    comp.estimations.connect(prob_est)

    assert comp.probability == 0.75
    assert comp.relevance is None  # Still no relevance

    # Test 3: Single relevance estimation
    rel_est = RelevanceEstimation(value=0.85)
    rel_est.save()
    comp.estimations.connect(rel_est)

    assert comp.probability == 0.75
    assert comp.relevance == 0.85

    # Test 4: Multiple estimations - should return geometric mean
    prob_est2 = ProbabilityEstimation(value=0.90)
    prob_est2.save()
    comp.estimations.connect(prob_est2)

    rel_est2 = RelevanceEstimation(value=0.95)
    rel_est2.save()
    comp.estimations.connect(rel_est2)

    # Geometric mean: GM(0.75, 0.90) = sqrt(0.75 * 0.90) ≈ 0.8216
    expected_prob = math.sqrt(0.75 * 0.90)
    assert abs(comp.probability - expected_prob) < 0.001

    # Geometric mean: GM(0.85, 0.95) = sqrt(0.85 * 0.95) ≈ 0.8986
    expected_rel = math.sqrt(0.85 * 0.95)
    assert abs(comp.relevance - expected_rel) < 0.001

    print(f"✓ Probability property works correctly (GM): {comp.probability:.4f}")
    print(f"✓ Relevance property works correctly (GM): {comp.relevance:.4f}")

    # Test 5: Zero estimation - should return 0 (veto semantics)
    comp2 = DialecticalComponent(statement="Test component 2")
    comp2.save()

    prob_est3 = ProbabilityEstimation(value=0.8)
    prob_est3.save()
    comp2.estimations.connect(prob_est3)

    prob_est4 = ProbabilityEstimation(value=0.0)  # Zero vetos
    prob_est4.save()
    comp2.estimations.connect(prob_est4)

    assert comp2.probability == 0.0  # Zero vetos all other values

    print(f"✓ Zero estimation veto works correctly: {comp2.probability}")


def test_best_rationale_property():
    """Test best_rationale property on AssessableEntity."""

    # Create a component
    comp = DialecticalComponent(statement="Test component")
    comp.save()

    # Test 1: No rationales - should return None
    assert comp.best_rationale is None

    # Test 2: Single rationale without score
    r1 = Rationale(text="First rationale")
    r1.save()
    comp.rationales.connect(r1)

    best = comp.best_rationale
    assert best is not None
    assert best.uid == r1.uid
    assert best.text == "First rationale"

    # Test 3: Multiple rationales with scores
    r2 = Rationale(text="Second rationale", score=0.7)
    r2.save()
    comp.rationales.connect(r2)

    r3 = Rationale(text="Third rationale", score=0.9)
    r3.save()
    comp.rationales.connect(r3)

    # Should return r3 (highest score)
    best = comp.best_rationale
    assert best.uid == r3.uid
    assert best.score == 0.9
    assert best.text == "Third rationale"

    # Test 4: Add even higher scored rationale
    r4 = Rationale(text="Fourth rationale", score=0.95)
    r4.save()
    comp.rationales.connect(r4)

    best = comp.best_rationale
    assert best.uid == r4.uid
    assert best.score == 0.95

    print(f"✓ best_rationale property works correctly: score={best.score}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
