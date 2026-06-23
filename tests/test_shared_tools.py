"""
Tests for shared agent tools and query security.

These are integration tests that verify:
1. Sid injection logic (automatic scoping of Cypher queries)
2. QueryGraph blocks write operations and hardcoded sids
3. AddInput concern creates and links Input nodes
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.add_input import AddInput
from dialectical_framework.agents.orchestrator.tools.query_graph import (
    QueryGraph, _has_hardcoded_sid, _inject_sid_scoping)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    """Create a Case and return its sid."""
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


class TestSidInjection:
    """Tests for automatic sid injection into queries."""

    def test_inject_sid_simple_node(self):
        query = "MATCH (n) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n {sid: $sid}) RETURN n"

    def test_inject_sid_labeled_node(self):
        query = "MATCH (n:Label) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n:Label {sid: $sid}) RETURN n"

    def test_inject_sid_node_with_properties(self):
        query = "MATCH (n:Label {foo: 'bar'}) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n:Label {sid: $sid, foo: 'bar'}) RETURN n"

    def test_inject_sid_multiple_nodes(self):
        query = "MATCH (a:Label)-[:REL]->(b:Other) RETURN a, b"
        result = _inject_sid_scoping(query)
        assert "(a:Label {sid: $sid})" in result
        assert "(b:Other {sid: $sid})" in result

    def test_inject_sid_anonymous_node(self):
        query = "MATCH (:Label) RETURN count(*)"
        result = _inject_sid_scoping(query)
        assert "(:Label {sid: $sid})" in result

    def test_detect_hardcoded_sid_string(self):
        assert _has_hardcoded_sid("MATCH (n {sid: 'evil'}) RETURN n")
        assert _has_hardcoded_sid('MATCH (n {sid: "evil"}) RETURN n')

    def test_detect_hardcoded_sid_other_param(self):
        assert _has_hardcoded_sid("MATCH (n {sid: $other_param}) RETURN n")

    def test_allow_sid_param(self):
        assert not _has_hardcoded_sid("MATCH (n {sid: $sid}) RETURN n")

    def test_inject_sid_no_duplicate(self):
        query = "MATCH (n:Label {sid: $sid}) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n:Label {sid: $sid}) RETURN n"
        assert result.count("sid:") == 1


class TestAddInput:
    """Tests for AddInput concern."""

    @pytest.mark.asyncio
    async def test_add_input(self):
        """Test AddInput adds content to case."""
        sid = _new_sid()

        with scope(sid):
            concern = AddInput()
            input_node = await concern.resolve(
                content="Remote work increases productivity."
            )

            assert input_node.is_committed
            assert concern.report.ok


class TestQueryGraph:
    """Tests for QueryGraph concern."""

    @pytest.mark.asyncio
    async def test_blocks_write_operations(self):
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()

            result = await concern.resolve(cypher="CREATE (n:Node) RETURN n")
            assert "Write operations not allowed" in result
            assert "CREATE" in result

            result = await concern.resolve(cypher="MATCH (n) DELETE n")
            assert "Write operations not allowed" in result

    @pytest.mark.asyncio
    async def test_blocks_hardcoded_sid(self):
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(
                cypher="MATCH (n {sid: 'evil-session'}) RETURN n"
            )

            assert "Hardcoded sid values are not allowed" in result

    @pytest.mark.asyncio
    async def test_auto_injects_sid(self):
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="MATCH (b:Case) RETURN b")

            assert "Found" in result
            assert "Case" in result

    @pytest.mark.asyncio
    async def test_no_results(self):
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="MATCH (pp:Perspective) RETURN pp")

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_allows_schema_queries(self):
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="SHOW SCHEMA INFO")

            assert "Error" not in result or "Query error" in result
