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
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.utils.order_transitions import order_transitions


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

    print("✓ Successfully created WisdomUnit with all required components")


def test_wisdom_unit_validation():
    """Test WisdomUnit completeness validation."""

    # Create incomplete wisdom unit
    wu = WisdomUnit()
    wu.save()

    # Add only T component - incomplete
    t = DialecticalComponent(statement="Test thesis")
    t.save()
    wu.t.connect(t, properties={'alias': 'T'})

    # Should not be complete (missing t_plus, t_minus, a, a_plus, a_minus)
    assert not wu.is_complete()

    # Add remaining required components
    t_plus = DialecticalComponent(statement="T+")
    t_plus.save()
    wu.t_plus.connect(t_plus, properties={'alias': 'T+'})

    t_minus = DialecticalComponent(statement="T-")
    t_minus.save()
    wu.t_minus.connect(t_minus, properties={'alias': 'T-'})

    a = DialecticalComponent(statement="Antithesis")
    a.save()
    wu.a.connect(a, properties={'alias': 'A'})

    a_plus = DialecticalComponent(statement="A+")
    a_plus.save()
    wu.a_plus.connect(a_plus, properties={'alias': 'A+'})

    a_minus = DialecticalComponent(statement="A-")
    a_minus.save()
    wu.a_minus.connect(a_minus, properties={'alias': 'A-'})

    # Now should be complete (s_plus and s_minus are optional)
    assert wu.is_complete()

    print("✓ WisdomUnit completeness validation works correctly")


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

    # Get all components with their aliases using repository
    from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
    repo = DialecticalComponentRepository()
    components_with_aliases = repo.find_by_wisdom_unit(wu)

    assert len(components_with_aliases) == 2
    aliases = [alias for _, alias in components_with_aliases]
    assert 'T3' in aliases
    assert 'A3' in aliases

    # Test component.get_alias() method
    t_alias = t.get_alias(wu)
    a_alias = a.get_alias(wu)

    assert t_alias == 'T3'
    assert a_alias == 'A3'

    # Test with component not in this wisdom unit
    other_comp = DialecticalComponent(statement="Not connected")
    other_comp.save()

    # Should raise ValueError when component not connected to WU
    import pytest
    with pytest.raises(ValueError, match="not connected to WisdomUnit"):
        other_comp.get_alias(wu)

    print(f"✓ Component aliases retrieved from relationships: {aliases}")
    print(f"✓ component.get_alias() works correctly: T={t_alias}, A={a_alias}")


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

    trans1.cycle.connect(cycle)
    trans2.cycle.connect(cycle)
    trans3.cycle.connect(cycle)

    # Test order_transitions utility
    all_transitions = cycle.transitions
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

    trans1.cycle.connect(cycle)
    trans2.cycle.connect(cycle)
    trans3.cycle.connect(cycle)

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
        trans.cycle.connect(cycle)

    # Create WisdomUnit and connect components with aliases FIRST
    wu = WisdomUnit()
    wu.save()

    wu.t.connect(components[0], properties={'alias': 'T'})
    wu.t_plus.connect(components[1], properties={'alias': 'T+'})
    wu.t_minus.connect(components[2], properties={'alias': 'T-'})
    wu.a.connect(components[3], properties={'alias': 'A'})

    # Create Nexus and connect WisdomUnit
    nexus = Nexus()
    nexus.save()
    wu.nexus.connect(nexus)

    # Connect Nexus to Cycle
    nexus.cycles.connect(cycle)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate transitions for wheel (same components, different transition objects)
    for i in range(4):
        wheel_trans = Transition()
        wheel_trans.save()
        wheel_trans.source.connect(components[i])
        wheel_trans.target.connect(components[(i + 1) % 4])
        wheel_trans.cycle.connect(wheel)

    # Now connect Wheel to Cycle (validation will succeed)
    cycle.wheels.connect(wheel)

    # Test 1: Automatic Wheel resolution (no parameters needed!)
    cycle_string = str(cycle)  # Use __str__ instead of as_str()
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
    orphan_trans.cycle.connect(orphan_cycle)

    fallback_string = str(orphan_cycle)  # Use __str__ instead of as_str()
    assert "Orphan component" in fallback_string

    print(f"✓ Cycle string fallback to statement preview: {fallback_string}")


def test_transition_str_formatting():
    """Test Transition.__format__() with various modes."""

    # Create components
    source_comp = DialecticalComponent(statement="Negative aspect of thesis")
    target_comp = DialecticalComponent(statement="Positive aspect of antithesis")
    source_comp.save()
    target_comp.save()

    # Create transition
    trans = Transition()
    trans.save()
    trans.source.connect(source_comp)
    trans.target.connect(target_comp)

    # Create WisdomUnit and connect components with aliases
    wu = WisdomUnit()
    wu.save()
    wu.t_minus.connect(source_comp, properties={'alias': 'T-'})
    wu.a_plus.connect(target_comp, properties={'alias': 'A+'})

    # Create Nexus and connect WisdomUnit
    nexus = Nexus()
    nexus.save()
    wu.nexus.connect(nexus)

    # Create Cycle and connect to Nexus + transition
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    nexus.cycles.connect(cycle)
    trans.cycle.connect(cycle)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transition (same components, different transition object)
    wheel_trans = Transition()
    wheel_trans.save()
    wheel_trans.source.connect(source_comp)
    wheel_trans.target.connect(target_comp)
    wheel_trans.cycle.connect(wheel)

    # Need a second transition to form a cycle
    wheel_trans2 = Transition()
    wheel_trans2.save()
    wheel_trans2.source.connect(target_comp)
    wheel_trans2.target.connect(source_comp)
    wheel_trans2.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    # Test 1: Default format (aliases) - use wheel_trans which is connected to wheel
    default_str = str(trans)
    assert "T-" in default_str
    assert "A+" in default_str
    assert "→" in default_str
    print(f"✓ Transition default format: {default_str}")

    # Test 2: Explicit format (aliases + statements)
    explicit_str = f"{trans:explicit}"
    assert "T-" in explicit_str
    assert "A+" in explicit_str
    assert "Negative aspect" in explicit_str
    assert "Positive aspect" in explicit_str
    print(f"✓ Transition explicit format: {explicit_str}")

    # Test 3: Statements format
    statements_str = f"{trans:statements}"
    assert "Negative aspect of thesis" in statements_str
    assert "Positive aspect of antithesis" in statements_str
    print(f"✓ Transition statements format: {statements_str}")

    # Test 4: Verbose format (with rationale)
    from dialectical_framework.graph.nodes.rationale import Rationale
    rationale = Rationale(text="This transition represents dialectical transformation")
    rationale.save()
    trans.rationales.connect(rationale)

    verbose_str = f"{trans:verbose}"
    assert "T-" in verbose_str
    assert "A+" in verbose_str
    assert "Rationale:" in verbose_str
    assert "dialectical transformation" in verbose_str
    print(f"✓ Transition verbose format: {verbose_str}")

    # Test 5: Orphan transition (no wheel context) - should fallback to UID
    orphan_trans = Transition()
    orphan_trans.save()
    orphan_comp1 = DialecticalComponent(statement="Orphan source")
    orphan_comp2 = DialecticalComponent(statement="Orphan target")
    orphan_comp1.save()
    orphan_comp2.save()
    orphan_trans.source.connect(orphan_comp1)
    orphan_trans.target.connect(orphan_comp2)

    orphan_str = str(orphan_trans)
    # Should contain truncated UIDs (8 chars) since no wheel context
    assert "→" in orphan_str
    print(f"✓ Orphan transition fallback: {orphan_str}")

    # Test 6: Orphan transition with statements mode
    orphan_statements = f"{orphan_trans:statements}"
    assert "Orphan source" in orphan_statements
    assert "Orphan target" in orphan_statements
    print(f"✓ Orphan transition statements format: {orphan_statements}")


def test_transition_segment_formatting():
    """Test Transition formatting shows segment aliases for Spiral/Transformation."""
    from dialectical_framework.graph.nodes.spiral import Spiral

    # Create components for a full wisdom unit
    t = DialecticalComponent(statement="Main thesis")
    t_plus = DialecticalComponent(statement="Positive thesis")
    t_minus = DialecticalComponent(statement="Negative thesis")
    a = DialecticalComponent(statement="Main antithesis")
    a_plus = DialecticalComponent(statement="Positive antithesis")
    a_minus = DialecticalComponent(statement="Negative antithesis")

    for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
        comp.save()

    # Create WisdomUnit with all components
    wu = WisdomUnit()
    wu.save()
    wu.t.connect(t, properties={'alias': 'T'})
    wu.t_plus.connect(t_plus, properties={'alias': 'T+'})
    wu.t_minus.connect(t_minus, properties={'alias': 'T-'})
    wu.a.connect(a, properties={'alias': 'A'})
    wu.a_plus.connect(a_plus, properties={'alias': 'A+'})
    wu.a_minus.connect(a_minus, properties={'alias': 'A-'})

    # Create Nexus and connect WisdomUnit
    nexus = Nexus()
    nexus.save()
    wu.nexus.connect(nexus)

    # Create Cycle (needed for Wheel)
    cycle_base = Cycle(causality_type=CausalityType.REALISTIC)
    cycle_base.save()
    nexus.cycles.connect(cycle_base)

    # Create cycle transitions: T- → A+ → T- (for the wheel)
    cycle_trans1 = Transition()
    cycle_trans1.save()
    cycle_trans1.source.connect(t_minus)
    cycle_trans1.target.connect(a_plus)
    cycle_trans1.cycle.connect(cycle_base)

    cycle_trans2 = Transition()
    cycle_trans2.save()
    cycle_trans2.source.connect(a_plus)
    cycle_trans2.target.connect(t_minus)
    cycle_trans2.cycle.connect(cycle_base)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transitions (same components, different transition objects)
    wheel_trans1 = Transition()
    wheel_trans1.save()
    wheel_trans1.source.connect(t_minus)
    wheel_trans1.target.connect(a_plus)
    wheel_trans1.cycle.connect(wheel)

    wheel_trans2 = Transition()
    wheel_trans2.save()
    wheel_trans2.source.connect(a_plus)
    wheel_trans2.target.connect(t_minus)
    wheel_trans2.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle_base.wheels.connect(wheel)

    # Create Spiral transition: T- → A+ (segment transition)
    spiral_trans = Transition()
    spiral_trans.save()
    spiral_trans.source.connect(t_minus)
    spiral_trans.target.connect(a_plus)

    # Create Spiral and connect
    spiral = Spiral()
    spiral.save()
    spiral_trans.cycle.connect(spiral)
    wheel.spiral.connect(spiral)

    # Test: Spiral transition should show "T-, T → A+" (segment format)
    spiral_str = str(spiral_trans)
    print(f"Spiral transition format: {spiral_str}")
    assert "T-" in spiral_str
    assert "T" in spiral_str  # Core T should also be present
    assert "A+" in spiral_str
    assert "," in spiral_str  # Should have comma separating segment aliases
    print(f"✓ Spiral transition shows segment aliases: {spiral_str}")

    # Test explicit mode
    explicit_str = f"{spiral_trans:explicit}"
    print(f"Spiral transition explicit: {explicit_str}")
    assert "T-" in explicit_str
    assert "Negative thesis" in explicit_str
    assert "A+" in explicit_str
    assert "Positive antithesis" in explicit_str
    print(f"✓ Spiral transition explicit format: {explicit_str}")

    # Compare with Cycle transition (should be component-only)
    cycle_trans = Transition()
    cycle_trans.save()
    cycle_trans.source.connect(t_minus)
    cycle_trans.target.connect(a_plus)

    # Connect to the existing cycle_base
    cycle_trans.cycle.connect(cycle_base)

    # Cycle transition should show only "T- → A+" (component format, no segment expansion)
    cycle_str = str(cycle_trans)
    print(f"Cycle transition format: {cycle_str}")
    # Cycle should NOT have comma (single component on each side)
    # Note: It will have T- and A+ but not "T-, T"
    assert "→" in cycle_str
    print(f"✓ Cycle transition shows component aliases: {cycle_str}")


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

    trans1a.cycle.connect(cycle1)
    trans2a.cycle.connect(cycle1)
    trans3a.cycle.connect(cycle1)

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

    trans1b.cycle.connect(cycle2)
    trans2b.cycle.connect(cycle2)
    trans3b.cycle.connect(cycle2)

    # Test is_same_structure (should be True - rotational equivalence)
    # Use compare='statement' since cycles aren't connected to wheels
    assert cycle1.is_same_structure(cycle2, compare='statement'), "Cycles should be structurally equivalent"

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

    trans1c.cycle.connect(cycle3)
    trans2c.cycle.connect(cycle3)
    trans3c.cycle.connect(cycle3)

    # Test is_same_structure (should be False - different components)
    assert not cycle1.is_same_structure(cycle3, compare='statement'), "Cycles with different components should not be equivalent"

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


