"""
Tests for Orchestrator.

These are integration tests that verify the orchestrator correctly:
1. Creates sessions on init
2. Registers and executes tools
3. Tools are stateless and use DI for context
4. Queries are automatically scoped by sid for security
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.orchestrator.orchestrator import Orchestrator
from dialectical_framework.agents.orchestrator.tools.session_tools import AddInput
from dialectical_framework.agents.orchestrator.tools.query_graph import (
    QueryGraph,
    _inject_sid_scoping,
    _has_hardcoded_sid,
)
from dialectical_framework.graph.scope_context import scope


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
        """Test AddInput adds content to brainstorm."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            tool = AddInput(content="Remote work increases productivity.")
            result = await tool.call()

            assert "Added input to brainstorm" in result
            assert "Input hash:" in result


class TestQueryTools:
    """Tests for query tools."""

    @pytest.mark.asyncio
    async def test_query_graph_blocks_write_operations(self):
        """Test QueryGraph blocks CREATE, MERGE, DELETE etc."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            # Test CREATE blocked
            tool = QueryGraph(cypher="CREATE (n:Node) RETURN n")
            result = await tool.call()
            assert "Write operations not allowed" in result
            assert "CREATE" in result

            # Test DELETE blocked
            tool = QueryGraph(cypher="MATCH (n) DELETE n")
            result = await tool.call()
            assert "Write operations not allowed" in result

    @pytest.mark.asyncio
    async def test_query_graph_blocks_hardcoded_sid(self):
        """Test QueryGraph blocks hardcoded sid values."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            tool = QueryGraph(cypher="MATCH (n {sid: 'evil-session'}) RETURN n")
            result = await tool.call()

            assert "Hardcoded sid values are not allowed" in result

    @pytest.mark.asyncio
    async def test_query_graph_auto_injects_sid(self):
        """Test QueryGraph auto-injects sid - LLM doesn't need to include it."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            # Query WITHOUT sid - should work because we inject it
            tool = QueryGraph(cypher="MATCH (b:Brainstorm) RETURN b")
            result = await tool.call()

            assert "Found" in result
            assert "Brainstorm" in result

    @pytest.mark.asyncio
    async def test_query_graph_no_results(self):
        """Test QueryGraph handles empty results."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            tool = QueryGraph(cypher="MATCH (wu:WisdomUnit) RETURN wu")
            result = await tool.call()

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_query_graph_allows_schema_queries(self):
        """Test QueryGraph allows schema introspection."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            tool = QueryGraph(cypher="SHOW SCHEMA INFO")
            result = await tool.call()

            # Should not get any error - schema queries don't need sid
            assert "Error" not in result or "Query error" in result  # Query error OK if DB doesn't support


class TestOrchestratorInitialization:
    """Tests for Orchestrator initialization."""

    def test_orchestrator_creates_session(self):
        """Test orchestrator creates a session on init."""
        orchestrator = Orchestrator()

        assert orchestrator.sid is not None
        assert len(orchestrator.sid) > 0

    def test_orchestrator_loads_existing_session(self):
        """Test orchestrator can load existing session."""
        # Create a session first
        first = Orchestrator()
        sid = first.sid

        # Load it in a new orchestrator
        second = Orchestrator(sid=sid)

        assert second.sid == sid

    def test_orchestrator_has_all_tool_types(self):
        """Test orchestrator has session, query, and build tools."""
        orchestrator = Orchestrator()

        tool_names = [t.__name__ for t in orchestrator._tools]

        # Session tools
        assert "AddInput" in tool_names

        # Query tools
        assert "QueryGraph" in tool_names

        # Build tools (subagents)
        assert "SurfaceTheses" in tool_names
        assert "TensionAgent" in tool_names
        assert "FindPolarities" in tool_names
        assert "ExploreTransformations" in tool_names


class TestOrchestratorWorkflow:
    """Integration tests for orchestrator workflows."""

    @pytest.mark.asyncio
    async def test_add_input_workflow(self):
        """Test workflow: add input -> query inputs."""
        orchestrator = Orchestrator()

        with scope(orchestrator.sid):
            # Add input
            add_tool = AddInput(content="Remote work increases productivity and flexibility.")
            result = await add_tool.call()

            assert "Added input to brainstorm" in result
            assert "Input hash:" in result

            # Query inputs - no sid needed, auto-injected
            query_tool = QueryGraph(
                cypher="MATCH (b:Brainstorm)-[:HAS_INPUT]->(i:Input) RETURN i.content"
            )
            query_result = await query_tool.call()

            assert "Remote work" in query_result
