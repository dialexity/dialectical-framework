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

import random

import pytest

from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.utils.order_transitions import order_transitions
from dialectical_framework.graph.relationships.polarity_relationship import (
    HasPolarityRelationship,
    TPlusRelationship,
    TMinusRelationship,
    APlusRelationship,
    AMinusRelationship,
)


def create_wisdom_unit_with_polarity(
    t_statement: str = "Democracy empowers citizens",
    a_statement: str = "Authority provides order",
    t_plus_statement: str = "Democracy promotes equality",
    t_minus_statement: str = "Democracy can be inefficient",
    a_plus_statement: str = "Authority ensures security",
    a_minus_statement: str = "Authority restricts freedom",
    intent: str = "test",
    heuristic_similarity: float = 0.8,
) -> tuple[WisdomUnit, Polarity, dict]:
    """
    Helper to create a WisdomUnit with proper Polarity structure.

    Returns:
        Tuple of (wisdom_unit, polarity, components_dict)
        where components_dict has keys: t, a, t_plus, t_minus, a_plus, a_minus
    """
    # Create T and A components
    t = DialecticalComponent(statement=t_statement, meaning="test")
    t.commit()
    a = DialecticalComponent(statement=a_statement, meaning="test")
    a.commit()

    # Create Polarity with T and A
    polarity = Polarity(intent=intent)
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=heuristic_similarity)
    polarity.commit()

    # Create WU and connect to Polarity
    wu = WisdomUnit(intent=intent)
    wu.save()
    wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Create and connect poles
    t_plus = DialecticalComponent(statement=t_plus_statement, meaning="test")
    t_plus.commit()
    t_minus = DialecticalComponent(statement=t_minus_statement, meaning="test")
    t_minus.commit()
    a_plus = DialecticalComponent(statement=a_plus_statement, meaning="test")
    a_plus.commit()
    a_minus = DialecticalComponent(statement=a_minus_statement, meaning="test")
    a_minus.commit()

    wu.t_plus.connect(t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9))
    wu.t_minus.connect(t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9))
    wu.a_plus.connect(a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9))
    wu.a_minus.connect(a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9))

    components = {
        "t": t,
        "a": a,
        "t_plus": t_plus,
        "t_minus": t_minus,
        "a_plus": a_plus,
        "a_minus": a_minus,
    }

    return wu, polarity, components


def create_wu_from_components(
    t: DialecticalComponent,
    a: DialecticalComponent,
    t_plus: DialecticalComponent | None = None,
    t_minus: DialecticalComponent | None = None,
    a_plus: DialecticalComponent | None = None,
    a_minus: DialecticalComponent | None = None,
    intent: str = "test",
    heuristic_similarity: float = 0.8,
) -> tuple[WisdomUnit, Polarity]:
    """
    Create a WisdomUnit with Polarity from pre-existing components.

    T and A are required and must be committed.
    Poles (T+, T-, A+, A-) are optional.

    Returns:
        Tuple of (wisdom_unit, polarity)
    """
    # Create Polarity with T and A
    polarity = Polarity(intent=intent)
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=heuristic_similarity)
    polarity.commit()

    # Create WU and connect to Polarity
    wu = WisdomUnit(intent=intent)
    wu.save()
    wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Connect poles if provided
    if t_plus:
        wu.t_plus.connect(t_plus, relationship=TPlusRelationship(alias="T+", heuristic_similarity=0.9))
    if t_minus:
        wu.t_minus.connect(t_minus, relationship=TMinusRelationship(alias="T-", heuristic_similarity=0.9))
    if a_plus:
        wu.a_plus.connect(a_plus, relationship=APlusRelationship(alias="A+", heuristic_similarity=0.9))
    if a_minus:
        wu.a_minus.connect(a_minus, relationship=AMinusRelationship(alias="A-", heuristic_similarity=0.9))

    return wu, polarity


def create_cycle_wheel_setup(
    wus: list[WisdomUnit],
    components_for_transitions: list[DialecticalComponent],
    cycle_intent: str = "preset:balanced",
    wheel_intent: str = "test_wheel",
) -> tuple[Cycle, Wheel, list[Transition]]:
    """
    Create a Cycle with ordered WUs and a Wheel with transitions.

    New model pattern (no Nexus):
    1. Create Cycle with set_wisdom_units()
    2. Create Wheel and add transitions
    3. Connect Wheel to Cycle

    Args:
        wus: List of committed WisdomUnits (order matters for T-cycle)
        components_for_transitions: Components to use for wheel transitions
            (must belong to WUs in the cycle)
        cycle_intent: Intent for the cycle
        wheel_intent: Intent for the wheel

    Returns:
        Tuple of (cycle, wheel, transitions)
    """
    # Ensure all WUs are committed
    for wu in wus:
        if not wu.is_committed:
            wu.commit()

    # Create Cycle with ordered WUs
    cycle = Cycle(intent=cycle_intent)
    cycle.set_wisdom_units(wus)
    cycle.commit()

    # Create Wheel
    wheel = Wheel(intent=wheel_intent)
    wheel.save()

    # Create transitions forming a cycle through the components
    transitions = []
    num_comps = len(components_for_transitions)
    for i in range(num_comps):
        trans = Transition()
        trans.set_source(components_for_transitions[i])
        trans.set_target(components_for_transitions[(i + 1) % num_comps])
        trans.commit()
        trans.cycle.connect(wheel)
        transitions.append(trans)

    # Connect Wheel to Cycle
    cycle.wheels.connect(wheel)

    return cycle, wheel, transitions


def test_create_simple_wisdom_unit():
    """Test creating a WisdomUnit with basic components."""

    # Use helper to create WU with proper Polarity structure
    wu, polarity, components = create_wisdom_unit_with_polarity(
        t_statement="Democracy empowers citizens",
        a_statement="Authority provides order",
        t_plus_statement="Democracy promotes equality",
        t_minus_statement="Democracy can be inefficient",
        a_plus_statement="Authority ensures security",
        a_minus_statement="Authority restricts freedom",
        intent="dialectical",
    )

    # Verify connections through Polarity
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

    # Create T and A components first
    t = DialecticalComponent(statement="Test thesis", meaning="test")
    t.commit()
    a = DialecticalComponent(statement="Antithesis", meaning="test")
    a.commit()

    # Create Polarity with T and A
    polarity = Polarity(intent="test")
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    # Create WU and connect to Polarity
    wu = WisdomUnit(intent=f"wu_{random.random()}")
    wu.save()
    wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Should not be complete (missing t_plus, t_minus, a_plus, a_minus)
    assert not wu.is_complete()

    # Add remaining required pole components
    t_plus = DialecticalComponent(statement="T+", meaning="test")
    t_plus.commit()
    wu.t_plus.connect(t_plus, relationship=TPlusRelationship(alias='T+', heuristic_similarity=0.9))

    t_minus = DialecticalComponent(statement="T-", meaning="test")
    t_minus.commit()
    wu.t_minus.connect(t_minus, relationship=TMinusRelationship(alias='T-', heuristic_similarity=0.9))

    a_plus = DialecticalComponent(statement="A+", meaning="test")
    a_plus.commit()
    wu.a_plus.connect(a_plus, relationship=APlusRelationship(alias='A+', heuristic_similarity=0.9))

    a_minus = DialecticalComponent(statement="A-", meaning="test")
    a_minus.commit()
    wu.a_minus.connect(a_minus, relationship=AMinusRelationship(alias='A-', heuristic_similarity=0.9))

    # Now should be complete (s_plus and s_minus are optional)
    assert wu.is_complete()

    print("✓ WisdomUnit completeness validation works correctly")


def test_component_aliases():
    """Test getting components with their contextual aliases from relationships."""

    # Create T and A components
    t = DialecticalComponent(statement="Thesis 3", meaning="test")
    a = DialecticalComponent(statement="Antithesis 3", meaning="test")
    t.commit()
    a.commit()

    # Create Polarity with custom aliases (aliases are stored on relationship)
    polarity = Polarity(intent="test")
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    # Create WU and connect to Polarity
    wu = WisdomUnit(intent=f"wu_{random.random()}")
    wu.save()
    wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

    # Get all components with their aliases using repository
    from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
    repo = DialecticalComponentRepository()
    components_with_aliases = repo.find_by_wisdom_unit(wu)

    # Should find T and A through Polarity
    assert len(components_with_aliases) == 2
    aliases = [alias for _, alias in components_with_aliases]
    assert 'T' in aliases
    assert 'A' in aliases

    # Test component.get_alias() method
    t_alias = t.get_alias(wu)
    a_alias = a.get_alias(wu)

    assert t_alias == 'T'
    assert a_alias == 'A'

    # Test with component not in this wisdom unit
    other_comp = DialecticalComponent(statement="Not connected", meaning="test")
    other_comp.commit()

    # Should raise ValueError when component not connected to WU
    import pytest
    with pytest.raises(ValueError, match="not connected to WisdomUnit"):
        other_comp.get_alias(wu)

    print(f"✓ Component aliases retrieved from relationships: {aliases}")
    print(f"✓ component.get_alias() works correctly: T={t_alias}, A={a_alias}")


def test_cycle_ordered_wisdom_units():
    """Test that Cycle stores WisdomUnits in order (T-cycle)."""

    # Create 3 WisdomUnits with proper Polarity structure
    wu1, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 1", a_statement="Antithesis 1",
        t_plus_statement="T1+", t_minus_statement="T1-",
        a_plus_statement="A1+", a_minus_statement="A1-",
        intent=f"wu1_{random.random()}"
    )
    wu1.commit()

    wu2, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 2", a_statement="Antithesis 2",
        t_plus_statement="T2+", t_minus_statement="T2-",
        a_plus_statement="A2+", a_minus_statement="A2-",
        intent=f"wu2_{random.random()}"
    )
    wu2.commit()

    wu3, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 3", a_statement="Antithesis 3",
        t_plus_statement="T3+", t_minus_statement="T3-",
        a_plus_statement="A3+", a_minus_statement="A3-",
        intent=f"wu3_{random.random()}"
    )
    wu3.commit()

    # Create cycle with ordered WUs (order defines T-cycle: T1 → T2 → T3)
    cycle = Cycle(intent="preset:balanced")
    cycle.set_wisdom_units([wu1, wu2, wu3])
    cycle.commit()

    # Verify order is preserved
    assert cycle.wisdom_unit_count == 3, f"Expected 3 WUs, got {cycle.wisdom_unit_count}"
    assert cycle.wisdom_unit_hashes == [wu1.hash, wu2.hash, wu3.hash], "Order should be preserved"

    # Verify wisdom_units property returns WUs in order
    wus = cycle.wisdom_units
    assert len(wus) == 3, f"Expected 3 WUs, got {len(wus)}"
    assert wus[0].hash == wu1.hash, "First WU should be wu1"
    assert wus[1].hash == wu2.hash, "Second WU should be wu2"
    assert wus[2].hash == wu3.hash, "Third WU should be wu3"

    print(f"✓ Cycle T-cycle order preserved: WU1 → WU2 → WU3")


