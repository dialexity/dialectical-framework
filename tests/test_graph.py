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

from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


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

    # Connect components to wisdom unit (no db parameter!)
    wu.t.connect(t)
    wu.t_plus.connect(t_plus)
    wu.t_minus.connect(t_minus)

    wu.a.connect(a)
    wu.a_plus.connect(a_plus)
    wu.a_minus.connect(a_minus)

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
    wu = WisdomUnit(index=2)
    wu.save()

    # Add only T component
    t = DialecticalComponent(statement="Test thesis")
    t.save()
    wu.t.connect(t)  # No db parameter

    # Validate - should fail (missing other required components)
    is_valid, errors = wu.validate_cardinality()  # No db parameter
    assert not is_valid
    assert len(errors) > 0

    print(f"✓ Validation correctly detected missing components: {len(errors)} errors")


def test_component_aliases():
    """Test getting components with their aliases."""

    wu = WisdomUnit(index=3)
    wu.save()

    # Add components
    t = DialecticalComponent(statement="Thesis 3")
    a = DialecticalComponent(statement="Antithesis 3")

    t.save()
    a.save()

    wu.t.connect(t)  # No db parameter
    wu.a.connect(a)  # No db parameter

    # Get component alias
    t_alias = wu.get_component_alias("T")
    assert t_alias == "T3"

    a_alias = wu.get_component_alias("A")
    assert a_alias == "A3"

    print(f"✓ Component aliases generated correctly: {t_alias}, {a_alias}")


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
