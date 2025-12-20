"""
Test graph structures with Memgraph.

This test demonstrates creating a simple WisdomUnit with dialectical components
and verifying the relationships work correctly.

To run these tests, start Memgraph first:
    docker-compose -f docker-compose.test.yml up -d

Then run:
    poetry run pytest tests/test_graph.py -v
"""

import pytest

from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


def test_create_simple_wisdom_unit(db):
    """Test creating a WisdomUnit with basic components."""

    # Create a wisdom unit
    wu = WisdomUnit(index=1, reasoning_mode="dialectical")
    db.save_node(wu)

    # Create thesis components
    t = DialecticalComponent(statement="Democracy empowers citizens")
    t_plus = DialecticalComponent(statement="Democracy promotes equality")
    t_minus = DialecticalComponent(statement="Democracy can be inefficient")

    db.save_node(t)
    db.save_node(t_plus)
    db.save_node(t_minus)

    # Create antithesis components
    a = DialecticalComponent(statement="Authority provides order")
    a_plus = DialecticalComponent(statement="Authority ensures security")
    a_minus = DialecticalComponent(statement="Authority restricts freedom")

    db.save_node(a)
    db.save_node(a_plus)
    db.save_node(a_minus)

    # Connect components to wisdom unit
    wu.t.connect(t, db=db)
    wu.t_plus.connect(t_plus, db=db)
    wu.t_minus.connect(t_minus, db=db)

    wu.a.connect(a, db=db)
    wu.a_plus.connect(a_plus, db=db)
    wu.a_minus.connect(a_minus, db=db)

    # Verify connections
    t_component = wu.t.get(db=db)
    assert t_component is not None
    assert t_component[0].statement == "Democracy empowers citizens"

    a_component = wu.a.get(db=db)
    assert a_component is not None
    assert a_component[0].statement == "Authority provides order"

    # Verify cardinality
    assert wu.t.count(db=db) == 1
    assert wu.t_plus.count(db=db) == 1
    assert wu.t_minus.count(db=db) == 1
    assert wu.a.count(db=db) == 1
    assert wu.a_plus.count(db=db) == 1
    assert wu.a_minus.count(db=db) == 1

    # Verify summary
    summary = wu.get_component_summary(db=db)
    assert summary['t'] == 1
    assert summary['t_plus'] == 1
    assert summary['t_minus'] == 1
    assert summary['a'] == 1
    assert summary['a_plus'] == 1
    assert summary['a_minus'] == 1

    print("✓ Successfully created WisdomUnit with all required components")


def test_wisdom_unit_validation(db):
    """Test WisdomUnit cardinality validation."""

    # Create incomplete wisdom unit
    wu = WisdomUnit(index=2)
    db.save_node(wu)

    # Add only T component
    t = DialecticalComponent(statement="Test thesis")
    db.save_node(t)
    wu.t.connect(t, db=db)

    # Validate - should fail (missing other required components)
    is_valid, errors = wu.validate_cardinality(db=db)
    assert not is_valid
    assert len(errors) > 0

    print(f"✓ Validation correctly detected missing components: {len(errors)} errors")


def test_component_aliases(db):
    """Test getting components with their aliases."""

    wu = WisdomUnit(index=3)
    db.save_node(wu)

    # Add components
    t = DialecticalComponent(statement="Thesis 3")
    a = DialecticalComponent(statement="Antithesis 3")

    db.save_node(t)
    db.save_node(a)

    wu.t.connect(t, db=db)
    wu.a.connect(a, db=db)

    # Get component alias
    t_alias = wu.get_component_alias("T")
    assert t_alias == "T3"

    a_alias = wu.get_component_alias("A")
    assert a_alias == "A3"

    print(f"✓ Component aliases generated correctly: {t_alias}, {a_alias}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