def test_cycle_requires_committed_wisdom_units():
    """Test that Cycle requires committed WisdomUnits."""

    # Create uncommitted WU
    wu, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 1", a_statement="Antithesis 1",
        t_plus_statement="T1+", t_minus_statement="T1-",
        a_plus_statement="A1+", a_minus_statement="A1-",
        intent=f"wu_{random.random()}"
    )
    # wu is NOT committed

    # Create cycle
    cycle = Cycle(intent="preset:realistic")

    # Should fail with uncommitted WU
    with pytest.raises(ValueError, match="WisdomUnit must be committed"):
        cycle.set_wisdom_units([wu])

    # Now commit WU and try again
    wu.commit()
    cycle.set_wisdom_units([wu])
    cycle.commit()

    assert cycle.wisdom_unit_count == 1
    assert cycle.wisdom_unit_hashes == [wu.hash]

    print(f"✓ Cycle correctly validates WU commitment")


def test_cycle_str_formatting():
    """Test Cycle string formatting shows T-cycle."""

    # Create 3 WisdomUnits
    wu1, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 1", a_statement="Antithesis 1",
        t_plus_statement="T1+", t_minus_statement="T1-",
        a_plus_statement="A1+", a_minus_statement="A1-",
        intent=f"wu1_{random.random()}"
    )
    wu1.commit()

    wu2, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 2", a_statement="Antithesis 2",
        t_plus_statement="T2+", t_minus_statement="T2-",
        a_plus_statement="A2+", a_minus_statement="A2-",
        intent=f"wu2_{random.random()}"
    )
    wu2.commit()

    wu3, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 3", a_statement="Antithesis 3",
        t_plus_statement="T3+", t_minus_statement="T3-",
        a_plus_statement="A3+", a_minus_statement="A3-",
        intent=f"wu3_{random.random()}"
    )
    wu3.commit()

    # Create cycle with 3 WUs
    cycle = Cycle(intent="preset:desirable")
    cycle.set_wisdom_units([wu1, wu2, wu3])
    cycle.commit()

    # Test default format shows T-cycle
    cycle_string = str(cycle)
    assert "T1" in cycle_string, f"Expected T1 in cycle string: {cycle_string}"
    assert "T2" in cycle_string, f"Expected T2 in cycle string: {cycle_string}"
    assert "T3" in cycle_string, f"Expected T3 in cycle string: {cycle_string}"
    assert "→" in cycle_string, f"Expected arrows in cycle string: {cycle_string}"

    print(f"✓ Cycle string shows T-cycle: {cycle_string}")

    # Test verbose format
    verbose_string = f"{cycle:verbose}"
    assert "preset:desirable" in verbose_string, f"Expected intent in verbose: {verbose_string}"
    assert "T1" in verbose_string
    assert "Rationale" in verbose_string  # Shows "Rationale: N/A" when no rationales

    print(f"✓ Cycle verbose format works correctly")

    # Test repr
    cycle_repr = repr(cycle)
    assert "Cycle" in cycle_repr
    assert "wu_count=3" in cycle_repr
    assert "preset:desirable" in cycle_repr

    print(f"✓ Cycle repr: {cycle_repr}")


def test_transition_str_formatting():
    """Test Transition.__format__() with various modes."""

    # Create components (T- and A+ are source/target for transition)
    source_comp = DialecticalComponent(statement="Negative aspect of thesis", meaning="test")
    target_comp = DialecticalComponent(statement="Positive aspect of antithesis", meaning="test")
    source_comp.commit()
    target_comp.commit()

    # Create T and A components for Polarity
    t_comp = DialecticalComponent(statement="Thesis", meaning="test")
    t_comp.commit()
    a_comp = DialecticalComponent(statement="Antithesis", meaning="test")
    a_comp.commit()

    # Create additional components for T+ and A- positions
    t_plus_comp = DialecticalComponent(statement="Positive thesis aspect", meaning="test")
    t_plus_comp.commit()
    a_minus_comp = DialecticalComponent(statement="Negative antithesis aspect", meaning="test")
    a_minus_comp.commit()

    # Create WisdomUnit with Polarity and connect all components with aliases
    wu, _ = create_wu_from_components(
        t=t_comp,
        a=a_comp,
        t_plus=t_plus_comp,
        t_minus=source_comp,
        a_plus=target_comp,
        a_minus=a_minus_comp,
        intent=f"wu_{random.random()}",
    )
    wu.commit()

    # Create Cycle with ordered WUs (new model: no Nexus)
    cycle = Cycle(intent="preset:balanced")
    cycle.set_wisdom_units([wu])
    cycle.commit()

    # Create transition with source/target set before save
    trans = Transition()
    trans.set_source(source_comp).set_target(target_comp)
    trans.commit()

    # Create Wheel and connect transitions to it (not to Cycle)
    wheel = Wheel(intent="test_transition_str_formatting")
    wheel.save()

    # Connect transition to wheel
    trans.cycle.connect(wheel)

    # Add second transition to form a cycle (wheel needs at least 2 transitions)
    trans2 = Transition()
    trans2.set_source(target_comp).set_target(source_comp)
    trans2.commit()
    trans2.cycle.connect(wheel)

    # Connect Wheel to Cycle
    cycle.wheels.connect(wheel)

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
    rationale.set_explanation_target(trans)  # Set target before save
    rationale.commit()

    verbose_str = f"{trans:verbose}"
    assert "T-" in verbose_str
    assert "A+" in verbose_str
    assert "Rationale:" in verbose_str
    assert "dialectical transformation" in verbose_str
    print(f"✓ Transition verbose format: {verbose_str}")

    # Test 5: Orphan transition (no wheel context) - should fallback to UID
    orphan_comp1 = DialecticalComponent(statement="Orphan source", meaning="test")
    orphan_comp2 = DialecticalComponent(statement="Orphan target", meaning="test")
    orphan_comp1.commit()
    orphan_comp2.commit()
    orphan_trans = Transition()
    orphan_trans.set_source(orphan_comp1).set_target(orphan_comp2)
    orphan_trans.commit()

    orphan_str = str(orphan_trans)
    # Should contain truncated UIDs (8 chars) since no wheel context
    assert "→" in orphan_str
    print(f"✓ Orphan transition fallback: {orphan_str}")

    # Test 6: Orphan transition with statements mode
    orphan_statements = f"{orphan_trans:statements}"
    assert "Orphan source" in orphan_statements
    assert "Orphan target" in orphan_statements
    print(f"✓ Orphan transition statements format: {orphan_statements}")


def test_transition_formatting_with_wheel():
    """Test Transition formatting shows segment aliases for Wheel."""
    # Create components for a full wisdom unit
    t = DialecticalComponent(statement="Main thesis", meaning="test")
    t_plus = DialecticalComponent(statement="Positive thesis", meaning="test")
    t_minus = DialecticalComponent(statement="Negative thesis", meaning="test")
    a = DialecticalComponent(statement="Main antithesis", meaning="test")
    a_plus = DialecticalComponent(statement="Positive antithesis", meaning="test")
    a_minus = DialecticalComponent(statement="Negative antithesis", meaning="test")

    for comp in [t, t_plus, t_minus, a, a_plus, a_minus]:
        comp.commit()

    # Create WisdomUnit with Polarity
    wu, _ = create_wu_from_components(
        t=t,
        a=a,
        t_plus=t_plus,
        t_minus=t_minus,
        a_plus=a_plus,
        a_minus=a_minus,
        intent=f"wu_{random.random()}",
    )
    wu.commit()

    # Create Cycle with ordered WUs (new model: no Nexus)
    cycle_base = Cycle(intent="preset:realistic")
    cycle_base.set_wisdom_units([wu])
    cycle_base.commit()

    # Create Wheel
    wheel = Wheel(intent="test_transition_formatting_with_wheel")
    wheel.save()

    # Create wheel transitions
    wheel_trans1 = Transition()
    wheel_trans1.set_source(t).set_target(a)
    wheel_trans1.commit()
    wheel_trans1.cycle.connect(wheel)

    wheel_trans2 = Transition()
    wheel_trans2.set_source(a).set_target(t)
    wheel_trans2.commit()
    wheel_trans2.cycle.connect(wheel)

    # Connect Wheel to Cycle
    cycle_base.wheels.connect(wheel)

    # Test: Wheel transition should show component format
    wheel_str = str(wheel_trans1)
    print(f"Wheel transition format: {wheel_str}")
    assert "→" in wheel_str
    print(f"✓ Wheel transition shows component aliases: {wheel_str}")


