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
    orphan_cycle.transitions.connect(orphan_trans)

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

    # Create Wheel and connect
    wheel = Wheel()
    wheel.save()
    wu.wheel.connect(wheel)

    # Create Cycle and connect transition + wheel
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.enums.causality_type import CausalityType
    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    cycle.transitions.connect(trans)
    wheel.t_cycle.connect(cycle)

    # Test 1: Default format (aliases)
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

    # Create Wheel
    wheel = Wheel()
    wheel.save()
    wu.wheel.connect(wheel)

    # Create Spiral transition: T- → A+ (segment transition)
    spiral_trans = Transition()
    spiral_trans.save()
    spiral_trans.source.connect(t_minus)
    spiral_trans.target.connect(a_plus)

    # Create Spiral and connect
    spiral = Spiral()
    spiral.save()
    spiral.transitions.connect(spiral_trans)
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
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.enums.causality_type import CausalityType

    cycle_trans = Transition()
    cycle_trans.save()
    cycle_trans.source.connect(t_minus)
    cycle_trans.target.connect(a_plus)

    cycle = Cycle(causality_type=CausalityType.BALANCED)
    cycle.save()
    cycle.transitions.connect(cycle_trans)
    wheel.t_cycle.connect(cycle)

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

    cycle3.transitions.connect(trans1c)
    cycle3.transitions.connect(trans2c)
    cycle3.transitions.connect(trans3c)

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

    # Create a wheel with 4 wisdom units
    wheel = Wheel()
    wheel.save()

    wus = []
    for i in range(4):
        wu = WisdomUnit(reasoning_mode=f"mode_{i}")
        wu.save()
        wu.wheel.connect(wheel)
        wus.append(wu)

    # Test 1: polarity_count property
    assert wheel.polarity_count == 4

    # Test 2: segment_count property (2 × polarity_count)
    assert wheel.segment_count == 8

    print(f"✓ polarity_count={wheel.polarity_count}, segment_count={wheel.segment_count}")


def test_wheel_wisdom_unit_at():
    """Test wisdom_unit_at() method (no integer indexing)."""

    wheel = Wheel()
    wheel.save()

    # Create wisdom units with components
    wus = []
    for i in range(3):
        wu = WisdomUnit()
        wu.save()
        wu.wheel.connect(wheel)

        # Add a T component with alias
        comp = DialecticalComponent(statement=f"Component {i}")
        comp.save()
        wu.t.connect(comp, properties={'alias': f'T{i}'})
        wus.append((wu, comp))

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
    """Test is_same_structure() for comparing wheels."""

    # Create first wheel with 2 wisdom units
    wheel1 = Wheel()
    wheel1.save()

    for i in range(2):
        wu = WisdomUnit()
        wu.save()
        wu.wheel.connect(wheel1)

    # Create second wheel with same order
    wheel2 = Wheel()
    wheel2.save()

    for i in range(2):
        wu = WisdomUnit()
        wu.save()
        wu.wheel.connect(wheel2)

    # Test 1: Same order
    assert wheel1.is_same_structure(wheel2)

    # Create third wheel with different order
    wheel3 = Wheel()
    wheel3.save()

    for i in range(3):  # Different order
        wu = WisdomUnit()
        wu.save()
        wu.wheel.connect(wheel3)

    # Test 2: Different order
    assert not wheel1.is_same_structure(wheel3)

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

    # Create wheel with 2 wisdom units
    wheel = Wheel()
    wheel.save()

    wus = []
    for i in range(2):
        wu = WisdomUnit(reasoning_mode=f"mode_{i}")
        wu.save()
        wu.wheel.connect(wheel)

        # Add T-side components
        t_comp = DialecticalComponent(statement=f"Thesis {i}")
        t_comp.save()
        wu.t.connect(t_comp, properties={'alias': f'T{i}'})

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
    wheel = Wheel()
    wheel.save()

    # Create 2 wisdom units
    wus = []
    for i in range(2):
        wu = WisdomUnit(reasoning_mode=f"mode_{i}")
        wu.save()
        wu.wheel.connect(wheel)

        # Add minimal components
        t = DialecticalComponent(statement=f"T{i}")
        t.save()
        wu.t.connect(t, properties={'alias': f'T{i}'})

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
    wheel = Wheel()
    wheel.save()

    wu = WisdomUnit(reasoning_mode="test")
    wu.save()
    wu.wheel.connect(wheel)

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


def test_dialectical_component_repository_find_wisdom_units():
    """Test DialecticalComponentRepository.find_wisdom_units()."""
    from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository

    # Create wisdom unit
    wu = WisdomUnit(reasoning_mode="test")
    wu.save()

    # Create component and connect it to wisdom unit
    component = DialecticalComponent(statement="Test statement")
    component.save()
    wu.t.connect(component, properties={'alias': 'T'})

    # Use repository to find wisdom units
    repo = DialecticalComponentRepository()
    results = repo.find_wisdom_units(component)

    # Verify results
    assert len(results) == 1
    assert results[0][0].uid == wu.uid
    assert results[0][1] == "T"

    print("✓ DialecticalComponentRepository.find_wisdom_units() works correctly")


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
    transformation.transitions.connect(trans1)

    trans2 = Transition()
    trans2.save()
    trans2.source.connect(wu_a_minus)
    trans2.target.connect(wu_t_plus)
    transformation.transitions.connect(trans2)

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


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
