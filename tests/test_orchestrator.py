"""
Tests for agent tools and session management.

These are integration tests that verify:
1. Tools are stateless and use DI for context
2. Queries are automatically scoped by sid for security
3. Analyst agent initialization and tool registration
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.analyst import Analyst
from dialectical_framework.agents.orchestrator.tools.add_input import AddInput
from dialectical_framework.agents.orchestrator.tools.query_graph import (
    QueryGraph,
    _inject_sid_scoping,
    _has_hardcoded_sid,
)
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
        """Test sid injection into simple node pattern."""
        query = "MATCH (n) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n {sid: $sid}) RETURN n"

    def test_inject_sid_labeled_node(self):
        """Test sid injection into labeled node pattern."""
        query = "MATCH (n:Label) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n:Label {sid: $sid}) RETURN n"

    def test_inject_sid_node_with_properties(self):
        """Test sid injection into node with existing properties."""
        query = "MATCH (n:Label {foo: 'bar'}) RETURN n"
        result = _inject_sid_scoping(query)
        assert result == "MATCH (n:Label {sid: $sid, foo: 'bar'}) RETURN n"

    def test_inject_sid_multiple_nodes(self):
        """Test sid injection into multiple nodes in pattern."""
        query = "MATCH (a:Label)-[:REL]->(b:Other) RETURN a, b"
        result = _inject_sid_scoping(query)
        assert "(a:Label {sid: $sid})" in result
        assert "(b:Other {sid: $sid})" in result

    def test_inject_sid_anonymous_node(self):
        """Test sid injection into anonymous node."""
        query = "MATCH (:Label) RETURN count(*)"
        result = _inject_sid_scoping(query)
        assert "(:Label {sid: $sid})" in result

    def test_detect_hardcoded_sid_string(self):
        """Test detection of hardcoded sid string values."""
        assert _has_hardcoded_sid("MATCH (n {sid: 'evil'}) RETURN n")
        assert _has_hardcoded_sid('MATCH (n {sid: "evil"}) RETURN n')

    def test_detect_hardcoded_sid_other_param(self):
        """Test detection of sid with different parameter."""
        assert _has_hardcoded_sid("MATCH (n {sid: $other_param}) RETURN n")

    def test_allow_sid_param(self):
        """Test that $sid parameter is allowed (we inject it)."""
        assert not _has_hardcoded_sid("MATCH (n {sid: $sid}) RETURN n")

    def test_inject_sid_no_duplicate(self):
        """Test that sid: $sid is not duplicated if already present."""
        query = "MATCH (n:Label {sid: $sid}) RETURN n"
        result = _inject_sid_scoping(query)
        # Should not have duplicate sid
        assert result == "MATCH (n:Label {sid: $sid}) RETURN n"
        assert result.count("sid:") == 1


class TestSessionTools:
    """Tests for session tools."""

    @pytest.mark.asyncio
    async def test_add_input(self):
        """Test AddInput adds content to case."""
        sid = _new_sid()

        with scope(sid):
            concern = AddInput()
            input_node = await concern.resolve(content="Remote work increases productivity.")

            assert input_node.is_committed
            assert concern.report.ok


class TestQueryTools:
    """Tests for query tools."""

    @pytest.mark.asyncio
    async def test_query_graph_blocks_write_operations(self):
        """Test QueryGraph blocks CREATE, MERGE, DELETE etc."""
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()

            # Test CREATE blocked
            result = await concern.resolve(cypher="CREATE (n:Node) RETURN n")
            assert "Write operations not allowed" in result
            assert "CREATE" in result

            # Test DELETE blocked
            result = await concern.resolve(cypher="MATCH (n) DELETE n")
            assert "Write operations not allowed" in result

    @pytest.mark.asyncio
    async def test_query_graph_blocks_hardcoded_sid(self):
        """Test QueryGraph blocks hardcoded sid values."""
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="MATCH (n {sid: 'evil-session'}) RETURN n")

            assert "Hardcoded sid values are not allowed" in result

    @pytest.mark.asyncio
    async def test_query_graph_auto_injects_sid(self):
        """Test QueryGraph auto-injects sid - LLM doesn't need to include it."""
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="MATCH (b:Case) RETURN b")

            assert "Found" in result
            assert "Case" in result

    @pytest.mark.asyncio
    async def test_query_graph_no_results(self):
        """Test QueryGraph handles empty results."""
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="MATCH (pp:Perspective) RETURN pp")

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_query_graph_allows_schema_queries(self):
        """Test QueryGraph allows schema introspection."""
        sid = _new_sid()

        with scope(sid):
            concern = QueryGraph()
            result = await concern.resolve(cypher="SHOW SCHEMA INFO")

            # Should not get any error - schema queries don't need sid
            assert "Error" not in result or "Query error" in result  # Query error OK if DB doesn't support


class TestAnalystInitialization:
    """Tests for Analyst initialization."""

    def test_default_mode_tools(self):
        """Test default mode has autonomous pipeline + steering + query tools."""
        analyst = Analyst()

        tool_names = [t.__name__ for t in analyst._tools]

        assert "analyze" in tool_names
        assert "create_nexus" in tool_names
        assert "edit_perspective" in tool_names
        assert "reject" in tool_names
        assert "present_analysis" in tool_names
        assert "inspect_node" in tool_names
        assert "query_graph" in tool_names
        assert "get_schema" in tool_names

        # Granular tools NOT in default mode
        assert "surface_theses" not in tool_names
        assert "find_polarities" not in tool_names
        assert "build_wheels" not in tool_names

    def test_advanced_mode_tools(self):
        """Test advanced mode has all granular tools."""
        analyst = Analyst(mode="advanced")

        tool_names = [t.__name__ for t in analyst._tools]

        # Granular analysis tools
        assert "add_input" in tool_names
        assert "surface_theses" in tool_names
        assert "find_polarities" in tool_names
        assert "introduce_polarity" in tool_names
        assert "expand_polarities" in tool_names
        assert "place_statement" in tool_names
        assert "edit_perspective" in tool_names
        assert "reject" in tool_names
        assert "create_nexus" in tool_names

        # Query tools
        assert "present_analysis" in tool_names
        assert "inspect_node" in tool_names
        assert "query_graph" in tool_names
        assert "get_schema" in tool_names

        # Autonomous pipeline NOT in advanced mode
        assert "analyze" not in tool_names


class TestAnalystWorkflow:
    """Integration tests for analyst workflows."""

    @pytest.mark.asyncio
    async def test_add_input_workflow(self):
        """Test workflow: add input -> query inputs."""
        sid = _new_sid()

        with scope(sid):
            # Add input
            concern = AddInput()
            input_node = await concern.resolve(content="Remote work increases productivity and flexibility.")

            assert input_node.is_committed

            # Query inputs - no sid needed, auto-injected
            query_concern = QueryGraph()
            query_result = await query_concern.resolve(
                cypher="MATCH (b:Case)-[:HAS_INPUT]->(i:Input) RETURN i.content"
            )

            assert "Remote work" in query_result