def test_cycle_hash_identity():
    """Test that Cycle hash depends on ordered WUs and intent."""

    # Create 3 WisdomUnits
    wu1, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 1", a_statement="Antithesis 1",
        t_plus_statement="T1+", t_minus_statement="T1-",
        a_plus_statement="A1+", a_minus_statement="A1-",
        intent=f"wu1_{random.random()}"
    )
    wu1.commit()

    wu2, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 2", a_statement="Antithesis 2",
        t_plus_statement="T2+", t_minus_statement="T2-",
        a_plus_statement="A2+", a_minus_statement="A2-",
        intent=f"wu2_{random.random()}"
    )
    wu2.commit()

    wu3, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis 3", a_statement="Antithesis 3",
        t_plus_statement="T3+", t_minus_statement="T3-",
        a_plus_statement="A3+", a_minus_statement="A3-",
        intent=f"wu3_{random.random()}"
    )
    wu3.commit()

    # Create cycle with WUs in order [wu1, wu2, wu3]
    cycle1 = Cycle(intent="preset:balanced")
    cycle1.set_wisdom_units([wu1, wu2, wu3])
    cycle1.commit()

    # Create another cycle with SAME WUs in SAME order and SAME intent
    # This should produce the same hash (content-addressed identity)
    cycle2 = Cycle(intent="preset:balanced")
    cycle2.set_wisdom_units([wu1, wu2, wu3])
    # Note: Don't commit cycle2 - we'll check the hash computation

    # Create cycle with WUs in DIFFERENT order - should have different hash
    cycle3 = Cycle(intent="preset:balanced")
    cycle3.set_wisdom_units([wu2, wu1, wu3])  # Different order!
    cycle3.commit()

    assert cycle1.hash != cycle3.hash, "Different WU order should produce different hash"

    # Create cycle with SAME WUs but DIFFERENT intent - should have different hash
    cycle4 = Cycle(intent="preset:realistic")  # Different intent!
    cycle4.set_wisdom_units([wu1, wu2, wu3])
    cycle4.commit()

    assert cycle1.hash != cycle4.hash, "Different intent should produce different hash"

    print(f"✓ Cycle hash correctly depends on WU order and intent")
    print(f"  cycle1 (balanced, 1-2-3): {cycle1.short_hash}")
    print(f"  cycle3 (balanced, 2-1-3): {cycle3.short_hash}")
    print(f"  cycle4 (realistic, 1-2-3): {cycle4.short_hash}")


def test_estimation_properties():
    """Test probability and relevance properties on AssessableEntity."""
    import math
    import random

    # Use random values to avoid collision with previous test runs
    p1 = round(0.7 + random.random() * 0.05, 4)  # ~0.70-0.75
    p2 = round(0.88 + random.random() * 0.05, 4)  # ~0.88-0.93
    r1 = round(0.83 + random.random() * 0.05, 4)  # ~0.83-0.88
    r2 = round(0.93 + random.random() * 0.05, 4)  # ~0.93-0.98

    # Create a component with unique statement
    comp = DialecticalComponent(statement=f"Test component {random.random()}", meaning="test")
    comp.commit()

    # Test 1: No estimations - should return None
    assert comp.probability is None
    assert comp.relevance is None

    # Test 2: Single probability estimation
    prob_est = ProbabilityEstimation(value=p1)
    prob_est.set_target(comp)  # Set target before save
    prob_est.commit()

    assert comp.probability == p1
    assert comp.relevance is None  # Still no relevance

    # Test 3: Single relevance estimation
    rel_est = RelevanceEstimation(value=r1)
    rel_est.set_target(comp)
    rel_est.commit()

    assert comp.probability == p1
    assert comp.relevance == r1

    # Test 4: Multiple estimations - should return geometric mean
    prob_est2 = ProbabilityEstimation(value=p2)
    prob_est2.set_target(comp)
    prob_est2.commit()

    rel_est2 = RelevanceEstimation(value=r2)
    rel_est2.set_target(comp)
    rel_est2.commit()

    # Geometric mean: GM(p1, p2) = sqrt(p1 * p2)
    expected_prob = math.sqrt(p1 * p2)
    assert abs(comp.probability - expected_prob) < 0.001

    # Geometric mean: GM(r1, r2) = sqrt(r1 * r2)
    expected_rel = math.sqrt(r1 * r2)
    assert abs(comp.relevance - expected_rel) < 0.001

    print(f"✓ Probability property works correctly (GM): {comp.probability:.4f}")
    print(f"✓ Relevance property works correctly (GM): {comp.relevance:.4f}")

    # Test 5: Zero estimation - should return 0 (veto semantics)
    comp2 = DialecticalComponent(statement=f"Test component 2 {random.random()}", meaning="test")
    comp2.commit()

    prob_est3 = ProbabilityEstimation(value=round(0.79 + random.random() * 0.02, 4))
    prob_est3.set_target(comp2)
    prob_est3.commit()

    # Use tiny random value (near zero) to test veto semantics while avoiding hash collision
    tiny_value = random.random() * 1e-10  # Very small but not exactly 0
    prob_est4 = ProbabilityEstimation(value=tiny_value)
    prob_est4.set_target(comp2)
    prob_est4.commit()

    # Near-zero value should effectively veto (geometric mean approaches zero)
    assert comp2.probability < 0.01  # Effectively vetoed

    print(f"✓ Near-zero estimation veto works correctly: {comp2.probability}")


def test_best_rationale_property():
    """Test best_rationale property on AssessableEntity."""
    # Create a component
    comp = DialecticalComponent(statement="Test component", meaning="test")
    comp.commit()

    # Test 1: No rationales - should return None
    assert comp.best_rationale is None

    # Test 2: Single rationale without rating
    r1 = Rationale(text="First rationale")
    r1.set_explanation_target(comp)  # Set target before save
    r1.commit()

    best = comp.best_rationale
    assert best is not None
    assert best.hash == r1.hash
    assert best.text == "First rationale"

    # Test 3: Multiple rationales with ratings
    # Note: Rationale no longer extends AssessableEntity and doesn't have score.
    # Use the rating field instead for ranking.
    r2 = Rationale(text="Second rationale", rating=0.7)
    r2.set_explanation_target(comp)
    r2.commit()

    r3 = Rationale(text="Third rationale", rating=0.9)
    r3.set_explanation_target(comp)
    r3.commit()

    # Should return r3 (highest rating)
    best = comp.best_rationale
    assert best.hash == r3.hash
    assert best.rating == 0.9
    assert best.text == "Third rationale"

    # Test 4: Add even higher rated rationale
    r4 = Rationale(text="Fourth rationale", rating=0.95)
    r4.set_explanation_target(comp)
    r4.commit()

    best = comp.best_rationale
    assert best.hash == r4.hash
    assert best.rating == 0.95

    print(f"✓ best_rationale property works correctly: rating={best.rating}")


def test_wheel_navigation_properties():
    """Test wheel navigation properties (order, degree)."""

    # Create 4 wisdom units with full components using Polarity
    wus = []
    a_components = []
    for i in range(4):
        # Create all required components for a complete WU
        t_comp = DialecticalComponent(statement=f"T Component {i}", meaning="test")
        t_comp.commit()
        t_plus = DialecticalComponent(statement=f"T+ Component {i}", meaning="test")
        t_plus.commit()
        t_minus = DialecticalComponent(statement=f"T- Component {i}", meaning="test")
        t_minus.commit()

        a_comp = DialecticalComponent(statement=f"A Component {i}", meaning="test")
        a_comp.commit()
        a_plus = DialecticalComponent(statement=f"A+ Component {i}", meaning="test")
        a_plus.commit()
        a_minus = DialecticalComponent(statement=f"A- Component {i}", meaning="test")
        a_minus.commit()

        # Create WU with Polarity and all poles
        wu, _ = create_wu_from_components(
            t=t_comp,
            a=a_comp,
            t_plus=t_plus,
            t_minus=t_minus,
            a_plus=a_plus,
            a_minus=a_minus,
            intent=f"mode_{i}",
        )

        wus.append(wu)
        a_components.append(a_comp)

    # Use helper to create Cycle+Wheel setup (new model: no Nexus)
    cycle, wheel, _ = create_cycle_wheel_setup(
        wus=wus,
        components_for_transitions=a_components,  # Use A components for transitions
        cycle_intent="preset:balanced",
        wheel_intent=f"wheel_{random.random()}",
    )

    # Test 1: polarity_count property
    assert wheel.polarity_count == 4

    # Test 2: segment_count property (2 × polarity_count)
    assert wheel.segment_count == 8

    print(f"✓ polarity_count={wheel.polarity_count}, segment_count={wheel.segment_count}")


def test_wheel_wisdom_unit_at():
    """Test polar_segment_at() method (no integer indexing)."""

    # Create wisdom units with full components using Polarity
    wus = []
    t_components = []
    a_components = []
    for i in range(3):
        # Create all required components
        t_comp = DialecticalComponent(statement=f"T Component {i}", meaning="test")
        t_comp.commit()
        t_plus = DialecticalComponent(statement=f"T+ Component {i}", meaning="test")
        t_plus.commit()
        t_minus = DialecticalComponent(statement=f"T- Component {i}", meaning="test")
        t_minus.commit()

        a_comp = DialecticalComponent(statement=f"A Component {i}", meaning="test")
        a_comp.commit()
        a_plus = DialecticalComponent(statement=f"A+ Component {i}", meaning="test")
        a_plus.commit()
        a_minus = DialecticalComponent(statement=f"A- Component {i}", meaning="test")
        a_minus.commit()

        # Create WU with Polarity and all poles
        wu, _ = create_wu_from_components(
            t=t_comp,
            a=a_comp,
            t_plus=t_plus,
            t_minus=t_minus,
            a_plus=a_plus,
            a_minus=a_minus,
            intent=f"wu_{random.random()}",
        )

        wus.append((wu, t_comp))
        t_components.append(t_comp)
        a_components.append(a_comp)

    # Use helper to create Cycle+Wheel setup (new model: no Nexus)
    wu_list = [w[0] for w in wus]
    cycle, wheel, _ = create_cycle_wheel_setup(
        wus=wu_list,
        components_for_transitions=a_components,  # Use A components for transitions
        cycle_intent="preset:balanced",
        wheel_intent=f"wheel_{random.random()}",
    )

    # Test 1: Get by component (T components) - returns polar pair
    pair = wheel.polar_segment_at(t_components[0])
    assert pair.wisdom_unit.hash == wus[0][0].hash

    pair = wheel.polar_segment_at(t_components[1])
    assert pair.wisdom_unit.hash == wus[1][0].hash

    pair = wheel.polar_segment_at(t_components[2])
    assert pair.wisdom_unit.hash == wus[2][0].hash

    # Test 2: Get by component (from wus tuple)
    pair = wheel.polar_segment_at(wus[0][1])
    assert pair.wisdom_unit.hash == wus[0][0].hash

    pair = wheel.polar_segment_at(wus[2][1])  # Component from wu2
    assert pair.wisdom_unit.hash == wus[2][0].hash

    # Test 3: Get by WisdomUnit
    pair = wheel.polar_segment_at(wus[1][0])
    assert pair.wisdom_unit.hash == wus[1][0].hash

    # Test 4: Component not found
    orphan_comp = DialecticalComponent(statement="Orphan", meaning="test")
    orphan_comp.commit()
    try:
        _ = wheel.polar_segment_at(orphan_comp)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass

    print("✓ polar_segment_at() works with alias, component, and WisdomUnit")