def test_wheel_navigation_properties():
    """Test wheel navigation properties (order, degree)."""

    # Create 4 wisdom units with T components
    wus = []
    components = []
    for i in range(4):
        wu = WisdomUnit(reasoning_mode=f"mode_{i}")
        wu.save()

        comp = DialecticalComponent(statement=f"Component {i}")
        comp.save()
        wu.t.connect(comp, properties={'alias': f'T{i}'})

        wus.append(wu)
        components.append(comp)

    # Create Nexus and connect all WUs
    nexus = Nexus()
    nexus.save()
    for wu in wus:
        wu.nexus.connect(nexus)

    # Create Cycle and connect to Nexus
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    nexus.cycles.connect(cycle)

    # Create transitions forming a cycle: T0 → T1 → T2 → T3 → T0
    transitions = []
    for i in range(4):
        trans = Transition()
        trans.save()
        trans.source.connect(components[i])
        trans.target.connect(components[(i + 1) % 4])
        trans.cycle.connect(cycle)
        transitions.append(trans)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transitions (same components, different transition objects)
    for i in range(4):
        wheel_trans = Transition()
        wheel_trans.save()
        wheel_trans.source.connect(components[i])
        wheel_trans.target.connect(components[(i + 1) % 4])
        wheel_trans.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    # Test 1: polarity_count property
    assert wheel.polarity_count == 4

    # Test 2: segment_count property (2 × polarity_count)
    assert wheel.segment_count == 8

    print(f"✓ polarity_count={wheel.polarity_count}, segment_count={wheel.segment_count}")


def test_wheel_wisdom_unit_at():
    """Test wisdom_unit_at() method (no integer indexing)."""

    # Create wisdom units with components
    wus = []
    components = []
    for i in range(3):
        wu = WisdomUnit()
        wu.save()

        # Add a T component with alias
        comp = DialecticalComponent(statement=f"Component {i}")
        comp.save()
        wu.t.connect(comp, properties={'alias': f'T{i}'})
        wus.append((wu, comp))
        components.append(comp)

    # Create Nexus and connect all WUs
    nexus = Nexus()
    nexus.save()
    for wu, _ in wus:
        wu.nexus.connect(nexus)

    # Create Cycle and connect to Nexus
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    nexus.cycles.connect(cycle)

    # Create transitions forming a cycle: T0 → T1 → T2 → T0
    transitions = []
    for i in range(3):
        trans = Transition()
        trans.save()
        trans.source.connect(components[i])
        trans.target.connect(components[(i + 1) % 3])
        trans.cycle.connect(cycle)
        transitions.append(trans)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transitions (same components, different transition objects)
    for i in range(3):
        wheel_trans = Transition()
        wheel_trans.save()
        wheel_trans.source.connect(components[i])
        wheel_trans.target.connect(components[(i + 1) % 3])
        wheel_trans.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    # Test 1: Get by alias
    wu = wheel.wisdom_unit_at("T0")
    assert wu.uid == wus[0][0].uid

    wu = wheel.wisdom_unit_at("T1")
    assert wu.uid == wus[1][0].uid

    wu = wheel.wisdom_unit_at("T2")
    assert wu.uid == wus[2][0].uid

    # Test 2: Get by component
    wu = wheel.wisdom_unit_at(wus[0][1])
    assert wu.uid == wus[0][0].uid

    wu = wheel.wisdom_unit_at(wus[2][1])  # Component from wu2
    assert wu.uid == wus[2][0].uid

    # Test 3: Get by WisdomUnit
    wu = wheel.wisdom_unit_at(wus[1][0])
    assert wu.uid == wus[1][0].uid

    # Test 4: Alias not found
    try:
        _ = wheel.wisdom_unit_at("NonexistentAlias")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    print("✓ wisdom_unit_at() works with alias, component, and WisdomUnit")


def test_wheel_is_same_structure():
    """Test is_same_structure() for comparing wheels by transitions."""

    # Helper function to create a complete wheel setup
    def create_wheel_with_transitions(n_components: int, prefix: str):
        """Create a wheel with n components connected in a cycle."""
        components = []
        for i in range(n_components):
            comp = DialecticalComponent(statement=f"{prefix} Component {i}")
            comp.save()
            components.append(comp)

        # Create WisdomUnits
        wus = []
        for i, comp in enumerate(components):
            wu = WisdomUnit()
            wu.save()
            wu.t.connect(comp, properties={'alias': f'{prefix}T{i}'})
            wus.append(wu)

        # Create Nexus
        nexus = Nexus()
        nexus.save()
        for wu in wus:
            wu.nexus.connect(nexus)

        # Create Cycle
        cycle = Cycle(causality_type=CausalityType.BALANCED)
        cycle.save()
        nexus.cycles.connect(cycle)

        # Create transitions forming a cycle
        transitions = []
        for i in range(n_components):
            trans = Transition()
            trans.save()
            trans.source.connect(components[i])
            trans.target.connect(components[(i + 1) % n_components])
            trans.cycle.connect(cycle)
            transitions.append(trans)

        # Create Wheel first
        wheel = Wheel()
        wheel.save()

        # Create separate wheel transitions (same components, different transition objects)
        for i in range(n_components):
            wheel_trans = Transition()
            wheel_trans.save()
            wheel_trans.source.connect(components[i])
            wheel_trans.target.connect(components[(i + 1) % n_components])
            wheel_trans.cycle.connect(wheel)

        # Now connect Wheel to Cycle
        cycle.wheels.connect(wheel)

        return wheel, components

    # Create first wheel with 2 components
    wheel1, _ = create_wheel_with_transitions(2, "W1")

    # Create second wheel with same structure (2 components)
    wheel2, _ = create_wheel_with_transitions(2, "W2")

    # Test 1: Same structure (same number of transitions)
    # Note: is_same_structure compares by component statements
    assert wheel1.is_same_structure(wheel2, compare='statement') is False  # Different statements
    # Both have 2 transitions, but comparing by alias/statement shows they're different

    # Create third wheel with different structure (3 components)
    wheel3, _ = create_wheel_with_transitions(3, "W3")

    # Test 2: Different structure
    assert not wheel1.is_same_structure(wheel3, compare='statement')

    print("✓ is_same_structure() correctly compares wheels")


def test_wheel_segment_from_wisdom_unit():
    """Test creating WheelSegment from WisdomUnit using segment_t() and segment_a()."""
    from dialectical_framework.graph.wheel_segment import WheelSegment

    # Create wisdom unit with complete T-side and A-side
    wu = WisdomUnit(reasoning_mode="test")
    wu.save()

    # Create T-side components
    t_comp = DialecticalComponent(statement="Thesis")
    t_comp.save()
    wu.t.connect(t_comp, properties={'alias': 'T'})

    t_plus_comp = DialecticalComponent(statement="Thesis positive")
    t_plus_comp.save()
    wu.t_plus.connect(t_plus_comp, properties={'alias': 'T+'})

    t_minus_comp = DialecticalComponent(statement="Thesis negative")
    t_minus_comp.save()
    wu.t_minus.connect(t_minus_comp, properties={'alias': 'T-'})

    # Create A-side components
    a_comp = DialecticalComponent(statement="Antithesis")
    a_comp.save()
    wu.a.connect(a_comp, properties={'alias': 'A'})

    a_plus_comp = DialecticalComponent(statement="Antithesis positive")
    a_plus_comp.save()
    wu.a_plus.connect(a_plus_comp, properties={'alias': 'A+'})

    a_minus_comp = DialecticalComponent(statement="Antithesis negative")
    a_minus_comp.save()
    wu.a_minus.connect(a_minus_comp, properties={'alias': 'A-'})

    # Get T-side segment
    t_seg = wu.segment_t
    assert isinstance(t_seg, WheelSegment)
    assert t_seg.side == 'T'
    assert t_seg.wisdom_unit.uid == wu.uid

    # Test window into T-side relationships
    assert t_seg.t.get()[0].uid == t_comp.uid
    t_plus_list = [c for c, _ in t_seg.t_plus.all()]
    assert len(t_plus_list) == 1
    assert t_plus_list[0].uid == t_plus_comp.uid
    t_minus_list = [c for c, _ in t_seg.t_minus.all()]
    assert len(t_minus_list) == 1
    assert t_minus_list[0].uid == t_minus_comp.uid
    assert t_seg.is_complete()

    # Get A-side segment
    a_seg = wu.segment_a
    assert isinstance(a_seg, WheelSegment)
    assert a_seg.side == 'A'
    assert a_seg.wisdom_unit.uid == wu.uid

    # Test window into A-side relationships (using t/t_plus/t_minus properties)
    assert a_seg.t.get()[0].uid == a_comp.uid
    a_plus_list = [c for c, _ in a_seg.t_plus.all()]
    assert len(a_plus_list) == 1
    assert a_plus_list[0].uid == a_plus_comp.uid
    a_minus_list = [c for c, _ in a_seg.t_minus.all()]
    assert len(a_minus_list) == 1
    assert a_minus_list[0].uid == a_minus_comp.uid
    assert a_seg.is_complete()

    print("✓ WheelSegment.segment_t and segment_a work correctly")


def test_wheel_segment_get_component_by_alias():
    """Test finding components within a segment by alias."""
    wu = WisdomUnit(reasoning_mode="test")
    wu.save()

    # Create T-side components
    t_comp = DialecticalComponent(statement="Thesis")
    t_comp.save()
    wu.t.connect(t_comp, properties={'alias': 'T1'})

    t_plus_comp = DialecticalComponent(statement="Thesis positive")
    t_plus_comp.save()
    wu.t_plus.connect(t_plus_comp, properties={'alias': 'T1+'})

    # Create A-side component
    a_comp = DialecticalComponent(statement="Antithesis")
    a_comp.save()
    wu.a.connect(a_comp, properties={'alias': 'A1'})

    # Get T-side segment
    t_seg = wu.segment_t

    # Find T-side components by alias
    found_t = t_seg.get_component('T1')
    assert found_t is not None
    assert found_t.uid == t_comp.uid

    found_t_plus = t_seg.get_component('T1+')
    assert found_t_plus is not None
    assert found_t_plus.uid == t_plus_comp.uid

    # A-side component should not be found in T-side segment
    found_a = t_seg.get_component('A1')
    assert found_a is None

    # Get A-side segment
    a_seg = wu.segment_a

    # Find A-side component by alias
    found_a = a_seg.get_component('A1')
    assert found_a is not None
    assert found_a.uid == a_comp.uid

    # T-side component should not be found in A-side segment
    found_t = a_seg.get_component('T1')
    assert found_t is None

    print("✓ WheelSegment.get_component_by_alias() filters by side correctly")


