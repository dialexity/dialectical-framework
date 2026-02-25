"""Tests for RunReport."""

import pytest

from dialectical_framework.agents.run_report import (
    Effect,
    NodeRef,
    RelationshipRef,
    RunReport,
    _resolve_rel_type,
)


class MockNode:
    """Minimal mock for testing."""

    def __init__(self, label: str, hash: str, statement: str = ""):
        self._label = label
        self.hash = hash
        self.statement = statement

    def __class__(self):
        pass


# Patch __class__.__name__ for MockNode
MockNode.__name__ = "MockNode"


def test_run_report_node_created():
    report = RunReport(tool="test_tool")

    # Create a mock node
    node = MockNode("DialecticalComponent", "abc123", "Test statement")
    node.__class__ = type("DialecticalComponent", (), {})

    report.node_created(node)

    assert len(report.effects) == 1
    effect = report.effects[0]
    assert effect.seq == 0
    assert effect.effect_type == "node_created"
    assert effect.node.hash == "abc123"
    assert effect.patch["statement"] == "Test statement"


def test_run_report_sequencing():
    report = RunReport(tool="test_tool")

    node1 = MockNode("A", "hash1", "First")
    node1.__class__ = type("A", (), {})
    node2 = MockNode("B", "hash2", "Second")
    node2.__class__ = type("B", (), {})

    report.node_created(node1)
    report.node_created(node2)

    assert report.effects[0].seq == 0
    assert report.effects[1].seq == 1


def test_run_report_relationship_created():
    report = RunReport(tool="test_tool")

    node1 = MockNode("A", "hash1")
    node1.__class__ = type("A", (), {})
    node2 = MockNode("B", "hash2")
    node2.__class__ = type("B", (), {})

    report.relationship_created("OPPOSITE_OF", node1, node2)

    assert len(report.effects) == 1
    effect = report.effects[0]
    assert effect.effect_type == "relationship_created"
    assert effect.relationship.type == "OPPOSITE_OF"
    assert effect.relationship.from_node.hash == "hash1"
    assert effect.relationship.to_node.hash == "hash2"


def test_run_report_merge():
    report1 = RunReport(tool="tool1", summary="First tool")
    report2 = RunReport(tool="tool2", summary="Second tool")

    node1 = MockNode("A", "hash1")
    node1.__class__ = type("A", (), {})
    node2 = MockNode("B", "hash2")
    node2.__class__ = type("B", (), {})

    report1.node_created(node1)
    report2.node_created(node2)

    report1.artifacts["key1"] = "value1"
    report2.artifacts["key2"] = "value2"

    merged = report1.merge(report2)

    assert len(merged.effects) == 2
    assert merged.effects[0].seq == 0
    assert merged.effects[1].seq == 1
    assert "First tool" in merged.summary
    assert "Second tool" in merged.summary
    assert merged.artifacts["key1"] == "value1"
    assert merged.artifacts["key2"] == "value2"


def test_run_report_artifacts():
    report = RunReport(tool="extract_antitheses")

    report.artifacts["antithesis_hashes"] = ["hash1", "hash2"]
    report.artifacts["hs_by_hash"] = {"hash1": 0.8, "hash2": 0.6}

    assert report.artifacts["antithesis_hashes"] == ["hash1", "hash2"]
    assert report.artifacts["hs_by_hash"]["hash1"] == 0.8


# --- Tests for _resolve_rel_type ---


def test_resolve_rel_type_string():
    assert _resolve_rel_type("OPPOSITE_OF") == "OPPOSITE_OF"


def test_resolve_rel_type_relationship_manager():
    """Test with an object that has .relationship_type attribute."""
    class MockRelationshipManager:
        relationship_type = "BELONGS_TO"

    manager = MockRelationshipManager()
    assert _resolve_rel_type(manager) == "BELONGS_TO"


def test_resolve_rel_type_relationship_class():
    """Test with a class that has .type attribute (like GQLAlchemy relationships)."""
    class MockRelationshipClass:
        type = "LINKS_TO"

    assert _resolve_rel_type(MockRelationshipClass) == "LINKS_TO"


def test_resolve_rel_type_invalid():
    """Test with an unsupported type."""
    with pytest.raises(ValueError, match="Cannot resolve relationship type"):
        _resolve_rel_type(12345)


def test_run_report_relationship_with_manager():
    """Test relationship methods accept relationship manager-like objects."""
    report = RunReport(tool="test_tool")

    class MockRelManager:
        relationship_type = "CUSTOM_REL"

    node1 = MockNode("A", "hash1")
    node1.__class__ = type("A", (), {})
    node2 = MockNode("B", "hash2")
    node2.__class__ = type("B", (), {})

    report.relationship_created(MockRelManager(), node1, node2)

    assert len(report.effects) == 1
    assert report.effects[0].relationship.type == "CUSTOM_REL"