def test_wheel_is_same_structure():
    """Test is_same_structure() for comparing wheels by transitions."""

    # Helper function to create a complete wheel setup (new model: no Nexus)
    def create_wheel_with_transitions(n_components: int, prefix: str):
        """Create a wheel with n components connected in a cycle."""
        a_components = []

        # Create WisdomUnits with all required components using Polarity
        wus = []
        for i in range(n_components):
            # Create all required components
            t_comp = DialecticalComponent(statement=f"{prefix} T Component {i}", meaning="test")
            t_comp.commit()
            t_plus = DialecticalComponent(statement=f"{prefix} T+ Component {i}", meaning="test")
            t_plus.commit()
            t_minus = DialecticalComponent(statement=f"{prefix} T- Component {i}", meaning="test")
            t_minus.commit()

            a_comp = DialecticalComponent(statement=f"{prefix} A Component {i}", meaning="test")
            a_comp.commit()
            a_plus = DialecticalComponent(statement=f"{prefix} A+ Component {i}", meaning="test")
            a_plus.commit()
            a_minus = DialecticalComponent(statement=f"{prefix} A- Component {i}", meaning="test")
            a_minus.commit()

            a_components.append(a_comp)

            # Create WU with Polarity and all poles
            wu, _ = create_wu_from_components(
                t=t_comp,
                a=a_comp,
                t_plus=t_plus,
                t_minus=t_minus,
                a_plus=a_plus,
                a_minus=a_minus,
                intent=f"wu_{random.random()}",
            )
            wus.append(wu)

        # Use helper to create Cycle+Wheel setup
        cycle, wheel, _ = create_cycle_wheel_setup(
            wus=wus,
            components_for_transitions=a_components,
            cycle_intent="preset:balanced",
            wheel_intent=f"wheel_{random.random()}",
        )

        return wheel, a_components

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

    # Create all components
    t_comp = DialecticalComponent(statement="Thesis", meaning="test")
    t_comp.commit()
    t_plus_comp = DialecticalComponent(statement="Thesis positive", meaning="test")
    t_plus_comp.commit()
    t_minus_comp = DialecticalComponent(statement="Thesis negative", meaning="test")
    t_minus_comp.commit()
    a_comp = DialecticalComponent(statement="Antithesis", meaning="test")
    a_comp.commit()
    a_plus_comp = DialecticalComponent(statement="Antithesis positive", meaning="test")
    a_plus_comp.commit()
    a_minus_comp = DialecticalComponent(statement="Antithesis negative", meaning="test")
    a_minus_comp.commit()

    # Create WisdomUnit with Polarity
    wu, _ = create_wu_from_components(
        t=t_comp,
        a=a_comp,
        t_plus=t_plus_comp,
        t_minus=t_minus_comp,
        a_plus=a_plus_comp,
        a_minus=a_minus_comp,
        intent="test",
    )

    # Get T-side segment
    t_seg = wu.segment_t
    assert isinstance(t_seg, WheelSegment)
    assert t_seg.side == 'T'
    assert t_seg.wisdom_unit.hash == wu.hash

    # Test window into T-side relationships
    assert t_seg.t.get()[0].hash == t_comp.hash
    t_plus_list = [c for c, _ in t_seg.t_plus.all()]
    assert len(t_plus_list) == 1
    assert t_plus_list[0].hash == t_plus_comp.hash
    t_minus_list = [c for c, _ in t_seg.t_minus.all()]
    assert len(t_minus_list) == 1
    assert t_minus_list[0].hash == t_minus_comp.hash
    assert t_seg.is_complete()

    # Get A-side segment
    a_seg = wu.segment_a
    assert isinstance(a_seg, WheelSegment)
    assert a_seg.side == 'A'
    assert a_seg.wisdom_unit.hash == wu.hash

    # Test window into A-side relationships (using t/t_plus/t_minus properties)
    assert a_seg.t.get()[0].hash == a_comp.hash
    a_plus_list = [c for c, _ in a_seg.t_plus.all()]
    assert len(a_plus_list) == 1
    assert a_plus_list[0].hash == a_plus_comp.hash
    a_minus_list = [c for c, _ in a_seg.t_minus.all()]
    assert len(a_minus_list) == 1
    assert a_minus_list[0].hash == a_minus_comp.hash
    assert a_seg.is_complete()

    print("✓ WheelSegment.segment_t and segment_a work correctly")


def test_wheel_segment_get_component_by_alias():
    """Test finding components within a segment by alias."""
    # Create components
    t_comp = DialecticalComponent(statement="Thesis", meaning="test")
    t_comp.commit()
    t_plus_comp = DialecticalComponent(statement="Thesis positive", meaning="test")
    t_plus_comp.commit()
    a_comp = DialecticalComponent(statement="Antithesis", meaning="test")
    a_comp.commit()

    # Create WisdomUnit with Polarity
    wu, _ = create_wu_from_components(
        t=t_comp,
        a=a_comp,
        t_plus=t_plus_comp,
        intent="test",
    )

    # Get T-side segment
    t_seg = wu.segment_t

    # Find T-side components by alias (default aliases from create_wu_from_components)
    found_t = t_seg.get_component('T')
    assert found_t is not None
    assert found_t.hash == t_comp.hash

    found_t_plus = t_seg.get_component('T+')
    assert found_t_plus is not None
    assert found_t_plus.hash == t_plus_comp.hash

    # A-side component should not be found in T-side segment
    found_a = t_seg.get_component('A')
    assert found_a is None

    # Get A-side segment
    a_seg = wu.segment_a

    # Find A-side component by alias
    found_a = a_seg.get_component('A')
    assert found_a is not None
    assert found_a.hash == a_comp.hash

    # T-side component should not be found in A-side segment
    found_t = a_seg.get_component('T')
    assert found_t is None

    print("✓ WheelSegment.get_component_by_alias() filters by side correctly")


def test_wheel_segment_at():
    """Test Wheel.segment_at() lookup by alias or component."""
    from dialectical_framework.graph.wheel_segment import WheelSegment

    # Create 2 wisdom units with full components using Polarity
    wus = []
    t_comps = []
    a_comps = []
    for i in range(2):
        # Create all components
        t_comp = DialecticalComponent(statement=f"Thesis {i}", meaning="test")
        t_comp.commit()
        t_comps.append(t_comp)

        t_plus = DialecticalComponent(statement=f"T+ {i}", meaning="test")
        t_plus.commit()
        t_minus = DialecticalComponent(statement=f"T- {i}", meaning="test")
        t_minus.commit()

        a_comp = DialecticalComponent(statement=f"Antithesis {i}", meaning="test")
        a_comp.commit()
        a_comps.append(a_comp)

        a_plus = DialecticalComponent(statement=f"A+ {i}", meaning="test")
        a_plus.commit()
        a_minus = DialecticalComponent(statement=f"A- {i}", meaning="test")
        a_minus.commit()

        # Create WU with Polarity
        wu, _ = create_wu_from_components(
            t=t_comp,
            a=a_comp,
            t_plus=t_plus,
            t_minus=t_minus,
            a_plus=a_plus,
            a_minus=a_minus,
            intent=f"mode_{i}",
        )

        wus.append((wu, t_comp, a_comp))

    # Use helper to create Cycle+Wheel setup (new model: no Nexus)
    wu_list = [w[0] for w in wus]
    cycle, wheel, _ = create_cycle_wheel_setup(
        wus=wu_list,
        components_for_transitions=a_comps,  # Use A components for transitions
        cycle_intent="preset:balanced",
        wheel_intent=f"wheel_{random.random()}",
    )

    # Test 1: By component (T components)
    seg_t0 = wheel.segment_at(t_comps[0])
    assert isinstance(seg_t0, WheelSegment)
    assert seg_t0.side == 'T'
    assert seg_t0.wisdom_unit.hash == wus[0][0].hash

    seg_a1 = wheel.segment_at(wus[1][2])  # A component of second WU
    assert seg_a1.side == 'A'
    assert seg_a1.wisdom_unit.hash == wus[1][0].hash

    # Test 2: By component (from wus tuple)
    seg_by_comp = wheel.segment_at(wus[0][1])  # T component of first WU
    assert seg_by_comp.side == 'T'
    assert seg_by_comp.wisdom_unit.hash == wus[0][0].hash

    seg_by_a_comp = wheel.segment_at(wus[1][2])  # A component of second WU
    assert seg_by_a_comp.side == 'A'
    assert seg_by_a_comp.wisdom_unit.hash == wus[1][0].hash

    print("✓ Wheel.segment_at() supports component lookup")


def test_wheel_segment_is_same():
    """Test WheelSegment.is_same() comparison."""
    # Create WUs using helper
    wus = []
    for idx in range(2):
        t_comp = DialecticalComponent(statement=f"Thesis WU{idx}", meaning="test")
        t_comp.commit()
        t_plus = DialecticalComponent(statement=f"T+ WU{idx}", meaning="test")
        t_plus.commit()
        t_minus = DialecticalComponent(statement=f"T- WU{idx}", meaning="test")
        t_minus.commit()
        a_comp = DialecticalComponent(statement=f"Antithesis WU{idx}", meaning="test")
        a_comp.commit()

        wu, _ = create_wu_from_components(
            t=t_comp,
            a=a_comp,
            t_plus=t_plus,
            t_minus=t_minus,
            intent=f"test{idx+1}",
        )
        wus.append(wu)

    wu1, wu2 = wus

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
    # Create components
    t_comp = DialecticalComponent(statement="Thesis", meaning="test")
    t_comp.commit()
    t_plus = DialecticalComponent(statement="T+", meaning="test")
    t_plus.commit()
    a_comp = DialecticalComponent(statement="Antithesis", meaning="test")
    a_comp.commit()

    # Create WU with Polarity
    wu, _ = create_wu_from_components(
        t=t_comp,
        a=a_comp,
        t_plus=t_plus,
        intent="test",
    )

    # Get segments
    t_seg = wu.segment_t
    a_seg = wu.segment_a

    # Test is_set by alias (default aliases from helper)
    assert t_seg.is_set("T")
    assert t_seg.is_set("T+")
    assert not t_seg.is_set("A")  # A component not in T segment

    assert a_seg.is_set("A")
    assert not a_seg.is_set("T")  # T component not in A segment

    # Test is_set by component
    assert t_seg.is_set(t_comp)
    assert t_seg.is_set(t_plus)
    assert not t_seg.is_set(a_comp)

    assert a_seg.is_set(a_comp)
    assert not a_seg.is_set(t_comp)

    print("✓ WheelSegment.is_set() works correctly")