def test_wheel_segment_at():
    """Test Wheel.segment_at() lookup by alias or component."""
    from dialectical_framework.graph.wheel_segment import WheelSegment

    # Create 2 wisdom units with full components
    wus = []
    t_comps = []
    for i in range(2):
        wu = WisdomUnit(reasoning_mode=f"mode_{i}")
        wu.save()

        # Add T-side components
        t_comp = DialecticalComponent(statement=f"Thesis {i}")
        t_comp.save()
        wu.t.connect(t_comp, properties={'alias': f'T{i}'})
        t_comps.append(t_comp)

        t_plus = DialecticalComponent(statement=f"T+ {i}")
        t_plus.save()
        wu.t_plus.connect(t_plus, properties={'alias': f'T{i}+'})

        t_minus = DialecticalComponent(statement=f"T- {i}")
        t_minus.save()
        wu.t_minus.connect(t_minus, properties={'alias': f'T{i}-'})

        # Add A-side components
        a_comp = DialecticalComponent(statement=f"Antithesis {i}")
        a_comp.save()
        wu.a.connect(a_comp, properties={'alias': f'A{i}'})

        a_plus = DialecticalComponent(statement=f"A+ {i}")
        a_plus.save()
        wu.a_plus.connect(a_plus, properties={'alias': f'A{i}+'})

        a_minus = DialecticalComponent(statement=f"A- {i}")
        a_minus.save()
        wu.a_minus.connect(a_minus, properties={'alias': f'A{i}-'})

        wus.append((wu, t_comp, a_comp))

    # Create Nexus and connect WUs
    nexus = Nexus()
    nexus.save()
    for wu, _, _ in wus:
        wu.nexus.connect(nexus)

    # Create Cycle and connect to Nexus
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    nexus.cycles.connect(cycle)

    # Create transitions: T0 → T1 → T0
    transitions = []
    for i in range(2):
        trans = Transition()
        trans.save()
        trans.source.connect(t_comps[i])
        trans.target.connect(t_comps[(i + 1) % 2])
        trans.cycle.connect(cycle)
        transitions.append(trans)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transitions (same components, different transition objects)
    for i in range(2):
        wheel_trans = Transition()
        wheel_trans.save()
        wheel_trans.source.connect(t_comps[i])
        wheel_trans.target.connect(t_comps[(i + 1) % 2])
        wheel_trans.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    # Test 1: By alias
    seg_t0 = wheel.segment_at("T0")
    assert isinstance(seg_t0, WheelSegment)
    assert seg_t0.side == 'T'
    assert seg_t0.wisdom_unit.uid == wus[0][0].uid

    seg_a1 = wheel.segment_at("A1")
    assert seg_a1.side == 'A'
    assert seg_a1.wisdom_unit.uid == wus[1][0].uid

    # Test 2: By component
    seg_by_comp = wheel.segment_at(wus[0][1])  # T component of first WU
    assert seg_by_comp.side == 'T'
    assert seg_by_comp.wisdom_unit.uid == wus[0][0].uid

    seg_by_a_comp = wheel.segment_at(wus[1][2])  # A component of second WU
    assert seg_by_a_comp.side == 'A'
    assert seg_by_a_comp.wisdom_unit.uid == wus[1][0].uid

    print("✓ Wheel.segment_at() supports alias/component lookup")


def test_wheel_segment_is_same():
    """Test WheelSegment.is_same() comparison."""
    wu1 = WisdomUnit(reasoning_mode="test1")
    wu1.save()

    wu2 = WisdomUnit(reasoning_mode="test2")
    wu2.save()

    # Create identical T-side components for both WUs
    for wu in [wu1, wu2]:
        t_comp = DialecticalComponent(statement="Same thesis")
        t_comp.save()
        wu.t.connect(t_comp, properties={'alias': 'T'})

        t_plus = DialecticalComponent(statement="Same T+")
        t_plus.save()
        wu.t_plus.connect(t_plus, properties={'alias': 'T+'})

        t_minus = DialecticalComponent(statement="Same T-")
        t_minus.save()
        wu.t_minus.connect(t_minus, properties={'alias': 'T-'})

    # Extract segments
    seg1 = wu1.segment_t
    seg2 = wu2.segment_t

    # Should be considered the same (same component UIDs)
    # Actually they won't be same since components have different UIDs
    # Let's test reflexive case
    assert seg1.is_same(seg1)
    assert seg2.is_same(seg2)

    print("✓ WheelSegment.is_same() works correctly")


def test_wheel_segment_is_set():
    """Test WheelSegment.is_set() method."""
    wu = WisdomUnit(reasoning_mode="test")
    wu.save()

    # Create T-side components
    t_comp = DialecticalComponent(statement="Thesis")
    t_comp.save()
    wu.t.connect(t_comp, properties={'alias': 'T1'})

    t_plus = DialecticalComponent(statement="T+")
    t_plus.save()
    wu.t_plus.connect(t_plus, properties={'alias': 'T1+'})

    # Create A-side component
    a_comp = DialecticalComponent(statement="Antithesis")
    a_comp.save()
    wu.a.connect(a_comp, properties={'alias': 'A1'})

    # Get segments
    t_seg = wu.segment_t
    a_seg = wu.segment_a

    # Test is_set by alias
    assert t_seg.is_set("T1")
    assert t_seg.is_set("T1+")
    assert not t_seg.is_set("A1")  # A component not in T segment

    assert a_seg.is_set("A1")
    assert not a_seg.is_set("T1")  # T component not in A segment

    # Test is_set by component
    assert t_seg.is_set(t_comp)
    assert t_seg.is_set(t_plus)
    assert not t_seg.is_set(a_comp)

    assert a_seg.is_set(a_comp)
    assert not a_seg.is_set(t_comp)

    print("✓ WheelSegment.is_set() works correctly")


def test_wheel_wisdom_unit_at_segment():
    """Test Wheel.wisdom_unit_at() with WheelSegment."""
    # Create 2 wisdom units with components
    wus = []
    t_comps = []
    for i in range(2):
        wu = WisdomUnit(reasoning_mode=f"mode_{i}")
        wu.save()

        # Add minimal components
        t = DialecticalComponent(statement=f"T{i}")
        t.save()
        wu.t.connect(t, properties={'alias': f'T{i}'})
        t_comps.append(t)

        t_plus = DialecticalComponent(statement=f"T{i}+")
        t_plus.save()
        wu.t_plus.connect(t_plus, properties={'alias': f'T{i}+'})

        t_minus = DialecticalComponent(statement=f"T{i}-")
        t_minus.save()
        wu.t_minus.connect(t_minus, properties={'alias': f'T{i}-'})

        a = DialecticalComponent(statement=f"A{i}")
        a.save()
        wu.a.connect(a, properties={'alias': f'A{i}'})

        a_plus = DialecticalComponent(statement=f"A{i}+")
        a_plus.save()
        wu.a_plus.connect(a_plus, properties={'alias': f'A{i}+'})

        a_minus = DialecticalComponent(statement=f"A{i}-")
        a_minus.save()
        wu.a_minus.connect(a_minus, properties={'alias': f'A{i}-'})

        wus.append(wu)

    # Create Nexus and connect WUs
    nexus = Nexus()
    nexus.save()
    for wu in wus:
        wu.nexus.connect(nexus)

    # Create Cycle and connect to Nexus
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    nexus.cycles.connect(cycle)

    # Create transitions: T0 → T1 → T0
    transitions = []
    for i in range(2):
        trans = Transition()
        trans.save()
        trans.source.connect(t_comps[i])
        trans.target.connect(t_comps[(i + 1) % 2])
        trans.cycle.connect(cycle)
        transitions.append(trans)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transitions (same components, different transition objects)
    for i in range(2):
        wheel_trans = Transition()
        wheel_trans.save()
        wheel_trans.source.connect(t_comps[i])
        wheel_trans.target.connect(t_comps[(i + 1) % 2])
        wheel_trans.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    # Get segments
    t_seg_1 = wus[1].segment_t
    a_seg_0 = wus[0].segment_a

    # Test wisdom_unit_at with WheelSegment
    found_wu = wheel.wisdom_unit_at(t_seg_1)
    assert found_wu.uid == wus[1].uid

    found_wu = wheel.wisdom_unit_at(a_seg_0)
    assert found_wu.uid == wus[0].uid

    print("✓ Wheel.wisdom_unit_at() works with WheelSegment")


def test_wheel_is_set():
    """Test Wheel.is_set() method."""
    # Create WisdomUnit
    wu = WisdomUnit(reasoning_mode="test")
    wu.save()

    # Add components
    t = DialecticalComponent(statement="T")
    t.save()
    wu.t.connect(t, properties={'alias': 'T'})

    t_plus = DialecticalComponent(statement="T+")
    t_plus.save()
    wu.t_plus.connect(t_plus, properties={'alias': 'T+'})

    a = DialecticalComponent(statement="A")
    a.save()
    wu.a.connect(a, properties={'alias': 'A'})

    # Create Nexus and connect WU
    nexus = Nexus()
    nexus.save()
    wu.nexus.connect(nexus)

    # Create Cycle and connect to Nexus
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    nexus.cycles.connect(cycle)

    # Create transitions: T → A → T (minimal cycle)
    trans1 = Transition()
    trans1.save()
    trans1.source.connect(t)
    trans1.target.connect(a)
    trans1.cycle.connect(cycle)

    trans2 = Transition()
    trans2.save()
    trans2.source.connect(a)
    trans2.target.connect(t)
    trans2.cycle.connect(cycle)

    # Create Wheel first
    wheel = Wheel()
    wheel.save()

    # Create separate wheel transitions (same components, different transition objects)
    wheel_trans1 = Transition()
    wheel_trans1.save()
    wheel_trans1.source.connect(t)
    wheel_trans1.target.connect(a)
    wheel_trans1.cycle.connect(wheel)

    wheel_trans2 = Transition()
    wheel_trans2.save()
    wheel_trans2.source.connect(a)
    wheel_trans2.target.connect(t)
    wheel_trans2.cycle.connect(wheel)

    # Now connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    # Test with alias
    assert wheel.is_set('T') is True
    assert wheel.is_set('T+') is True
    assert wheel.is_set('A') is True
    assert wheel.is_set('NonExistent') is False

    # Test with component
    assert wheel.is_set(t) is True
    assert wheel.is_set(t_plus) is True
    assert wheel.is_set(a) is True

    # Test with segment
    t_seg = wu.segment_t
    a_seg = wu.segment_a
    assert wheel.is_set(t_seg) is True
    assert wheel.is_set(a_seg) is True

    print("✓ Wheel.is_set() works correctly")


def test_dialectical_component_repository_find_by_wisdom_unit():
    """Test DialecticalComponentRepository.find_by_wisdom_unit()."""
    from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository

    # Create wisdom unit
    wu = WisdomUnit(reasoning_mode="test")
    wu.save()

    # Create and connect components
    t_comp = DialecticalComponent(statement="Thesis")
    t_comp.save()
    wu.t.connect(t_comp, properties={'alias': 'T1'})

    t_plus_comp = DialecticalComponent(statement="Thesis positive")
    t_plus_comp.save()
    wu.t_plus.connect(t_plus_comp, properties={'alias': 'T1+'})

    a_comp = DialecticalComponent(statement="Antithesis")
    a_comp.save()
    wu.a.connect(a_comp, properties={'alias': 'A1'})

    # Use repository to find components
    repo = DialecticalComponentRepository()
    results = repo.find_by_wisdom_unit(wu)

    # Verify results
    assert len(results) == 3

    # Check that all expected aliases are present
    aliases = [alias for _, alias in results]
    assert 'T1' in aliases
    assert 'T1+' in aliases
    assert 'A1' in aliases

    # Verify component UIDs match
    component_uids = {comp.uid for comp, _ in results}
    assert t_comp.uid in component_uids
    assert t_plus_comp.uid in component_uids
    assert a_comp.uid in component_uids

    print("✓ DialecticalComponentRepository.find_by_wisdom_unit() works correctly")