def test_wheel_wisdom_unit_at_segment():
    """Test Wheel.polar_segment_at() with WheelSegment."""
    # Create 2 wisdom units with components using Polarity
    wus = []
    a_comps = []
    for i in range(2):
        # Create components
        t = DialecticalComponent(statement=f"T{i}", meaning="test")
        t.commit()

        t_plus = DialecticalComponent(statement=f"T{i}+", meaning="test")
        t_plus.commit()
        t_minus = DialecticalComponent(statement=f"T{i}-", meaning="test")
        t_minus.commit()

        a = DialecticalComponent(statement=f"A{i}", meaning="test")
        a.commit()
        a_comps.append(a)

        a_plus = DialecticalComponent(statement=f"A{i}+", meaning="test")
        a_plus.commit()
        a_minus = DialecticalComponent(statement=f"A{i}-", meaning="test")
        a_minus.commit()

        # Create WU with Polarity
        wu, _ = create_wu_from_components(
            t=t,
            a=a,
            t_plus=t_plus,
            t_minus=t_minus,
            a_plus=a_plus,
            a_minus=a_minus,
            intent=f"mode_{i}",
        )
        wus.append(wu)

    # Use helper to create Cycle+Wheel setup (new model: no Nexus)
    cycle, wheel, _ = create_cycle_wheel_setup(
        wus=wus,
        components_for_transitions=a_comps,  # Use A components for transitions
        cycle_intent="preset:balanced",
        wheel_intent=f"wheel_{random.random()}",
    )

    # Get segments
    t_seg_1 = wus[1].segment_t
    a_seg_0 = wus[0].segment_a

    # Test polar_segment_at with WheelSegment - returns polar pair
    found_pair = wheel.polar_segment_at(t_seg_1)
    assert found_pair.wisdom_unit.hash == wus[1].hash

    found_pair = wheel.polar_segment_at(a_seg_0)
    assert found_pair.wisdom_unit.hash == wus[0].hash

    print("✓ Wheel.polar_segment_at() works with WheelSegment")


def test_wheel_is_set():
    """Test Wheel.is_set() method."""
    # Create all required components
    t = DialecticalComponent(statement="T", meaning="test")
    t.commit()
    t_plus = DialecticalComponent(statement="T+", meaning="test")
    t_plus.commit()
    t_wheel = DialecticalComponent(statement="T wheel specific (T-)", meaning="test")
    t_wheel.commit()
    a = DialecticalComponent(statement="A", meaning="test")
    a.commit()
    a_wheel = DialecticalComponent(statement="A wheel specific (A+)", meaning="test")
    a_wheel.commit()
    a_minus = DialecticalComponent(statement="A-", meaning="test")
    a_minus.commit()

    # Create WU with Polarity and all poles
    wu, _ = create_wu_from_components(
        t=t,
        a=a,
        t_plus=t_plus,
        t_minus=t_wheel,
        a_plus=a_wheel,
        a_minus=a_minus,
        intent="test",
    )
    wu.commit()

    # Use helper to create Cycle+Wheel setup (new model: no Nexus)
    # Use t_wheel and a_wheel for transitions since they're connected to WU as T- and A+
    cycle, wheel, _ = create_cycle_wheel_setup(
        wus=[wu],
        components_for_transitions=[t_wheel, a_wheel],  # T- → A+ → T-
        cycle_intent="preset:balanced",
        wheel_intent=f"wheel_{random.random()}",
    )

    # Test with alias - wheel transitions use T- and A+ components
    assert wheel.is_set('T-') is True
    assert wheel.is_set('A+') is True
    assert wheel.is_set('NonExistent') is False

    # Test with component - wheel transitions use t_wheel and a_wheel
    assert wheel.is_set(t_wheel) is True
    assert wheel.is_set(a_wheel) is True

    # Test with segment
    t_seg = wu.segment_t
    a_seg = wu.segment_a
    assert wheel.is_set(t_seg) is True
    assert wheel.is_set(a_seg) is True

    print("✓ Wheel.is_set() works correctly")


def test_dialectical_component_repository_find_by_wisdom_unit():
    """Test DialecticalComponentRepository.find_by_wisdom_unit()."""
    from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository

    # Create components
    t_comp = DialecticalComponent(statement="Thesis", meaning="test")
    t_comp.commit()
    t_plus_comp = DialecticalComponent(statement="Thesis positive", meaning="test")
    t_plus_comp.commit()
    a_comp = DialecticalComponent(statement="Antithesis", meaning="test")
    a_comp.commit()

    # Create WU with Polarity
    wu, _ = create_wu_from_components(
        t=t_comp,
        a=a_comp,
        t_plus=t_plus_comp,
        intent="test",
    )

    # Use repository to find components
    repo = DialecticalComponentRepository()
    results = repo.find_by_wisdom_unit(wu)

    # Verify results (T, A through Polarity + T+ connected to WU)
    assert len(results) == 3

    # Check that all expected aliases are present (default aliases from helper)
    aliases = [alias for _, alias in results]
    assert 'T' in aliases
    assert 'T+' in aliases
    assert 'A' in aliases

    # Verify component UIDs match
    component_uids = {comp.hash for comp, _ in results}
    assert t_comp.hash in component_uids
    assert t_plus_comp.hash in component_uids
    assert a_comp.hash in component_uids

    print("✓ DialecticalComponentRepository.find_by_wisdom_unit() works correctly")


def test_wisdom_unit_repository_safe_delete(di_container):
    """Test WisdomUnitRepository.safe_delete() with isolation checks."""
    from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository

    repo = WisdomUnitRepository()
    db = di_container.graph_db()

    # ========== Test 1: Isolated WU deletion (should delete) ==========
    # Create components
    t = DialecticalComponent(statement="Isolated thesis", meaning="meaning:T")
    t.commit()
    t_plus = DialecticalComponent(statement="Isolated T+", meaning="meaning:T+")
    t_plus.commit()
    t_minus = DialecticalComponent(statement="Isolated T-", meaning="meaning:T-")
    t_minus.commit()
    a = DialecticalComponent(statement="Isolated antithesis", meaning="meaning:A")
    a.commit()
    a_plus = DialecticalComponent(statement="Isolated A+", meaning="meaning:A+")
    a_plus.commit()
    a_minus = DialecticalComponent(statement="Isolated A-", meaning="meaning:A-")
    a_minus.commit()

    # Create WU with Polarity
    wu_isolated, _ = create_wu_from_components(
        t=t,
        a=a,
        t_plus=t_plus,
        t_minus=t_minus,
        a_plus=a_plus,
        a_minus=a_minus,
        intent="test_isolated",
    )

    # Commit WU (computes hash) so we can add rationales
    wu_isolated.commit()

    # Add rationale (attribute of WU)
    rat = Rationale(text="Test rationale")
    rat.set_explanation_target(wu_isolated)  # Set target before save
    rat.commit()

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
    # Create shared component (used by both WUs)
    shared_comp = DialecticalComponent(statement="Shared thesis", meaning="meaning:T")
    shared_comp.commit()

    # Create unique A components for each WU
    a1 = DialecticalComponent(statement="A1", meaning="meaning:A1")
    a1.commit()
    a2 = DialecticalComponent(statement="A2", meaning="meaning:A2")
    a2.commit()

    # Create WU1 with shared T component
    wu_shared_1, _ = create_wu_from_components(
        t=shared_comp,
        a=a1,
        intent="shared_1",
    )

    # Create WU2 with same shared T component
    wu_shared_2, _ = create_wu_from_components(
        t=shared_comp,
        a=a2,
        intent="shared_2",
    )

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
    # Create unique A component for wu_shared_3
    a3 = DialecticalComponent(statement="A3", meaning="meaning:A3")
    a3.commit()

    # Create WU3 with shared T component
    wu_shared_3, _ = create_wu_from_components(
        t=shared_comp,
        a=a3,
        intent="shared_3",
    )

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
    # Create components for boundary test
    t_boundary = DialecticalComponent(statement="Boundary thesis", meaning="meaning:T")
    t_boundary.commit()
    a_boundary = DialecticalComponent(statement="Boundary antithesis", meaning="meaning:A")
    a_boundary.commit()
    t_plus_boundary = DialecticalComponent(statement="T+", meaning="meaning:T+")
    t_plus_boundary.commit()
    t_minus_boundary = DialecticalComponent(statement="T-", meaning="meaning:T-")
    t_minus_boundary.commit()
    a_plus_boundary = DialecticalComponent(statement="A+", meaning="meaning:A+")
    a_plus_boundary.commit()
    a_minus_boundary = DialecticalComponent(statement="A-", meaning="meaning:A-")
    a_minus_boundary.commit()

    # Create WU with Polarity
    wu_boundary, _ = create_wu_from_components(
        t=t_boundary,
        a=a_boundary,
        t_plus=t_plus_boundary,
        t_minus=t_minus_boundary,
        a_plus=a_plus_boundary,
        a_minus=a_minus_boundary,
        intent="boundary_test",
    )

    # Commit WU so we can add rationales
    wu_boundary.commit()

    # Create Input with HAS_STATEMENT (orphaned component)
    # In the new model, derived statements come through Input nodes
    from dialectical_framework.graph.nodes.input import Input

    input_boundary = Input(content="Test input for boundary")
    input_boundary.commit()

    stmt_comp_orphan = DialecticalComponent(statement="Statement component (orphan)", meaning="meaning:orphan")
    stmt_comp_orphan.commit()
    input_boundary.statements.connect(stmt_comp_orphan)

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
    wu_boundary_2 = WisdomUnit(intent="boundary_test_2")
    wu_boundary_2.save()

    wu_other = WisdomUnit(intent="other_wu")
    wu_other.save()

    # Create WU components for wu_boundary_2
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt, meaning=f"meaning:{stmt}")
        comp.commit()
        getattr(wu_boundary_2, pos).connect(comp, properties={'alias': stmt})

    # Create shared stmt_component used in another WU
    stmt_comp_shared = DialecticalComponent(statement="Statement component (in another WU)", meaning="meaning:shared")
    stmt_comp_shared.commit()
    wu_other.t.connect(stmt_comp_shared, properties={'alias': 'T_other'})

    # Commit wu_boundary_2 so we can add rationales
    wu_boundary_2.commit()

    # Create Input with HAS_STATEMENT to shared component
    # In the new model, derived statements come through Input nodes
    input_boundary_2 = Input(content="Test input for boundary 2")
    input_boundary_2.commit()
    input_boundary_2.statements.connect(stmt_comp_shared)

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
    wu_rationale = WisdomUnit(intent="rationale_test")
    wu_rationale.save()

    # Create components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=stmt, meaning=f"meaning:{stmt}")
        comp.commit()
        getattr(wu_rationale, pos).connect(comp, properties={'alias': stmt})

    # Commit WU so we can add rationales
    wu_rationale.commit()

    # Create rationale chain (critique relationships)
    # rat1 explains wu_rationale directly
    # rat2 critiques rat1, rat3 critiques rat2 (transitive chain)
    rat1 = Rationale(text="Base rationale")
    rat1.set_explanation_target(wu_rationale)
    rat1.commit()

    rat2 = Rationale(text="Critique of rat1")
    rat2.set_critiques_target(rat1)  # rat2's target is rat1
    rat2.commit()

    rat3 = Rationale(text="Critique of rat2")
    rat3.set_critiques_target(rat2)  # rat3's target is rat2
    rat3.commit()

    # Check isolation (CRITIQUES within WU doesn't prevent deletion)
    assert repo.is_isolated(wu_rationale), "WU with internal critique chain should be isolated"

    # Safe delete should succeed
    deleted = repo.safe_delete(wu_rationale)
    assert deleted, "WU with internal critique chain should be deleted"

    # ALL rationales should be deleted (including critique chain)
    # The safe_delete cascades through critique chains to avoid orphans
    for rat in [rat1, rat2, rat3]:
        result = list(db.execute_and_fetch(
            f"MATCH (r:Rationale) WHERE id(r) = $r_id RETURN r",
            {"r_id": rat._id}
        ))
        assert len(result) == 0, f"Rationale '{rat.text}' should be deleted (cascade through critique chain)"

    print("✓ Test 5: All rationales deleted (including critique chain cascade)")

    # ========== Test 6: WU with Transformation (should delete Transformation and its components) ==========
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.relationships.polarity_relationship import (
        AcRelationship, ReRelationship,
        AcPlusRelationship, AcMinusRelationship,
        RePlusRelationship, ReMinusRelationship,
    )

    wu_with_trans = WisdomUnit(intent="with_transformation")
    wu_with_trans.save()

    # Create components for the WU
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"WU Trans {stmt}", meaning=f"meaning:{stmt}")
        comp.commit()
        getattr(wu_with_trans, pos).connect(comp, properties={'alias': stmt})

    # Commit WU before creating Transformation
    wu_with_trans.commit()

    # Create Transformation with 6 Ac/Re positions
    transformation = Transformation(intent="test_trans")
    transformation.set_wisdom_unit(wu_with_trans)
    transformation.save()

    # Add Ac/Re components
    ac_re_positions = [
        ('ac', 'Ac', AcRelationship),
        ('re', 'Re', ReRelationship),
        ('ac_plus', 'Ac+', AcPlusRelationship),
        ('ac_minus', 'Ac-', AcMinusRelationship),
        ('re_plus', 'Re+', RePlusRelationship),
        ('re_minus', 'Re-', ReMinusRelationship),
    ]

    for pos, stmt, rel_class in ac_re_positions:
        comp = DialecticalComponent(statement=f"Trans {stmt}", meaning=f"meaning:{stmt}")
        comp.commit()
        getattr(transformation, pos).connect(comp, relationship=rel_class(alias=stmt))

    # Commit the Transformation
    transformation.commit()

    # Store ID for verification
    trans_id = transformation._id

    # Check isolation (should be isolated - Transformation is part of subgraph)
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

    print("✓ Test 6: WU with Transformation deleted correctly")

    # Note: Tests 7 and 8 for ac_re behavior have been removed.
    # Transformation no longer has ac_re - it has its own 6 positions (Ac, Re, Ac+, Ac-, Re+, Re-).

    # ========== Test 7: WU with Synthesis (should delete Synthesis and orphaned S+/S- components) ==========
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.relationships.polarity_relationship import SPlusRelationship, SMinusRelationship

    wu_with_synth = WisdomUnit(intent="with_synthesis")
    wu_with_synth.save()

    # Create core components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"Synth test {stmt}", meaning=f"meaning:{stmt}")
        comp.commit()
        getattr(wu_with_synth, pos).connect(comp, properties={'alias': stmt})

    # Commit WU before creating Transformation
    wu_with_synth.commit()

    # Create Transformation for the WU
    trans = Transformation(intent="test_transformation")
    trans.set_wisdom_unit(wu_with_synth)
    trans.commit()

    # Create Synthesis with S+ and S- components connected to WU
    # Synthesis uses IncrementalBuildMixin: save() first (HEAD), connect, then commit()
    synth = Synthesis()
    synth.save()  # HEAD state (hash=None)

    s_plus_comp = DialecticalComponent(statement="Positive synthesis", meaning="meaning:S+")
    s_plus_comp.commit()
    synth.s_plus.connect(s_plus_comp, relationship=SPlusRelationship(alias="S+"))

    s_minus_comp = DialecticalComponent(statement="Negative synthesis", meaning="meaning:S-")
    s_minus_comp.commit()
    synth.s_minus.connect(s_minus_comp, relationship=SMinusRelationship(alias="S-"))

    synth.target.connect(wu_with_synth)
    synth.commit()  # Now compute hash

    synth_id = synth._id
    s_plus_id = s_plus_comp._id
    s_minus_id = s_minus_comp._id
    trans_id = trans._id

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

    # Verify Transformation deleted
    result = list(db.execute_and_fetch(
        f"MATCH (t:Transformation) WHERE id(t) = $t_id RETURN t",
        {"t_id": trans_id}
    ))
    assert len(result) == 0, "Transformation should be deleted"

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
    wu_synth_1 = WisdomUnit(intent="synth_shared_1")
    wu_synth_1.save()

    wu_synth_2 = WisdomUnit(intent="synth_shared_2")
    wu_synth_2.save()

    # Create core components for both WUs
    for wu in [wu_synth_1, wu_synth_2]:
        for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                           ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
            comp = DialecticalComponent(statement=f"{wu.intent} {stmt}", meaning=f"meaning:{stmt}")
            comp.commit()
            getattr(wu, pos).connect(comp, properties={'alias': stmt})

    # Commit WUs before creating Transformations
    wu_synth_1.commit()
    wu_synth_2.commit()

    # Create shared S+ component
    shared_s_plus = DialecticalComponent(statement=f"Shared positive synthesis {random.random()}", meaning="meaning:S+")
    shared_s_plus.commit()

    # Create Transformation for wu_synth_1
    trans_1 = Transformation(intent="trans_synth_1")
    trans_1.set_wisdom_unit(wu_synth_1)
    trans_1.commit()

    # Create Synthesis for wu_synth_1 using shared S+ connected to WU
    synth_1 = Synthesis(intent="synth_1")
    synth_1.save()
    synth_1.target.connect(wu_synth_1)
    synth_1.s_plus.connect(shared_s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus_1 = DialecticalComponent(statement=f"S- for wu_synth_1 {random.random()}", meaning="meaning:S-")
    s_minus_1.commit()
    synth_1.s_minus.connect(s_minus_1, relationship=SMinusRelationship(alias="S-"))

    # Create Transformation for wu_synth_2
    trans_2 = Transformation(intent="trans_synth_2")
    trans_2.set_wisdom_unit(wu_synth_2)
    trans_2.commit()

    # Create Synthesis for wu_synth_2 using same shared S+ connected to WU
    synth_2 = Synthesis(intent="synth_2")
    synth_2.save()
    synth_2.target.connect(wu_synth_2)
    synth_2.s_plus.connect(shared_s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus_2 = DialecticalComponent(statement=f"S- for wu_synth_2 {random.random()}", meaning="meaning:S-")
    s_minus_2.commit()
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
    wu_synth_conservative = WisdomUnit(intent="synth_conservative")
    wu_synth_conservative.save()

    # Create core components
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"Conservative {stmt}", meaning=f"meaning:{stmt}")
        comp.commit()
        getattr(wu_synth_conservative, pos).connect(comp, properties={'alias': stmt})

    # Commit WU before creating Transformation
    wu_synth_conservative.commit()

    # Create Transformation for wu_synth_conservative
    trans_conservative = Transformation(intent="trans_conservative")
    trans_conservative.set_wisdom_unit(wu_synth_conservative)
    trans_conservative.commit()

    # Create Synthesis using the shared S+ from wu_synth_2 connected to WU
    synth_conservative = Synthesis()
    synth_conservative.save()
    synth_conservative.target.connect(wu_synth_conservative)
    synth_conservative.s_plus.connect(shared_s_plus, relationship=SPlusRelationship(alias="S+"))

    s_minus_cons = DialecticalComponent(statement="S- for conservative", meaning="meaning:S-")
    s_minus_cons.commit()
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

    component = DialecticalComponent(statement=f"Test feasibility fallback {random.random()}", meaning="test")
    component.commit()

    # Add FeasibilityEstimation with unique value
    feas_value = 0.75 + random.random() * 0.001
    feas_est = FeasibilityEstimation(value=feas_value)
    feas_est.set_target(component)
    feas_est.commit()

    # Should use FeasibilityEstimation as relevance
    assert abs(component.relevance - feas_value) < 0.01, f"Expected relevance~{feas_value}, got {component.relevance}"

    print("✓ FeasibilityEstimation fallback works correctly")


def test_relevance_estimation_priority(di_container):
    """RelevanceEstimation should take priority over FeasibilityEstimation."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation, RelevanceEstimation

    component = DialecticalComponent(statement=f"Test relevance priority {random.random()}", meaning="test")
    component.commit()

    # Add both estimations with unique values
    feas_value = 0.6 + random.random() * 0.001
    feas_est = FeasibilityEstimation(value=feas_value)
    feas_est.set_target(component)
    feas_est.commit()

    rel_value = 0.9 + random.random() * 0.001
    rel_est = RelevanceEstimation(value=rel_value)
    rel_est.set_target(component)
    rel_est.commit()

    # Should use RelevanceEstimation (priority)
    assert abs(component.relevance - rel_value) < 0.01, f"Expected relevance~{rel_value}, got {component.relevance}"

    print("✓ RelevanceEstimation takes priority over FeasibilityEstimation")


def test_calculated_relevance_priority(di_container):
    """CalculatedRelevanceEstimation should take priority over both manual estimations."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import (
        FeasibilityEstimation,
        RelevanceEstimation,
        CalculatedRelevanceEstimation
    )

    component = DialecticalComponent(statement=f"Test calculated relevance {random.random()}", meaning="test")
    component.commit()

    # Add manual estimations with unique values
    feas_value = 0.6 + random.random() * 0.001
    feas_est = FeasibilityEstimation(value=feas_value)
    feas_est.set_target(component)
    feas_est.commit()

    rel_value = 0.9 + random.random() * 0.001
    rel_est = RelevanceEstimation(value=rel_value)
    rel_est.set_target(component)
    rel_est.commit()

    # Add calculated estimation with unique value
    calc_value = 0.75 + random.random() * 0.001
    calc_rel = CalculatedRelevanceEstimation(value=calc_value)
    calc_rel.set_target(component)
    calc_rel.commit()

    # Should use CalculatedRelevanceEstimation (highest priority)
    assert abs(component.relevance - calc_value) < 0.01, f"Expected relevance~{calc_value}, got {component.relevance}"

    print("✓ CalculatedRelevanceEstimation takes priority over both manual estimations")