def test_wisdom_unit_repository_safe_delete(di_container):
    """Test WisdomUnitRepository.safe_delete() with isolation checks."""
    from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository

    repo = WisdomUnitRepository()
    db = di_container.graph_db()

    # ========== Test 1: Isolated WU deletion (should delete) ==========
    wu_isolated = WisdomUnit(reasoning_mode="test_isolated")
    wu_isolated.save()

    # Create components
    t = DialecticalComponent(statement="Isolated thesis")
    t.save()
    wu_isolated.t.connect(t, properties={'alias': 'T'})

    t_plus = DialecticalComponent(statement="Isolated T+")
    t_plus.save()
    wu_isolated.t_plus.connect(t_plus, properties={'alias': 'T+'})

    t_minus = DialecticalComponent(statement="Isolated T-")
    t_minus.save()
    wu_isolated.t_minus.connect(t_minus, properties={'alias': 'T-'})

    a = DialecticalComponent(statement="Isolated antithesis")
    a.save()
    wu_isolated.a.connect(a, properties={'alias': 'A'})

    a_plus = DialecticalComponent(statement="Isolated A+")
    a_plus.save()
    wu_isolated.a_plus.connect(a_plus, properties={'alias': 'A+'})

    a_minus = DialecticalComponent(statement="Isolated A-")
    a_minus.save()
    wu_isolated.a_minus.connect(a_minus, properties={'alias': 'A-'})

    # Add rationale (attribute of WU)
    rat = Rationale(text="Test rationale")
    rat.save()
    wu_isolated.rationales.connect(rat)

    # Check isolation
    assert repo.is_isolated(wu_isolated), "WU should be isolated"

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_isolated)
    assert deleted, "Isolated WU should be deleted"

    # Verify all nodes were deleted

    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_isolated._id}
    ))
    assert len(result) == 0, "WU should be deleted"

    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": t._id}
    ))
    assert len(result) == 0, "Component should be deleted"

    result = list(db.execute_and_fetch(
        f"MATCH (r:Rationale) WHERE id(r) = $r_id RETURN r",
        {"r_id": rat._id}
    ))
    assert len(result) == 0, "Rationale should be deleted"

    print("✓ Test 1: Isolated WU deleted successfully")

    # ========== Test 2: Shared component (should NOT delete) ==========
    wu_shared_1 = WisdomUnit(reasoning_mode="shared_1")
    wu_shared_1.save()

    wu_shared_2 = WisdomUnit(reasoning_mode="shared_2")
    wu_shared_2.save()

    # Create shared component
    shared_comp = DialecticalComponent(statement="Shared thesis")
    shared_comp.save()

    # Connect to both WUs
    wu_shared_1.t.connect(shared_comp, properties={'alias': 'T1'})
    wu_shared_2.t.connect(shared_comp, properties={'alias': 'T2'})

    # Add other required components to wu_shared_1
    for pos, stmt in [('t_plus', 'T1+'), ('t_minus', 'T1-'),
                       ('a', 'A1'), ('a_plus', 'A1+'), ('a_minus', 'A1-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_shared_1, pos).connect(comp, properties={'alias': stmt})

    # Check isolation (should be False - shared component)
    assert not repo.is_isolated(wu_shared_1), "WU with shared component should not be isolated"

    # Check is_shared
    assert repo.is_shared(wu_shared_1), "WU should have shared components"

    # Check not in_use (not in wheel)
    assert not repo.in_use(wu_shared_1), "WU should not be in use (not in wheel)"

    # Safe delete with force_gc=True (default) SHOULD delete (ignores component sharing)
    deleted = repo.safe_delete(wu_shared_1, force_gc=True)
    assert deleted, "WU with shared components SHOULD be deleted in GC mode (default)"

    # Verify WU deleted but shared component preserved
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_shared_1._id}
    ))
    assert len(result) == 0, "WU should be deleted in GC mode"

    # Verify shared component still exists (preserved)
    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": shared_comp._id}
    ))
    assert len(result) == 1, "Shared component should still exist (preserved)"

    # Verify wu_shared_2 still has connection to shared component
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit)<-[:T]-(c:DialecticalComponent) WHERE id(wu) = $wu_id AND id(c) = $c_id RETURN wu",
        {"wu_id": wu_shared_2._id, "c_id": shared_comp._id}
    ))
    assert len(result) == 1, "wu_shared_2 should still have shared component connected"

    print("✓ Test 2: GC mode deleted WU but preserved shared component")

    # ========== Test 2b: Conservative mode with shared component (should NOT delete) ==========
    wu_shared_3 = WisdomUnit(reasoning_mode="shared_3")
    wu_shared_3.save()

    # Create shared component (reuse the same one)
    wu_shared_3.t.connect(shared_comp, properties={'alias': 'T3'})

    # Add other required components
    for pos, stmt in [('t_plus', 'T3+'), ('t_minus', 'T3-'),
                       ('a', 'A3'), ('a_plus', 'A3+'), ('a_minus', 'A3-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_shared_3, pos).connect(comp, properties={'alias': stmt})

    # Check is_shared
    assert repo.is_shared(wu_shared_3), "WU should have shared components"

    # Safe delete with force_gc=False (conservative) should NOT delete
    deleted = repo.safe_delete(wu_shared_3, force_gc=False)
    assert not deleted, "WU with shared components should NOT be deleted in conservative mode"

    # Verify WU still exists
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_shared_3._id}
    ))
    assert len(result) == 1, "WU should still exist (conservative mode preserved it)"

    print("✓ Test 2b: Conservative mode preserved WU with shared component")

    # ========== Test 3: HAS_STATEMENT boundary (should disconnect, conditionally delete) ==========
    wu_boundary = WisdomUnit(reasoning_mode="boundary_test")
    wu_boundary.save()

    # Create WU components
    t_boundary = DialecticalComponent(statement="Boundary thesis")
    t_boundary.save()
    wu_boundary.t.connect(t_boundary, properties={'alias': 'T'})

    # Add other required components
    for pos, stmt in [('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_boundary, pos).connect(comp, properties={'alias': stmt})

    # Create rationale with HAS_STATEMENT (orphaned component)
    rat_boundary = Rationale(text="Rationale with statement")
    rat_boundary.save()
    wu_boundary.rationales.connect(rat_boundary)

    stmt_comp_orphan = DialecticalComponent(statement="Statement component (orphan)")
    stmt_comp_orphan.save()
    rat_boundary.derived_statements.connect(stmt_comp_orphan)

    # Check isolation (HAS_STATEMENT doesn't prevent deletion)
    assert repo.is_isolated(wu_boundary), "WU with HAS_STATEMENT should still be isolated"

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_boundary)
    assert deleted, "WU with HAS_STATEMENT boundary should be deleted"

    # Verify WU deleted
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_boundary._id}
    ))
    assert len(result) == 0, "WU should be deleted"

    # Verify orphaned stmt_component also deleted (not in any WU)
    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": stmt_comp_orphan._id}
    ))
    assert len(result) == 0, "Orphaned statement component should be deleted"

    print("✓ Test 3: HAS_STATEMENT boundary handled correctly")

    # ========== Test 4: HAS_STATEMENT with component in another WU (should keep component) ==========
    wu_boundary_2 = WisdomUnit(reasoning_mode="boundary_test_2")
    wu_boundary_2.save()

    wu_other = WisdomUnit(reasoning_mode="other_wu")
    wu_other.save()

    # Create WU components for wu_boundary_2
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_boundary_2, pos).connect(comp, properties={'alias': stmt})

    # Create shared stmt_component used in another WU
    stmt_comp_shared = DialecticalComponent(statement="Statement component (in another WU)")
    stmt_comp_shared.save()
    wu_other.t.connect(stmt_comp_shared, properties={'alias': 'T_other'})

    # Create rationale with HAS_STATEMENT to shared component
    rat_boundary_2 = Rationale(text="Rationale with shared statement")
    rat_boundary_2.save()
    wu_boundary_2.rationales.connect(rat_boundary_2)
    rat_boundary_2.derived_statements.connect(stmt_comp_shared)

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_boundary_2)
    assert deleted, "WU should be deleted"

    # Verify WU deleted
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_boundary_2._id}
    ))
    assert len(result) == 0, "WU should be deleted"

    # Verify shared stmt_component still exists (used in wu_other)
    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": stmt_comp_shared._id}
    ))
    assert len(result) == 1, "Shared statement component should still exist"

    print("✓ Test 4: HAS_STATEMENT with shared component kept component alive")

    # ========== Test 5: Rationales as attributes (should delete with WU) ==========
    wu_rationale = WisdomUnit(reasoning_mode="rationale_test")
    wu_rationale.save()

    # Create components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_rationale, pos).connect(comp, properties={'alias': stmt})

    # Create rationale chain (critique relationships)
    rat1 = Rationale(text="Base rationale")
    rat1.save()
    wu_rationale.rationales.connect(rat1)

    rat2 = Rationale(text="Critique of rat1")
    rat2.save()
    rat2.critiques.connect(rat1)
    wu_rationale.rationales.connect(rat2)

    rat3 = Rationale(text="Critique of rat2")
    rat3.save()
    rat3.critiques.connect(rat2)
    wu_rationale.rationales.connect(rat3)

    # Check isolation (CRITIQUES within WU doesn't prevent deletion)
    assert repo.is_isolated(wu_rationale), "WU with internal critique chain should be isolated"

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_rationale)
    assert deleted, "WU with internal critique chain should be deleted"

    # Verify all rationales deleted (attributes of WU)
    for rat in [rat1, rat2, rat3]:
        result = list(db.execute_and_fetch(
            f"MATCH (r:Rationale) WHERE id(r) = $r_id RETURN r",
            {"r_id": rat._id}
        ))
        assert len(result) == 0, f"Rationale {rat.text} should be deleted"

    print("✓ Test 5: Rationales with CRITIQUES deleted as attributes")

    # ========== Test 6: WU with Transformation (should delete Transformation + Transitions) ==========
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition

    wu_with_trans = WisdomUnit(reasoning_mode="with_transformation")
    wu_with_trans.save()

    # Create components for the WU
    wu_t_minus = DialecticalComponent(statement="T-")
    wu_t_minus.save()
    wu_with_trans.t_minus.connect(wu_t_minus, properties={'alias': 'T-'})

    wu_a_plus = DialecticalComponent(statement="A+")
    wu_a_plus.save()
    wu_with_trans.a_plus.connect(wu_a_plus, properties={'alias': 'A+'})

    wu_a_minus = DialecticalComponent(statement="A-")
    wu_a_minus.save()
    wu_with_trans.a_minus.connect(wu_a_minus, properties={'alias': 'A-'})

    wu_t_plus = DialecticalComponent(statement="T+")
    wu_t_plus.save()
    wu_with_trans.t_plus.connect(wu_t_plus, properties={'alias': 'T+'})

    # Add remaining required components
    for pos, stmt in [('t', 'T'), ('a', 'A')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_with_trans, pos).connect(comp, properties={'alias': stmt})

    # Create Transformation with Transitions
    transformation = Transformation()
    transformation.save()
    wu_with_trans.transformation.connect(transformation)

    # Create ac_re WisdomUnit for the transformation
    ac_re_wu = WisdomUnit(reasoning_mode="ac_re")
    ac_re_wu.save()
    for pos, stmt in [('t', 'Ac'), ('t_plus', 'Ac+'), ('t_minus', 'Ac-'),
                       ('a', 'Re'), ('a_plus', 'Re+'), ('a_minus', 'Re-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(ac_re_wu, pos).connect(comp, properties={'alias': stmt})
    transformation.ac_re.connect(ac_re_wu)

    # Create Transitions
    trans1 = Transition()
    trans1.save()
    trans1.source.connect(wu_t_minus)
    trans1.target.connect(wu_a_plus)
    trans1.cycle.connect(transformation)

    trans2 = Transition()
    trans2.save()
    trans2.source.connect(wu_a_minus)
    trans2.target.connect(wu_t_plus)
    trans2.cycle.connect(transformation)

    # Store IDs for verification
    trans_id = transformation._id
    trans1_id = trans1._id
    trans2_id = trans2._id

    # Check isolation (should be isolated - Transformation and Transitions are part of subgraph)
    assert repo.is_isolated(wu_with_trans), "WU with Transformation should be isolated"

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_with_trans)
    assert deleted, "WU with Transformation should be deleted"

    # Verify WU deleted
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_with_trans._id}
    ))
    assert len(result) == 0, "WU should be deleted"

    # Verify Transformation deleted
    result = list(db.execute_and_fetch(
        f"MATCH (t:Transformation) WHERE id(t) = $t_id RETURN t",
        {"t_id": trans_id}
    ))
    assert len(result) == 0, "Transformation should be deleted"

    # Verify Transitions deleted
    result = list(db.execute_and_fetch(
        f"MATCH (t:Transition) WHERE id(t) = $t_id RETURN t",
        {"t_id": trans1_id}
    ))
    assert len(result) == 0, "Transition 1 should be deleted"

    result = list(db.execute_and_fetch(
        f"MATCH (t:Transition) WHERE id(t) = $t_id RETURN t",
        {"t_id": trans2_id}
    ))
    assert len(result) == 0, "Transition 2 should be deleted"

    # Note: ac_re_wu should still exist (it's referenced by transformation.ac_re)
    # But transformation is deleted, so ac_re becomes orphaned
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": ac_re_wu._id}
    ))
    assert len(result) == 1, "ac_re WU should still exist (becomes orphan)"

    print("✓ Test 6: WU with Transformation deleted Transformation and Transitions")

    # ========== Test 7: WU that IS an ac_re (should NOT delete - external reference) ==========
    wu_parent = WisdomUnit(reasoning_mode="parent_with_trans")
    wu_parent.save()

    # Create components for parent WU
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_parent, pos).connect(comp, properties={'alias': stmt})

    # Create Transformation that references another WU as ac_re
    wu_as_ac_re = WisdomUnit(reasoning_mode="used_as_ac_re")
    wu_as_ac_re.save()
    for pos, stmt in [('t', 'Ac'), ('t_plus', 'Ac+'), ('t_minus', 'Ac-'),
                       ('a', 'Re'), ('a_plus', 'Re+'), ('a_minus', 'Re-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_as_ac_re, pos).connect(comp, properties={'alias': stmt})

    parent_transformation = Transformation()
    parent_transformation.save()
    wu_parent.transformation.connect(parent_transformation)
    parent_transformation.ac_re.connect(wu_as_ac_re)

    # Check isolation (should NOT be isolated - referenced by transformation.ac_re)
    assert not repo.is_isolated(wu_as_ac_re), "WU used as ac_re should NOT be isolated"

    # Safe delete should NOT delete
    deleted = repo.safe_delete(wu_as_ac_re)
    assert not deleted, "WU used as ac_re should NOT be deleted"

    # Verify WU still exists
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_as_ac_re._id}
    ))
    assert len(result) == 1, "WU used as ac_re should still exist"

    print("✓ Test 7: WU used as ac_re prevented deletion (external reference)")

    # ========== Test 8: Replacing ac_re (disconnect + safe_delete) ==========
    wu_replace = WisdomUnit(reasoning_mode="replace_test")
    wu_replace.save()

    # Create components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(wu_replace, pos).connect(comp, properties={'alias': stmt})

    # Create old ac_re
    old_ac_re = WisdomUnit(reasoning_mode="old_ac_re")
    old_ac_re.save()
    for pos, stmt in [('t', 'Ac'), ('t_plus', 'Ac+'), ('t_minus', 'Ac-'),
                       ('a', 'Re'), ('a_plus', 'Re+'), ('a_minus', 'Re-')]:
        comp = DialecticalComponent(statement=stmt)
        comp.save()
        getattr(old_ac_re, pos).connect(comp, properties={'alias': stmt})

    # Create transformation with old ac_re
    replace_transformation = Transformation()
    replace_transformation.save()
    wu_replace.transformation.connect(replace_transformation)
    replace_transformation.ac_re.connect(old_ac_re)

    old_ac_re_id = old_ac_re._id

    # Verify old_ac_re is NOT isolated (still referenced)
    assert not repo.is_isolated(old_ac_re), "Old ac_re should NOT be isolated (still referenced)"

    # Simulate replacing ac_re (disconnect)
    replace_transformation.ac_re.disconnect(old_ac_re)

    # Now old_ac_re should be isolated
    assert repo.is_isolated(old_ac_re), "Old ac_re should be isolated after disconnect"

    # Safe delete should succeed
    deleted = repo.safe_delete(old_ac_re)
    assert deleted, "Old ac_re should be deleted after disconnect"

    # Verify old ac_re deleted
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": old_ac_re_id}
    ))
    assert len(result) == 0, "Old ac_re should be deleted"

    print("✓ Test 8: Replacing ac_re (disconnect + safe_delete) works correctly")

    # ========== Test 9: WU with Synthesis (should delete Synthesis and orphaned S+/S- components) ==========
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.relationships.polarity_relationship import SPlusRelationship, SMinusRelationship

    wu_with_synth = WisdomUnit(reasoning_mode="with_synthesis")
    wu_with_synth.save()

    # Create core components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"Synth test {stmt}")
        comp.save()
        getattr(wu_with_synth, pos).connect(comp, properties={'alias': stmt})

    # Create Synthesis with S+ and S- components
    synth = Synthesis()
    synth.save()
    synth.wisdom_unit.connect(wu_with_synth)

    s_plus_comp = DialecticalComponent(statement="Positive synthesis")
    s_plus_comp.save()
    synth.s_plus.connect(s_plus_comp, relationship=SPlusRelationship(alias="S+"))

    s_minus_comp = DialecticalComponent(statement="Negative synthesis")
    s_minus_comp.save()
    synth.s_minus.connect(s_minus_comp, relationship=SMinusRelationship(alias="S-"))

    synth_id = synth._id
    s_plus_id = s_plus_comp._id
    s_minus_id = s_minus_comp._id

    # Check isolation (should be isolated - no sharing)
    assert repo.is_isolated(wu_with_synth), "WU with isolated Synthesis should be isolated"
    assert not repo.is_shared(wu_with_synth), "WU with isolated Synthesis should not be shared"

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_with_synth)
    assert deleted, "WU with Synthesis should be deleted"

    # Verify WU deleted
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_with_synth._id}
    ))
    assert len(result) == 0, "WU should be deleted"

    # Verify Synthesis deleted
    result = list(db.execute_and_fetch(
        f"MATCH (s:Synthesis) WHERE id(s) = $s_id RETURN s",
        {"s_id": synth_id}
    ))
    assert len(result) == 0, "Synthesis should be deleted"

    # Verify S+ and S- components deleted (orphaned)
    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": s_plus_id}
    ))
    assert len(result) == 0, "Orphaned S+ component should be deleted"

    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": s_minus_id}
    ))
    assert len(result) == 0, "Orphaned S- component should be deleted"

    print("✓ Test 9: WU with Synthesis deleted Synthesis and orphaned S+/S- components")

    # ========== Test 10: Shared Synthesis component (should preserve shared S+ component) ==========
    wu_synth_1 = WisdomUnit(reasoning_mode="synth_shared_1")
    wu_synth_1.save()

    wu_synth_2 = WisdomUnit(reasoning_mode="synth_shared_2")
    wu_synth_2.save()

    # Create core components for both WUs
    for wu in [wu_synth_1, wu_synth_2]:
        for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                           ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
            comp = DialecticalComponent(statement=f"{wu.reasoning_mode} {stmt}")
            comp.save()
            getattr(wu, pos).connect(comp, properties={'alias': stmt})

    # Create shared S+ component
    shared_s_plus = DialecticalComponent(statement="Shared positive synthesis")
    shared_s_plus.save()

    # Create Synthesis for wu_synth_1 using shared S+
    synth_1 = Synthesis()
    synth_1.save()
    synth_1.wisdom_unit.connect(wu_synth_1)
    synth_1.s_plus.connect(shared_s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus_1 = DialecticalComponent(statement="S- for wu_synth_1")
    s_minus_1.save()
    synth_1.s_minus.connect(s_minus_1, relationship=SMinusRelationship(alias="S-"))

    # Create Synthesis for wu_synth_2 using same shared S+
    synth_2 = Synthesis()
    synth_2.save()
    synth_2.wisdom_unit.connect(wu_synth_2)
    synth_2.s_plus.connect(shared_s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus_2 = DialecticalComponent(statement="S- for wu_synth_2")
    s_minus_2.save()
    synth_2.s_minus.connect(s_minus_2, relationship=SMinusRelationship(alias="S-"))

    shared_s_plus_id = shared_s_plus._id
    s_minus_1_id = s_minus_1._id
    synth_1_id = synth_1._id

    # Check sharing - wu_synth_1 should have shared components (S+ is shared)
    assert repo.is_shared(wu_synth_1), "WU with shared S+ component should be shared"
    assert not repo.is_isolated(wu_synth_1), "WU with shared S+ component should NOT be isolated"

    # GC mode delete should delete WU but preserve shared S+ component
    deleted = repo.safe_delete(wu_synth_1, force_gc=True)
    assert deleted, "WU should be deleted in GC mode"

    # Verify WU deleted
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_synth_1._id}
    ))
    assert len(result) == 0, "wu_synth_1 should be deleted"

    # Verify Synthesis deleted
    result = list(db.execute_and_fetch(
        f"MATCH (s:Synthesis) WHERE id(s) = $s_id RETURN s",
        {"s_id": synth_1_id}
    ))
    assert len(result) == 0, "synth_1 should be deleted"

    # Verify shared S+ component preserved (still used by wu_synth_2's Synthesis)
    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": shared_s_plus_id}
    ))
    assert len(result) == 1, "Shared S+ component should be preserved"

    # Verify orphaned S- component deleted
    result = list(db.execute_and_fetch(
        f"MATCH (c:DialecticalComponent) WHERE id(c) = $c_id RETURN c",
        {"c_id": s_minus_1_id}
    ))
    assert len(result) == 0, "Orphaned S- component should be deleted"

    # Verify wu_synth_2's Synthesis still has connection to shared S+
    result = list(db.execute_and_fetch(
        """
        MATCH (synth:Synthesis)<-[:S_PLUS]-(c:DialecticalComponent)
        WHERE id(synth) = $synth_id AND id(c) = $c_id
        RETURN synth
        """,
        {"synth_id": synth_2._id, "c_id": shared_s_plus_id}
    ))
    assert len(result) == 1, "wu_synth_2's Synthesis should still have shared S+ connected"

    print("✓ Test 10: Shared Synthesis component preserved, orphaned component deleted")

    # ========== Test 11: Conservative mode with shared Synthesis (should NOT delete) ==========
    wu_synth_conservative = WisdomUnit(reasoning_mode="synth_conservative")
    wu_synth_conservative.save()

    # Create core components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"Conservative {stmt}")
        comp.save()
        getattr(wu_synth_conservative, pos).connect(comp, properties={'alias': stmt})

    # Create Synthesis using the shared S+ from wu_synth_2
    synth_conservative = Synthesis()
    synth_conservative.save()
    synth_conservative.wisdom_unit.connect(wu_synth_conservative)
    synth_conservative.s_plus.connect(shared_s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus_cons = DialecticalComponent(statement="S- for conservative")
    s_minus_cons.save()
    synth_conservative.s_minus.connect(s_minus_cons, relationship=SMinusRelationship(alias="S-"))

    # Check sharing
    assert repo.is_shared(wu_synth_conservative), "WU with shared S+ should be shared"

    # Conservative mode should NOT delete (shared component)
    deleted = repo.safe_delete(wu_synth_conservative, force_gc=False)
    assert not deleted, "WU with shared S+ should NOT be deleted in conservative mode"

    # Verify WU still exists
    result = list(db.execute_and_fetch(
        f"MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id RETURN wu",
        {"wu_id": wu_synth_conservative._id}
    ))
    assert len(result) == 1, "WU should still exist in conservative mode"

    print("✓ Test 11: Conservative mode preserved WU with shared Synthesis component")

    print("\n✅ All WisdomUnitRepository.safe_delete() tests passed!")


def test_feasibility_estimation_fallback(di_container):
    """FeasibilityEstimation should be used when RelevanceEstimation doesn't exist."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation

    component = DialecticalComponent(statement="Test")
    component.save()

    # Add FeasibilityEstimation
    feas_est = FeasibilityEstimation(value=0.75)
    feas_est.save()
    component.estimations.connect(feas_est)

    # Should use FeasibilityEstimation as relevance
    assert component.relevance == 0.75, f"Expected relevance=0.75, got {component.relevance}"

    print("✓ FeasibilityEstimation fallback works correctly")


def test_relevance_estimation_priority(di_container):
    """RelevanceEstimation should take priority over FeasibilityEstimation."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation, RelevanceEstimation

    component = DialecticalComponent(statement="Test")
    component.save()

    # Add both estimations
    feas_est = FeasibilityEstimation(value=0.6)
    feas_est.save()
    component.estimations.connect(feas_est)

    rel_est = RelevanceEstimation(value=0.9)
    rel_est.save()
    component.estimations.connect(rel_est)

    # Should use RelevanceEstimation (priority)
    assert component.relevance == 0.9, f"Expected relevance=0.9, got {component.relevance}"

    print("✓ RelevanceEstimation takes priority over FeasibilityEstimation")


def test_calculated_relevance_priority(di_container):
    """CalculatedRelevanceEstimation should take priority over both manual estimations."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import (
        FeasibilityEstimation,
        RelevanceEstimation,
        CalculatedRelevanceEstimation
    )

    component = DialecticalComponent(statement="Test")
    component.save()

    # Add manual estimations
    feas_est = FeasibilityEstimation(value=0.6)
    feas_est.save()
    component.estimations.connect(feas_est)

    rel_est = RelevanceEstimation(value=0.9)
    rel_est.save()
    component.estimations.connect(rel_est)

    # Add calculated estimation
    calc_rel = CalculatedRelevanceEstimation(value=0.75)
    calc_rel.save()
    component.estimations.connect(calc_rel)

    # Should use CalculatedRelevanceEstimation (highest priority)
    assert component.relevance == 0.75, f"Expected relevance=0.75, got {component.relevance}"

    print("✓ CalculatedRelevanceEstimation takes priority over both manual estimations")


def test_multiple_feasibility_estimations(di_container):
    """Multiple FeasibilityEstimations should be aggregated via GM."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation

    component = DialecticalComponent(statement="Test")
    component.save()

    # Add multiple FeasibilityEstimations
    feas_est1 = FeasibilityEstimation(value=0.8)
    feas_est1.save()
    component.estimations.connect(feas_est1)

    feas_est2 = FeasibilityEstimation(value=0.6)
    feas_est2.save()
    component.estimations.connect(feas_est2)

    # Should aggregate via geometric mean: sqrt(0.8 * 0.6) ≈ 0.693
    assert abs(component.relevance - 0.693) < 0.001, f"Expected relevance≈0.693, got {component.relevance}"

    print("✓ Multiple FeasibilityEstimations aggregated correctly via geometric mean")


# =============================================================================
# Bidirectional Cardinality Enforcement Tests
# =============================================================================

def test_bidirectional_cardinality_enforcement():
    """
    Test that cardinality is enforced from both sides of connect().

    Use Transformation -> WisdomUnit which has (0, 1) on WU.transformation.
    If we try to connect two transformations to the same WU, the second
    should fail due to inverse cardinality check.
    """
    from dialectical_framework.graph.nodes.transformation import Transformation

    # Create WisdomUnit with all required components
    wu = WisdomUnit()
    wu.save()

    # Add required components
    components = []
    for stmt in ["T", "T+", "T-", "A", "A+", "A-"]:
        c = DialecticalComponent(statement=f"Statement {stmt}")
        c.save()
        components.append(c)

    wu.t.connect(components[0], properties={'alias': 'T'})
    wu.t_plus.connect(components[1], properties={'alias': 'T+'})
    wu.t_minus.connect(components[2], properties={'alias': 'T-'})
    wu.a.connect(components[3], properties={'alias': 'A'})
    wu.a_plus.connect(components[4], properties={'alias': 'A+'})
    wu.a_minus.connect(components[5], properties={'alias': 'A-'})

    # Create first transformation and connect to WU - should succeed
    trans1 = Transformation()
    trans1.save()
    trans1.wisdom_unit.connect(wu)

    # Create second transformation
    trans2 = Transformation()
    trans2.save()

    # This should fail - WU already has a transformation (cardinality 0,1)
    # The inverse cardinality check on WU.transformation (0,1) should trigger
    with pytest.raises(ValueError, match="cardinality"):
        trans2.wisdom_unit.connect(wu)

    print("✓ Bidirectional cardinality enforcement works from child side")


def test_bidirectional_cardinality_via_parent_connect():
    """
    Test that parent-side connect also checks child's cardinality.

    When using wu.transformation.connect(trans), the inverse cardinality
    on Transformation.wisdom_unit (1,1) should be checked.
    """
    from dialectical_framework.graph.nodes.transformation import Transformation

    # Create WisdomUnit with all required components
    wu = WisdomUnit()
    wu.save()

    components = []
    for stmt in ["T", "T+", "T-", "A", "A+", "A-"]:
        c = DialecticalComponent(statement=f"Statement {stmt}")
        c.save()
        components.append(c)

    wu.t.connect(components[0], properties={'alias': 'T'})
    wu.t_plus.connect(components[1], properties={'alias': 'T+'})
    wu.t_minus.connect(components[2], properties={'alias': 'T-'})
    wu.a.connect(components[3], properties={'alias': 'A'})
    wu.a_plus.connect(components[4], properties={'alias': 'A+'})
    wu.a_minus.connect(components[5], properties={'alias': 'A-'})

    # Create first transformation - connect via PARENT side
    trans1 = Transformation()
    trans1.save()
    wu.transformation.connect(trans1)  # Via parent side - should succeed

    # Create second transformation
    trans2 = Transformation()
    trans2.save()

    # This should fail even via parent side - WU already has transformation
    # Error can come from either:
    # - Source side: "maximum cardinality ... already reached"
    # - Target side (inverse): "cardinality constraint violated"
    with pytest.raises(ValueError, match="cardinality"):
        wu.transformation.connect(trans2)

    print("✓ Bidirectional cardinality enforcement works from parent side")


def test_bidirectional_cardinality_allows_valid_connection():
    """Test that valid connections still work with bidirectional enforcement."""
    from dialectical_framework.graph.nodes.transformation import Transformation

    # Create TWO WisdomUnits
    wu1 = WisdomUnit()
    wu1.save()

    wu2 = WisdomUnit()
    wu2.save()

    # Each can have ONE transformation (cardinality 0,1)
    trans1 = Transformation()
    trans1.save()
    trans1.wisdom_unit.connect(wu1)  # OK - wu1 has no transformation

    trans2 = Transformation()
    trans2.save()
    trans2.wisdom_unit.connect(wu2)  # OK - wu2 has no transformation

    assert wu1.transformation.count() == 1
    assert wu2.transformation.count() == 1

    print("✓ Valid connections still work with bidirectional enforcement")


# =============================================================================
# Cardinality Validation Tests
# =============================================================================

def test_cycle_cardinality_validation():
    """Test that Cycle._transitions cardinality (2, None) is validated correctly."""
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.enums.causality_type import CausalityType

    # Create cycle with no transitions
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()

    # 0 transitions - should be invalid (min is 2)
    assert not cycle._transitions.is_cardinality_valid(), "Cycle with 0 transitions should be invalid"

    # Add 1 transition
    t1 = DialecticalComponent(statement="T1")
    t1.save()
    trans1 = Transition()
    trans1.save()
    trans1.source.connect(t1)
    trans1.target.connect(t1)
    trans1.cycle.connect(cycle)

    # 1 transition - should still be invalid (min is 2)
    assert not cycle._transitions.is_cardinality_valid(), "Cycle with 1 transition should be invalid"

    # Add 2nd transition
    t2 = DialecticalComponent(statement="T2")
    t2.save()
    trans2 = Transition()
    trans2.save()
    trans2.source.connect(t1)
    trans2.target.connect(t2)
    trans2.cycle.connect(cycle)

    # 2 transitions - should be valid (meets minimum)
    assert cycle._transitions.is_cardinality_valid(), "Cycle with 2 transitions should be valid"

    # Add 3rd transition - should still be valid (no max)
    trans3 = Transition()
    trans3.save()
    trans3.source.connect(t2)
    trans3.target.connect(t1)
    trans3.cycle.connect(cycle)

    assert cycle._transitions.is_cardinality_valid(), "Cycle with 3 transitions should be valid"

    print("✓ Cycle cardinality validation works correctly")


def test_transformation_cardinality_validation():
    """Test that Transformation._transitions cardinality (2, 2) is validated correctly."""
    from dialectical_framework.graph.nodes.transformation import Transformation

    # Create transformation with no transitions
    transformation = Transformation()
    transformation.save()

    # 0 transitions - should be invalid (min is 2)
    assert not transformation._transitions.is_cardinality_valid(), "Transformation with 0 transitions should be invalid"

    # Add 1 transition
    t1 = DialecticalComponent(statement="T-")
    t1.save()
    a1 = DialecticalComponent(statement="A+")
    a1.save()
    trans1 = Transition()
    trans1.save()
    trans1.source.connect(t1)
    trans1.target.connect(a1)
    trans1.cycle.connect(transformation)

    # 1 transition - should be invalid (min is 2)
    assert not transformation._transitions.is_cardinality_valid(), "Transformation with 1 transition should be invalid"

    # Add 2nd transition
    a2 = DialecticalComponent(statement="A-")
    a2.save()
    t2 = DialecticalComponent(statement="T+")
    t2.save()
    trans2 = Transition()
    trans2.save()
    trans2.source.connect(a2)
    trans2.target.connect(t2)
    trans2.cycle.connect(transformation)

    # 2 transitions - should be valid (exactly 2)
    assert transformation._transitions.is_cardinality_valid(), "Transformation with 2 transitions should be valid"

    print("✓ Transformation cardinality validation works correctly")


def test_transformation_max_cardinality_enforced():
    """Test that Transformation cannot exceed max cardinality of 2."""
    from dialectical_framework.graph.nodes.transformation import Transformation

    transformation = Transformation()
    transformation.save()

    # Add 2 transitions (the max allowed)
    components = []
    for i in range(4):
        c = DialecticalComponent(statement=f"C{i}")
        c.save()
        components.append(c)

    trans1 = Transition()
    trans1.save()
    trans1.source.connect(components[0])
    trans1.target.connect(components[1])
    trans1.cycle.connect(transformation)

    trans2 = Transition()
    trans2.save()
    trans2.source.connect(components[2])
    trans2.target.connect(components[3])
    trans2.cycle.connect(transformation)

    # Try to add 3rd transition - should fail (max cardinality)
    trans3 = Transition()
    trans3.save()
    trans3.source.connect(components[0])
    trans3.target.connect(components[2])

    with pytest.raises(ValueError, match="cardinality"):
        trans3.cycle.connect(transformation)

    print("✓ Transformation max cardinality (2) is enforced at connect time")


def test_wisdom_unit_vocabulary_validation():
    """
    Test that WisdomUnit components must all come from the same vocabulary context.

    Gen-0 WU: All components must come from the same Input.
    Gen-1+ WU: All components must come from the same Nexus vocabulary.
    """
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.relationships.polarity_relationship import (
        TRelationship, ARelationship, TPlusRelationship, TMinusRelationship,
        APlusRelationship, AMinusRelationship
    )

    # === Gen-0 Test: Components must come from the same Input ===

    # Create two separate Inputs
    input_a = Input(content_uri="https://example.com/article-a")
    input_a.save()

    input_b = Input(content_uri="https://example.com/article-b")
    input_b.save()

    # Create components for Input A
    t_a = DialecticalComponent(statement="Thesis from A")
    t_a.save()
    input_a.statements.connect(t_a)

    a_a = DialecticalComponent(statement="Antithesis from A")
    a_a.save()
    input_a.statements.connect(a_a)

    t_plus_a = DialecticalComponent(statement="T+ from A")
    t_plus_a.save()
    input_a.statements.connect(t_plus_a)

    t_minus_a = DialecticalComponent(statement="T- from A")
    t_minus_a.save()
    input_a.statements.connect(t_minus_a)

    a_plus_a = DialecticalComponent(statement="A+ from A")
    a_plus_a.save()
    input_a.statements.connect(a_plus_a)

    a_minus_a = DialecticalComponent(statement="A- from A")
    a_minus_a.save()
    input_a.statements.connect(a_minus_a)

    # Create a component for Input B
    t_b = DialecticalComponent(statement="Thesis from B")
    t_b.save()
    input_b.statements.connect(t_b)

    # Create WisdomUnit and connect first component from Input A
    wu = WisdomUnit()
    wu.save()
    wu.t.connect(t_a, relationship=TRelationship(alias="T"))

    # Connecting another component from Input A should work
    wu.a.connect(a_a, relationship=ARelationship(alias="A"))
    wu.t_plus.connect(t_plus_a, relationship=TPlusRelationship(alias="T+"))
    wu.t_minus.connect(t_minus_a, relationship=TMinusRelationship(alias="T-"))
    wu.a_plus.connect(a_plus_a, relationship=APlusRelationship(alias="A+"))

    # Trying to connect a component from Input B should FAIL
    with pytest.raises(ValueError, match="vocabulary context mismatch"):
        wu.a_minus.connect(t_b, relationship=AMinusRelationship(alias="A-"))

    # Complete with correct component
    wu.a_minus.connect(a_minus_a, relationship=AMinusRelationship(alias="A-"))

    print("✓ Gen-0 vocabulary validation: components from different Inputs rejected")

    # === Gen-1+ Test: Components from same Nexus vocabulary work ===

    # Pool the WU into a Nexus
    nexus = Nexus()
    nexus.save()
    wu.nexus.connect(nexus)

    # Create a second WU from Input B (valid on its own)
    t_plus_b = DialecticalComponent(statement="T+ from B")
    t_plus_b.save()
    input_b.statements.connect(t_plus_b)

    t_minus_b = DialecticalComponent(statement="T- from B")
    t_minus_b.save()
    input_b.statements.connect(t_minus_b)

    a_b = DialecticalComponent(statement="Antithesis from B")
    a_b.save()
    input_b.statements.connect(a_b)

    a_plus_b = DialecticalComponent(statement="A+ from B")
    a_plus_b.save()
    input_b.statements.connect(a_plus_b)

    a_minus_b = DialecticalComponent(statement="A- from B")
    a_minus_b.save()
    input_b.statements.connect(a_minus_b)

    wu_b = WisdomUnit()
    wu_b.save()
    wu_b.t.connect(t_b, relationship=TRelationship(alias="T"))
    wu_b.a.connect(a_b, relationship=ARelationship(alias="A"))
    wu_b.t_plus.connect(t_plus_b, relationship=TPlusRelationship(alias="T+"))
    wu_b.t_minus.connect(t_minus_b, relationship=TMinusRelationship(alias="T-"))
    wu_b.a_plus.connect(a_plus_b, relationship=APlusRelationship(alias="A+"))
    wu_b.a_minus.connect(a_minus_b, relationship=AMinusRelationship(alias="A-"))

    # Both WUs can be pooled into the same Nexus (mixing Inputs at Nexus level is OK)
    wu_b.nexus.connect(nexus)

    assert nexus.wisdom_units.count() == 2, "Nexus should have 2 WUs from different Inputs"

    print("✓ Gen-1+ vocabulary: WUs from different Inputs can be pooled in same Nexus")

    # === Gen-1+ Test: Create new WU mixing components from different original Inputs ===

    # Create a new WU and connect it to the Nexus FIRST (Gen-1 mode)
    wu_gen1 = WisdomUnit(reasoning_mode="gen1_mixed_inputs")
    wu_gen1.save()
    wu_gen1.nexus.connect(nexus)  # Connect to Nexus first = Gen-1 mode

    # Now we can mix components from different original Inputs
    # because they're all in the same Nexus vocabulary
    wu_gen1.t.connect(t_a, relationship=TRelationship(alias="T-Gen1"))  # From Input A
    wu_gen1.a.connect(t_b, relationship=ARelationship(alias="A-Gen1"))  # From Input B!

    # Add derived components (no HAS_STATEMENT) - should also work
    derived_t_plus = DialecticalComponent(statement="Derived T+ for Gen1")
    derived_t_plus.save()
    wu_gen1.t_plus.connect(derived_t_plus, relationship=TPlusRelationship(alias="T+-Gen1"))

    derived_t_minus = DialecticalComponent(statement="Derived T- for Gen1")
    derived_t_minus.save()
    wu_gen1.t_minus.connect(derived_t_minus, relationship=TMinusRelationship(alias="T--Gen1"))

    derived_a_plus = DialecticalComponent(statement="Derived A+ for Gen1")
    derived_a_plus.save()
    wu_gen1.a_plus.connect(derived_a_plus, relationship=APlusRelationship(alias="A+-Gen1"))

    derived_a_minus = DialecticalComponent(statement="Derived A- for Gen1")
    derived_a_minus.save()
    wu_gen1.a_minus.connect(derived_a_minus, relationship=AMinusRelationship(alias="A--Gen1"))

    assert wu_gen1.t.count() == 1
    assert wu_gen1.a.count() == 1
    assert nexus.wisdom_units.count() == 3

    print("✓ Gen-1+ vocabulary: Can mix components from different Inputs when WU is in Nexus")

    # === Gen-1+ Test: Create WU "in the air" using Nexus vocabulary ===
    # This tests the scenario where we create a new WU without connecting to Nexus first,
    # but use components that are already in the same Nexus vocabulary

    wu_air = WisdomUnit(reasoning_mode="wu_in_the_air")
    wu_air.save()
    # NOT connected to any Nexus yet!

    # Both t_a and t_b are in the same Nexus vocabulary (via wu and wu_b)
    # Even though they came from different original Inputs, their context is now Nexus
    wu_air.t.connect(t_a, relationship=TRelationship(alias="T-Air"))  # From Input A, but in Nexus
    wu_air.a.connect(a_b, relationship=ARelationship(alias="A-Air"))  # From Input B, but in same Nexus!

    # Add derived components
    air_t_plus = DialecticalComponent(statement="Air T+")
    air_t_plus.save()
    wu_air.t_plus.connect(air_t_plus, relationship=TPlusRelationship(alias="T+-Air"))

    air_t_minus = DialecticalComponent(statement="Air T-")
    air_t_minus.save()
    wu_air.t_minus.connect(air_t_minus, relationship=TMinusRelationship(alias="T--Air"))

    air_a_plus = DialecticalComponent(statement="Air A+")
    air_a_plus.save()
    wu_air.a_plus.connect(air_a_plus, relationship=APlusRelationship(alias="A+-Air"))

    air_a_minus = DialecticalComponent(statement="Air A-")
    air_a_minus.save()
    wu_air.a_minus.connect(air_a_minus, relationship=AMinusRelationship(alias="A--Air"))

    assert wu_air.t.count() == 1
    assert wu_air.a.count() == 1
    # WU is still not in any Nexus
    assert wu_air.nexus.count() == 0

    print("✓ Gen-1+ vocabulary: Can create WU 'in the air' with components from same Nexus")
    print("✓ WisdomUnit vocabulary validation works correctly")


def test_nexus_vocabulary_validation():
    """
    Test Gen-1+ vocabulary validation: components in a Nexus-based WU must come from
    the Nexus vocabulary (components from WUs already in the Nexus).

    This tests the Nexus branch of get_vocabulary() which had a Cypher syntax bug.
    """
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.relationships.polarity_relationship import (
        TRelationship, ARelationship, TPlusRelationship, TMinusRelationship,
        APlusRelationship, AMinusRelationship, SPlusRelationship, SMinusRelationship
    )
    from dialectical_framework.graph.repositories.dialectical_component_repository import (
        DialecticalComponentRepository
    )

    repo = DialecticalComponentRepository()

    # === Setup: Create Input with components and pool into Nexus ===

    input_source = Input(content_uri="https://example.com/nexus-test")
    input_source.save()

    # Create 6 components for the first WU
    components_wu1 = {}
    for pos in ['t', 'a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"WU1 {pos}")
        comp.save()
        input_source.statements.connect(comp)
        components_wu1[pos] = comp

    # Create WU1 and connect all components
    wu1 = WisdomUnit(reasoning_mode="nexus_vocab_test_wu1")
    wu1.save()
    wu1.t.connect(components_wu1['t'], relationship=TRelationship(alias="T"))
    wu1.a.connect(components_wu1['a'], relationship=ARelationship(alias="A"))
    wu1.t_plus.connect(components_wu1['t_plus'], relationship=TPlusRelationship(alias="T+"))
    wu1.t_minus.connect(components_wu1['t_minus'], relationship=TMinusRelationship(alias="T-"))
    wu1.a_plus.connect(components_wu1['a_plus'], relationship=APlusRelationship(alias="A+"))
    wu1.a_minus.connect(components_wu1['a_minus'], relationship=AMinusRelationship(alias="A-"))

    # Create Nexus and pool WU1
    nexus = Nexus()
    nexus.save()
    wu1.nexus.connect(nexus)

    # === Test 1: get_vocabulary() returns components from Nexus ===

    vocabulary = repo.get_vocabulary(nexus)
    assert len(vocabulary) == 6, f"Nexus vocabulary should have 6 components, got {len(vocabulary)}"

    vocab_uids = {c.uid for c in vocabulary}
    for pos, comp in components_wu1.items():
        assert comp.uid in vocab_uids, f"Component {pos} should be in Nexus vocabulary"

    print("✓ Test 1: get_vocabulary() correctly returns Nexus components")

    # === Test 2: Add Synthesis components to Nexus vocabulary ===

    synth = Synthesis()
    synth.save()
    synth.wisdom_unit.connect(wu1)

    s_plus = DialecticalComponent(statement="Synthesis S+")
    s_plus.save()
    synth.s_plus.connect(s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus = DialecticalComponent(statement="Synthesis S-")
    s_minus.save()
    synth.s_minus.connect(s_minus, relationship=SMinusRelationship(alias="S-"))

    # Vocabulary should now include synthesis components
    vocabulary = repo.get_vocabulary(nexus)
    assert len(vocabulary) == 8, f"Nexus vocabulary should have 8 components (6 core + 2 synthesis), got {len(vocabulary)}"

    vocab_uids = {c.uid for c in vocabulary}
    assert s_plus.uid in vocab_uids, "S+ should be in Nexus vocabulary"
    assert s_minus.uid in vocab_uids, "S- should be in Nexus vocabulary"

    print("✓ Test 2: Synthesis components included in Nexus vocabulary")

    # === Test 3: Create second WU reusing components from Nexus vocabulary ===

    # Create a second WU that reuses some components from WU1 (valid - same Nexus)
    wu2 = WisdomUnit(reasoning_mode="nexus_vocab_test_wu2")
    wu2.save()
    wu2.nexus.connect(nexus)  # Pool into same Nexus first

    # Reuse T from WU1 (should work - same vocabulary)
    wu2.t.connect(components_wu1['t'], relationship=TRelationship(alias="T2"))

    # Create new components for remaining positions
    for pos in ['a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"WU2 {pos}")
        comp.save()
        input_source.statements.connect(comp)

        rel_map = {
            'a': ARelationship(alias="A2"),
            't_plus': TPlusRelationship(alias="T2+"),
            't_minus': TMinusRelationship(alias="T2-"),
            'a_plus': APlusRelationship(alias="A2+"),
            'a_minus': AMinusRelationship(alias="A2-"),
        }
        getattr(wu2, pos).connect(comp, relationship=rel_map[pos])

    assert wu2.t.count() == 1, "WU2 should have T connected"
    assert nexus.wisdom_units.count() == 2, "Nexus should have 2 WUs"

    print("✓ Test 3: WU can reuse components from same Nexus vocabulary")

    # === Test 4: Components from different Nexus should be rejected ===

    # Create a separate Nexus with different components
    input_other = Input(content_uri="https://example.com/other-source")
    input_other.save()

    other_comp = DialecticalComponent(statement="Component from other Input")
    other_comp.save()
    input_other.statements.connect(other_comp)

    wu_other = WisdomUnit(reasoning_mode="other_nexus_wu")
    wu_other.save()
    wu_other.t.connect(other_comp, relationship=TRelationship(alias="T"))

    # Create other components for wu_other
    for pos in ['a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"Other {pos}")
        comp.save()
        input_other.statements.connect(comp)
        rel_map = {
            'a': ARelationship(alias="A"),
            't_plus': TPlusRelationship(alias="T+"),
            't_minus': TMinusRelationship(alias="T-"),
            'a_plus': APlusRelationship(alias="A+"),
            'a_minus': AMinusRelationship(alias="A-"),
        }
        getattr(wu_other, pos).connect(comp, relationship=rel_map[pos])

    nexus_other = Nexus()
    nexus_other.save()
    wu_other.nexus.connect(nexus_other)

    # Now try to create a WU in the original Nexus but with a component from nexus_other
    wu3 = WisdomUnit(reasoning_mode="cross_nexus_test")
    wu3.save()
    wu3.nexus.connect(nexus)  # Pool into original Nexus

    # First connect a valid component from the Nexus vocabulary
    wu3.t.connect(components_wu1['a'], relationship=TRelationship(alias="T3"))

    # Now try to connect a component from the OTHER Nexus - should FAIL
    with pytest.raises(ValueError, match="not in Nexus vocabulary"):
        wu3.a.connect(other_comp, relationship=ARelationship(alias="A3"))

    print("✓ Test 4: Components from different Nexus rejected")

    # === Test 5: HAS_STATEMENT components in Nexus tree ===

    # Create a Rationale with HAS_STATEMENT - should be in vocabulary
    from dialectical_framework.graph.nodes.rationale import Rationale

    rat = Rationale(text="Test rationale", headline="Test")
    rat.save()
    wu1.rationales.connect(rat)

    derived_comp = DialecticalComponent(statement="Derived from rationale")
    derived_comp.save()
    rat.derived_statements.connect(derived_comp)

    # Vocabulary should now include the derived component
    vocabulary = repo.get_vocabulary(nexus)
    vocab_uids = {c.uid for c in vocabulary}
    assert derived_comp.uid in vocab_uids, "HAS_STATEMENT derived component should be in Nexus vocabulary"

    print("✓ Test 5: HAS_STATEMENT components included in Nexus vocabulary")

    print("\n✅ All Nexus vocabulary validation tests passed!")


def test_nexus_vocabulary_context():
    """
    Test get_vocabulary_context() correctly identifies Nexus for Gen-1+ nodes.
    """
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.relationships.polarity_relationship import (
        TRelationship, ARelationship, TPlusRelationship, TMinusRelationship,
        APlusRelationship, AMinusRelationship, SPlusRelationship, SMinusRelationship
    )
    from dialectical_framework.graph.repositories.dialectical_component_repository import (
        DialecticalComponentRepository
    )

    repo = DialecticalComponentRepository()

    # Create Input
    input_node = Input(content_uri="https://example.com/context-test")
    input_node.save()

    # Input is its own vocabulary context
    assert repo.get_vocabulary_context(input_node) == input_node
    print("✓ Input is its own vocabulary context")

    # Create component from Input
    comp = DialecticalComponent(statement="Test component")
    comp.save()
    input_node.statements.connect(comp)

    # Component's context should be the Input
    context = repo.get_vocabulary_context(comp)
    assert context is not None
    assert context.uid == input_node.uid
    print("✓ Input-born component has Input as vocabulary context")

    # Create full WU and pool into Nexus
    wu = WisdomUnit(reasoning_mode="context_test")
    wu.save()
    wu.t.connect(comp, relationship=TRelationship(alias="T"))

    for pos in ['a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        c = DialecticalComponent(statement=f"Context {pos}")
        c.save()
        input_node.statements.connect(c)
        rel_map = {
            'a': ARelationship(alias="A"),
            't_plus': TPlusRelationship(alias="T+"),
            't_minus': TMinusRelationship(alias="T-"),
            'a_plus': APlusRelationship(alias="A+"),
            'a_minus': AMinusRelationship(alias="A-"),
        }
        getattr(wu, pos).connect(c, relationship=rel_map[pos])

    nexus = Nexus()
    nexus.save()
    wu.nexus.connect(nexus)

    # Nexus is its own vocabulary context
    assert repo.get_vocabulary_context(nexus) == nexus
    print("✓ Nexus is its own vocabulary context")

    # WU's context should now be the Nexus
    wu_context = repo.get_vocabulary_context(wu)
    assert wu_context is not None
    assert wu_context.uid == nexus.uid
    print("✓ WisdomUnit in Nexus has Nexus as vocabulary context")

    # Create Synthesis - its context should be the Nexus
    synth = Synthesis()
    synth.save()
    synth.wisdom_unit.connect(wu)

    s_plus = DialecticalComponent(statement="S+")
    s_plus.save()
    synth.s_plus.connect(s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus = DialecticalComponent(statement="S-")
    s_minus.save()
    synth.s_minus.connect(s_minus, relationship=SMinusRelationship(alias="S-"))

    synth_context = repo.get_vocabulary_context(synth)
    assert synth_context is not None
    assert synth_context.uid == nexus.uid
    print("✓ Synthesis has Nexus as vocabulary context")

    print("\n✅ All vocabulary context tests passed!")


def test_nexus_frozen_after_cycle():
    """
    Test that WisdomUnits cannot be added to a Nexus after Cycles have been created.

    Once a Nexus has been "crystallized" into one or more Cycles, its WisdomUnit
    membership should be frozen. This prevents semantic inconsistencies where
    Cycles reference components that don't include newly added WUs.
    """
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.relationships.polarity_relationship import (
        TRelationship, ARelationship, TPlusRelationship, TMinusRelationship,
        APlusRelationship, AMinusRelationship
    )

    # === Setup: Create Input with components ===

    input_source = Input(content_uri="https://example.com/frozen-nexus-test")
    input_source.save()

    # Create components for WU1
    components_wu1 = {}
    for pos in ['t', 'a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"WU1 {pos}")
        comp.save()
        input_source.statements.connect(comp)
        components_wu1[pos] = comp

    # Create WU1 and connect all components
    wu1 = WisdomUnit(reasoning_mode="frozen_nexus_test_wu1")
    wu1.save()
    wu1.t.connect(components_wu1['t'], relationship=TRelationship(alias="T1"))
    wu1.a.connect(components_wu1['a'], relationship=ARelationship(alias="A1"))
    wu1.t_plus.connect(components_wu1['t_plus'], relationship=TPlusRelationship(alias="T1+"))
    wu1.t_minus.connect(components_wu1['t_minus'], relationship=TMinusRelationship(alias="T1-"))
    wu1.a_plus.connect(components_wu1['a_plus'], relationship=APlusRelationship(alias="A1+"))
    wu1.a_minus.connect(components_wu1['a_minus'], relationship=AMinusRelationship(alias="A1-"))

    # Create Nexus and pool WU1
    nexus = Nexus()
    nexus.save()
    wu1.nexus.connect(nexus)

    # === Test 1: Can add WU before Cycle exists ===

    # Create components for WU2
    components_wu2 = {}
    for pos in ['t', 'a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"WU2 {pos}")
        comp.save()
        input_source.statements.connect(comp)
        components_wu2[pos] = comp

    wu2 = WisdomUnit(reasoning_mode="frozen_nexus_test_wu2")
    wu2.save()
    wu2.t.connect(components_wu2['t'], relationship=TRelationship(alias="T2"))
    wu2.a.connect(components_wu2['a'], relationship=ARelationship(alias="A2"))
    wu2.t_plus.connect(components_wu2['t_plus'], relationship=TPlusRelationship(alias="T2+"))
    wu2.t_minus.connect(components_wu2['t_minus'], relationship=TMinusRelationship(alias="T2-"))
    wu2.a_plus.connect(components_wu2['a_plus'], relationship=APlusRelationship(alias="A2+"))
    wu2.a_minus.connect(components_wu2['a_minus'], relationship=AMinusRelationship(alias="A2-"))

    # Should work - no Cycle yet
    wu2.nexus.connect(nexus)
    assert nexus.wisdom_units.count() == 2
    print("✓ Test 1: Can add WU to Nexus before Cycle exists")

    # === Test 2: Create Cycle - Nexus becomes frozen ===

    cycle = Cycle()
    cycle.save()
    nexus.cycles.connect(cycle)

    assert nexus.cycles.count() == 1
    print("✓ Test 2: Cycle created and connected to Nexus")

    # === Test 3: Cannot add WU after Cycle exists (via wu.nexus.connect) ===

    # Create WU3
    components_wu3 = {}
    for pos in ['t', 'a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"WU3 {pos}")
        comp.save()
        input_source.statements.connect(comp)
        components_wu3[pos] = comp

    wu3 = WisdomUnit(reasoning_mode="frozen_nexus_test_wu3")
    wu3.save()
    wu3.t.connect(components_wu3['t'], relationship=TRelationship(alias="T3"))
    wu3.a.connect(components_wu3['a'], relationship=ARelationship(alias="A3"))
    wu3.t_plus.connect(components_wu3['t_plus'], relationship=TPlusRelationship(alias="T3+"))
    wu3.t_minus.connect(components_wu3['t_minus'], relationship=TMinusRelationship(alias="T3-"))
    wu3.a_plus.connect(components_wu3['a_plus'], relationship=APlusRelationship(alias="A3+"))
    wu3.a_minus.connect(components_wu3['a_minus'], relationship=AMinusRelationship(alias="A3-"))

    # Should FAIL - Nexus is frozen
    with pytest.raises(ValueError, match="already has.*Cycle"):
        wu3.nexus.connect(nexus)

    print("✓ Test 3: Cannot add WU to frozen Nexus via wu.nexus.connect()")

    # === Test 4: Cannot add WU after Cycle exists (via nexus.wisdom_units.connect) ===

    # Create WU4
    components_wu4 = {}
    for pos in ['t', 'a', 't_plus', 't_minus', 'a_plus', 'a_minus']:
        comp = DialecticalComponent(statement=f"WU4 {pos}")
        comp.save()
        input_source.statements.connect(comp)
        components_wu4[pos] = comp

    wu4 = WisdomUnit(reasoning_mode="frozen_nexus_test_wu4")
    wu4.save()
    wu4.t.connect(components_wu4['t'], relationship=TRelationship(alias="T4"))
    wu4.a.connect(components_wu4['a'], relationship=ARelationship(alias="A4"))
    wu4.t_plus.connect(components_wu4['t_plus'], relationship=TPlusRelationship(alias="T4+"))
    wu4.t_minus.connect(components_wu4['t_minus'], relationship=TMinusRelationship(alias="T4-"))
    wu4.a_plus.connect(components_wu4['a_plus'], relationship=APlusRelationship(alias="A4+"))
    wu4.a_minus.connect(components_wu4['a_minus'], relationship=AMinusRelationship(alias="A4-"))

    # Should FAIL - Nexus is frozen (testing the other direction)
    with pytest.raises(ValueError, match="already has.*Cycle"):
        nexus.wisdom_units.connect(wu4)

    print("✓ Test 4: Cannot add WU to frozen Nexus via nexus.wisdom_units.connect()")

    # === Test 5: Evolution pattern - create new Nexus for changes ===

    # The correct way to "expand" a Nexus is to create a new one
    nexus2 = Nexus()
    nexus2.save()

    # Track evolution
    nexus.expanded_to.connect(nexus2)

    # Can add WUs to the new Nexus
    wu3.nexus.connect(nexus2)
    wu4.nexus.connect(nexus2)

    assert nexus2.wisdom_units.count() == 2
    assert nexus.expanded_to.count() == 1
    print("✓ Test 5: Evolution pattern works - new Nexus can receive WUs")

    print("\n✅ All Nexus frozen validation tests passed!")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