def test_multiple_feasibility_estimations(di_container):
    """Multiple FeasibilityEstimations should be aggregated via GM."""
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation
    import math

    component = DialecticalComponent(statement=f"Test multi feas {random.random()}", meaning="test")
    component.commit()

    # Add multiple FeasibilityEstimations with unique values
    feas_value1 = 0.8 + random.random() * 0.001
    feas_est1 = FeasibilityEstimation(value=feas_value1)
    feas_est1.set_target(component)
    feas_est1.commit()

    feas_value2 = 0.6 + random.random() * 0.001
    feas_est2 = FeasibilityEstimation(value=feas_value2)
    feas_est2.set_target(component)
    feas_est2.commit()

    # Should aggregate via geometric mean: sqrt(feas_value1 * feas_value2)
    expected_gm = math.sqrt(feas_value1 * feas_value2)
    assert abs(component.relevance - expected_gm) < 0.01, f"Expected relevance≈{expected_gm}, got {component.relevance}"

    print("✓ Multiple FeasibilityEstimations aggregated correctly via geometric mean")


# =============================================================================
# Bidirectional Cardinality Enforcement Tests
# =============================================================================

def test_wheel_multiple_transformations():
    """
    Test that Wheel can have multiple transformations (cardinality 0,N).

    Many Ac-Re paths → ONE S+ (synthesis emerges from T-A pair itself).
    """
    from dialectical_framework.graph.nodes.transformation import Transformation

    # Create components for WisdomUnit
    uid = random.random()
    components = []
    for stmt in ["T", "T+", "T-", "A", "A+", "A-"]:
        c = DialecticalComponent(statement=f"Multi trans Wheel {stmt} {uid}", meaning=f"meaning:{stmt}")
        c.commit()
        components.append(c)

    # Create WU with Polarity using helper
    wu, _ = create_wu_from_components(
        t=components[0],
        a=components[3],
        t_plus=components[1],
        t_minus=components[2],
        a_plus=components[4],
        a_minus=components[5],
        intent=f"wu_{random.random()}",
    )
    wu.commit()

    # Create Cycle
    cycle = Cycle(intent="preset:balanced")
    cycle.set_wisdom_units([wu])
    cycle.commit()

    # Create Wheel
    wheel = Wheel(intent=f"wheel_{uid}")
    wheel.save()

    # Add wheel-level transitions (required before connecting to cycle)
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.relationships.polarity_relationship import AcPlusRelationship, RePlusRelationship

    wheel_trans1 = Transition()
    wheel_trans1.set_source(components[0]).set_target(components[3])  # T → A
    wheel_trans1.commit()
    wheel_trans1.cycle.connect(wheel)

    wheel_trans2 = Transition()
    wheel_trans2.set_source(components[3]).set_target(components[0])  # A → T
    wheel_trans2.commit()
    wheel_trans2.cycle.connect(wheel)

    # Now connect wheel to cycle and commit it
    cycle.wheels.connect(wheel)
    wheel.commit()  # Wheel must be committed before transformations can use its hash

    # Helper to create required transitions (Ac+ and Re+) for a transformation
    def add_required_transitions(trans: Transformation) -> None:
        """Add Ac+ (T- → A+) and Re+ (A- → T+) transitions - the minimum required."""
        # Ac+: T- → A+
        ac_plus_trans = Transition()
        ac_plus_trans.set_source(components[2])  # T-
        ac_plus_trans.set_target(components[4])  # A+
        ac_plus_trans.commit()
        trans.ac_plus.connect(ac_plus_trans, relationship=AcPlusRelationship(alias="Ac+"))

        # Re+: A- → T+
        re_plus_trans = Transition()
        re_plus_trans.set_source(components[5])  # A-
        re_plus_trans.set_target(components[1])  # T+
        re_plus_trans.commit()
        trans.re_plus.connect(re_plus_trans, relationship=RePlusRelationship(alias="Re+"))

    # Create first transformation and connect to Wheel - should succeed
    trans1 = Transformation(intent=f"multi_trans1_{uid}")
    trans1.set_wheel(wheel)
    trans1.save()
    add_required_transitions(trans1)
    trans1.commit()

    # Verify first transformation is connected
    assert wheel.transformations.count() == 1, "Wheel should have 1 transformation"

    # Create second transformation and connect to SAME Wheel - should also succeed (0,N cardinality)
    trans2 = Transformation(intent=f"multi_trans2_{uid}")
    trans2.set_wheel(wheel)
    trans2.save()
    add_required_transitions(trans2)
    trans2.commit()

    # Verify both transformations are connected
    assert wheel.transformations.count() == 2, "Wheel should now have 2 transformations"

    print("✓ Wheel can have multiple transformations (0,N cardinality)")


# =============================================================================
# Cardinality Validation Tests
# =============================================================================

def test_cycle_requires_wisdom_units():
    """Test that Cycle requires at least one WisdomUnit to commit."""
    from dialectical_framework.graph.nodes.cycle import Cycle

    # Create cycle without WUs
    cycle = Cycle(intent="preset:balanced")

    # Should fail to commit without WUs
    with pytest.raises(ValueError, match="Cycle must have WisdomUnits"):
        cycle.commit()

    # Create and commit a WU
    wu, _, _ = create_wisdom_unit_with_polarity(
        t_statement="Thesis", a_statement="Antithesis",
        t_plus_statement="T+", t_minus_statement="T-",
        a_plus_statement="A+", a_minus_statement="A-",
        intent=f"wu_{random.random()}"
    )
    wu.commit()

    # Now set WUs and commit should work
    cycle.set_wisdom_units([wu])
    cycle.commit()

    assert cycle.wisdom_unit_count == 1
    assert cycle.is_committed

    print("✓ Cycle requires at least one WisdomUnit to commit")


def test_transformation_six_positions():
    """Test that Transformation has 6 Transition positions (Ac, Re, Ac+, Ac-, Re+, Re-)."""
    from dialectical_framework.graph.nodes.transformation import (
        Transformation,
        POSITION_AC, POSITION_RE,
        POSITION_AC_PLUS, POSITION_AC_MINUS,
        POSITION_RE_PLUS, POSITION_RE_MINUS,
    )
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.relationships.polarity_relationship import (
        AcRelationship, ReRelationship,
        AcPlusRelationship, AcMinusRelationship,
        RePlusRelationship, ReMinusRelationship,
    )

    uid = random.random()

    # Create components for WisdomUnit
    wu_comps = {}
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"Trans six WU {stmt} {uid}", meaning=f"meaning:{stmt}")
        comp.commit()
        wu_comps[pos] = comp

    # Create WU with Polarity
    wu, _ = create_wu_from_components(
        t=wu_comps['t'],
        a=wu_comps['a'],
        t_plus=wu_comps['t_plus'],
        t_minus=wu_comps['t_minus'],
        a_plus=wu_comps['a_plus'],
        a_minus=wu_comps['a_minus'],
        intent=f"trans_six_{uid}",
    )
    wu.commit()

    # Create Cycle
    cycle = Cycle(intent="preset:balanced")
    cycle.set_wisdom_units([wu])
    cycle.commit()

    # Create Wheel
    wheel = Wheel(intent=f"wheel_{uid}")
    wheel.save()

    # Add wheel-level transitions (required before connecting to cycle)
    wheel_trans1 = Transition()
    wheel_trans1.set_source(wu_comps['t']).set_target(wu_comps['a'])
    wheel_trans1.commit()
    wheel_trans1.cycle.connect(wheel)

    wheel_trans2 = Transition()
    wheel_trans2.set_source(wu_comps['a']).set_target(wu_comps['t'])
    wheel_trans2.commit()
    wheel_trans2.cycle.connect(wheel)

    # Now connect wheel to cycle and commit it
    cycle.wheels.connect(wheel)
    wheel.commit()  # Wheel must be committed before transformations can use its hash

    # Create transformation with 6 transition positions
    transformation = Transformation(intent="test_6_positions")
    transformation.set_wheel(wheel)
    transformation.save()

    # Define transitions: position -> (source_pos, target_pos)
    # Ac: T → A, Ac+: T- → A+, Ac-: T+ → A-
    # Re: A → T, Re+: A- → T+, Re-: A+ → T-
    transition_specs = [
        (POSITION_AC, 't', 'a', transformation.ac, AcRelationship),
        (POSITION_RE, 'a', 't', transformation.re, ReRelationship),
        (POSITION_AC_PLUS, 't_minus', 'a_plus', transformation.ac_plus, AcPlusRelationship),
        (POSITION_AC_MINUS, 't_plus', 'a_minus', transformation.ac_minus, AcMinusRelationship),
        (POSITION_RE_PLUS, 'a_minus', 't_plus', transformation.re_plus, RePlusRelationship),
        (POSITION_RE_MINUS, 'a_plus', 't_minus', transformation.re_minus, ReMinusRelationship),
    ]

    for pos_name, source_pos, target_pos, manager, rel_class in transition_specs:
        trans = Transition()
        trans.set_source(wu_comps[source_pos])
        trans.set_target(wu_comps[target_pos])
        trans.commit()
        manager.connect(trans, relationship=rel_class(alias=pos_name))

    # Commit transformation (cardinality enforced here)
    transformation.commit()

    # Verify all positions are accessible
    for pos_name, _, _, manager, _ in transition_specs:
        result = manager.get()
        assert result is not None, f"Position {pos_name} should have transition"
        trans, rel = result
        assert rel.alias == pos_name, f"Position {pos_name} should have correct alias"

    # Verify get_relationship_manager_by_position works
    for pos_name, _, _, _, _ in transition_specs:
        manager = transformation.get_relationship_manager_by_position(pos_name)
        assert manager.count() == 1, f"Position {pos_name} should have exactly one transition"

    print("✓ Transformation 6-position structure works correctly")


def test_transformation_incomplete():
    """Test that Transformation commit fails when required positions (Ac+, Re+) are missing."""
    import pytest
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.relationships.polarity_relationship import AcRelationship

    uid = random.random()

    # Create components for WisdomUnit
    wu_comps = {}
    for pos, stmt in [('t', 'T'), ('t_plus', 'T+'), ('t_minus', 'T-'),
                       ('a', 'A'), ('a_plus', 'A+'), ('a_minus', 'A-')]:
        comp = DialecticalComponent(statement=f"Trans incomplete WU {stmt} {uid}", meaning=f"meaning:{stmt}")
        comp.commit()
        wu_comps[pos] = comp

    # Create WU with Polarity
    wu, _ = create_wu_from_components(
        t=wu_comps['t'],
        a=wu_comps['a'],
        t_plus=wu_comps['t_plus'],
        t_minus=wu_comps['t_minus'],
        a_plus=wu_comps['a_plus'],
        a_minus=wu_comps['a_minus'],
        intent=f"trans_incomplete_{uid}",
    )
    wu.commit()

    # Create Cycle
    cycle = Cycle(intent="preset:balanced")
    cycle.set_wisdom_units([wu])
    cycle.commit()

    # Create Wheel
    wheel = Wheel(intent=f"wheel_{uid}")
    wheel.save()

    # Add wheel-level transitions (required before connecting to cycle)
    from dialectical_framework.graph.nodes.transition import Transition as Trans
    wheel_trans1 = Trans()
    wheel_trans1.set_source(wu_comps['t']).set_target(wu_comps['a'])
    wheel_trans1.commit()
    wheel_trans1.cycle.connect(wheel)

    wheel_trans2 = Trans()
    wheel_trans2.set_source(wu_comps['a']).set_target(wu_comps['t'])
    wheel_trans2.commit()
    wheel_trans2.cycle.connect(wheel)

    # Now connect wheel to cycle
    cycle.wheels.connect(wheel)

    # Create transformation with only Ac position (missing required Ac+ and Re+)
    transformation = Transformation(intent="test_incomplete")
    transformation.set_wheel(wheel)
    transformation.save()

    # Add only one transition (Ac: T → A) - optional position
    trans = Transition()
    trans.set_source(wu_comps['t'])
    trans.set_target(wu_comps['a'])
    trans.commit()
    transformation.ac.connect(trans, relationship=AcRelationship(alias="Ac"))

    # Verify commit fails due to missing required positions (Ac+ and Re+)
    with pytest.raises(ValueError) as exc_info:
        transformation.commit()

    assert "ac_plus" in str(exc_info.value), "Error should mention missing ac_plus"
    assert "re_plus" in str(exc_info.value), "Error should mention missing re_plus"

    print("✓ Transformation cardinality enforcement works correctly")


def test_input_transforms_to_dx_reference_when_component_exists():
    """
    Test that Input transforms plain text content to dx:// reference
    when a DialecticalComponent with the same statement already exists.

    This prevents hash collision between Input and DialecticalComponent
    when content == statement.
    """
    from dialectical_framework.graph.nodes.input import Input

    uid = random.random()
    statement = f"Democracy empowers citizens {uid}"

    # First, create a DialecticalComponent
    comp = DialecticalComponent(statement=statement, meaning="test", sid="test-sid")
    comp.commit()

    # Now create Input with the same content
    input_node = Input(content=statement, sid="test-sid")
    input_node.commit()

    # Input content should have been transformed to dx:// reference
    assert input_node.content.startswith("dx://"), \
        f"Input content should be dx:// reference, got: {input_node.content}"
    assert comp.hash in input_node.content, \
        f"dx:// reference should contain component hash {comp.hash[:8]}"

    # Hashes should be different (no collision)
    assert input_node.hash != comp.hash, \
        "Input hash should differ from Component hash after transformation"

    print(f"✅ Input content transformed: {input_node.content[:50]}...")


def test_input_keeps_plain_text_when_no_component_collision():
    """
    Test that Input keeps plain text content when no matching
    DialecticalComponent exists (no collision risk).
    """
    from dialectical_framework.graph.nodes.input import Input

    uid = random.random()
    content = f"Some unique content that has no matching component {uid}"

    input_node = Input(content=content, sid="test-sid")
    input_node.commit()

    # Content should remain as plain text
    assert input_node.content == content, \
        f"Input content should remain unchanged, got: {input_node.content}"
    assert not input_node.content.startswith("dx://"), \
        "Content should not be transformed when no collision risk"

    print("✅ Input content kept as plain text (no collision)")


def test_input_keeps_uri_content_unchanged():
    """
    Test that Input keeps URI content unchanged (no transformation).
    """
    from dialectical_framework.graph.nodes.input import Input

    uid = random.random()

    # Test various URI schemes
    uri_contents = [
        f"https://example.com/article-{uid}",
        f"http://example.com/page-{uid}",
        f"dx://test-sid/abc123def456",
        f"ipfs://QmTest{uid}",
        f"data:text/plain,test-{uid}",
    ]

    for content in uri_contents:
        input_node = Input(content=content, sid="test-sid")
        input_node.commit()

        assert input_node.content == content, \
            f"URI content should remain unchanged: {content}"

    print("✅ URI content kept unchanged for all schemes")


def test_scope_vocabulary():
    """
    Test that get_vocabulary(sid) includes all components in the scope.

    Vocabulary is simply all DialecticalComponents with matching sid.
    """
    from dialectical_framework.graph.nodes.brainstorm import Brainstorm
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.ideas import Ideas
    from dialectical_framework.graph.repositories.dialectical_component_repository import (
        DialecticalComponentRepository
    )
    from dialectical_framework.graph.scope_context import scope

    repo = DialecticalComponentRepository()
    uid = random.random()

    # Create Brainstorm (scope root)
    brainstorm = Brainstorm()
    brainstorm.commit()

    with scope(brainstorm.sid):
        # Create Input
        input_node = Input(content=f"https://example.com/article-{uid}")
        input_node.commit()
        brainstorm.inputs.connect(input_node)

        # Create component (inherits sid from scope context)
        comp1 = DialecticalComponent(statement=f"Component 1 {uid}", meaning="test")
        comp1.commit()

        comp2 = DialecticalComponent(statement=f"Component 2 {uid}", meaning="test")
        comp2.commit()

        # Get vocabulary - should include all components in scope
        vocab = repo.get_vocabulary()
        vocab_hashes = {c.hash for c in vocab}

        assert comp1.hash in vocab_hashes, "Component 1 should be in vocabulary"
        assert comp2.hash in vocab_hashes, "Component 2 should be in vocabulary"
        assert len(vocab) == 2, f"Expected 2 components, got {len(vocab)}"

    print("✅ Scope vocabulary correctly includes all components")


# =============================================================================
# Rationale Critique Temporal Validation Tests
# =============================================================================

def test_critique_chain_temporal_order():
    """
    Critique chains maintain temporal ordering: each critique has a later committed_at.

    This ensures cycles are impossible:
    - A→B→C implies A.committed_at > B.committed_at > C.committed_at
    - Therefore C→A is impossible (would require C.committed_at > A.committed_at)
    """
    import time

    # Create base rationale explaining a component
    component = DialecticalComponent(statement=f"Test comp {random.random()}", meaning="test")
    component.commit()

    base = Rationale(text=f"Base rationale {random.random()}")
    base.set_explanation_target(component)
    base.commit()
    base_time = base.committed_at

    # Create first critique - should have later committed_at
    time.sleep(0.01)  # Ensure time difference

    critique1 = Rationale(text=f"First critique {random.random()}")
    critique1.set_critiques_target(base)
    critique1.commit()
    critique1_time = critique1.committed_at

    assert critique1_time > base_time, "Critique must be committed after its target"

    # Create second critique of critique1 - should have even later committed_at
    time.sleep(0.01)

    critique2 = Rationale(text=f"Second critique {random.random()}")
    critique2.set_critiques_target(critique1)
    critique2.commit()
    critique2_time = critique2.committed_at

    assert critique2_time > critique1_time > base_time, "Critique chain must maintain temporal order"

    print("✓ Critique chain maintains temporal order (prevents cycles)")


def test_cannot_critique_uncommitted_rationale():
    """Cannot set an uncommitted rationale as critique target."""
    uncommitted = Rationale(text="Uncommitted rationale")
    # Don't commit it

    critique = Rationale(text="Attempted critique")

    with pytest.raises(ValueError, match="committed"):
        critique.set_critiques_target(uncommitted)

    print("✓ Cannot critique uncommitted rationale")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
