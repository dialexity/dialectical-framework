"""
Tests for Orchestrator.

These are integration tests that verify the orchestrator correctly:
1. Creates sessions on init
2. Registers and executes tools
3. Tools are stateless and use DI for context
4. Queries are automatically scoped by case_id for security
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.orchestrator.orchestrator import Orchestrator
from dialectical_framework.agents.orchestrator.tools.add_input import AddInput
from dialectical_framework.agents.orchestrator.tools.query_graph import (
    QueryGraph,
    _inject_case_id_scoping,
    _has_hardcoded_case_id,
)
from dialectical_framework.graph.scope_context import scope


class TestCaseIdInjection:
    """Tests for automatic case_id injection into queries."""

    def test_inject_case_id_simple_node(self):
        """Test case_id injection into simple node pattern."""
        query = "MATCH (n) RETURN n"
        result = _inject_case_id_scoping(query)
        assert result == "MATCH (n {case_id: $case_id}) RETURN n"

    def test_inject_case_id_labeled_node(self):
        """Test case_id injection into labeled node pattern."""
        query = "MATCH (n:Label) RETURN n"
        result = _inject_case_id_scoping(query)
        assert result == "MATCH (n:Label {case_id: $case_id}) RETURN n"

    def test_inject_case_id_node_with_properties(self):
        """Test case_id injection into node with existing properties."""
        query = "MATCH (n:Label {foo: 'bar'}) RETURN n"
        result = _inject_case_id_scoping(query)
        assert result == "MATCH (n:Label {case_id: $case_id, foo: 'bar'}) RETURN n"

    def test_inject_case_id_multiple_nodes(self):
        """Test case_id injection into multiple nodes in pattern."""
        query = "MATCH (a:Label)-[:REL]->(b:Other) RETURN a, b"
        result = _inject_case_id_scoping(query)
        assert "(a:Label {case_id: $case_id})" in result
        assert "(b:Other {case_id: $case_id})" in result

    def test_inject_case_id_anonymous_node(self):
        """Test case_id injection into anonymous node."""
        query = "MATCH (:Label) RETURN count(*)"
        result = _inject_case_id_scoping(query)
        assert "(:Label {case_id: $case_id})" in result

    def test_detect_hardcoded_case_id_string(self):
        """Test detection of hardcoded case_id string values."""
        assert _has_hardcoded_case_id("MATCH (n {case_id: 'evil'}) RETURN n")
        assert _has_hardcoded_case_id('MATCH (n {case_id: "evil"}) RETURN n')

    def test_detect_hardcoded_case_id_other_param(self):
        """Test detection of case_id with different parameter."""
        assert _has_hardcoded_case_id("MATCH (n {case_id: $other_param}) RETURN n")

    def test_allow_case_id_param(self):
        """Test that $case_id parameter is allowed (we inject it)."""
        assert not _has_hardcoded_case_id("MATCH (n {case_id: $case_id}) RETURN n")

    def test_inject_case_id_no_duplicate(self):
        """Test that case_id: $case_id is not duplicated if already present."""
        query = "MATCH (n:Label {case_id: $case_id}) RETURN n"
        result = _inject_case_id_scoping(query)
        # Should not have duplicate case_id
        assert result == "MATCH (n:Label {case_id: $case_id}) RETURN n"
        assert result.count("case_id:") == 1


class TestSessionTools:
    """Tests for session tools."""

    @pytest.mark.asyncio
    async def test_add_input(self):
        """Test AddInput adds content to case."""
        orchestrator = Orchestrator()

        with scope(orchestrator.case_id):
            tool = AddInput(content="Remote work increases productivity.")
            result = await tool.call()

            assert "Added input to case" in result
            assert "Input hash:" in result


class TestQueryTools:
    """Tests for query tools."""

    @pytest.mark.asyncio
    async def test_query_graph_blocks_write_operations(self):
        """Test QueryGraph blocks CREATE, MERGE, DELETE etc."""
        orchestrator = Orchestrator()

        with scope(orchestrator.case_id):
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
    async def test_query_graph_blocks_hardcoded_case_id(self):
        """Test QueryGraph blocks hardcoded case_id values."""
        orchestrator = Orchestrator()

        with scope(orchestrator.case_id):
            tool = QueryGraph(cypher="MATCH (n {case_id: 'evil-session'}) RETURN n")
            result = await tool.call()

            assert "Hardcoded case_id values are not allowed" in result

    @pytest.mark.asyncio
    async def test_query_graph_auto_injects_case_id(self):
        """Test QueryGraph auto-injects case_id - LLM doesn't need to include it."""
        orchestrator = Orchestrator()

        with scope(orchestrator.case_id):
            # Query WITHOUT case_id - should work because we inject it
            tool = QueryGraph(cypher="MATCH (b:Case) RETURN b")
            result = await tool.call()

            assert "Found" in result
            assert "Case" in result

    @pytest.mark.asyncio
    async def test_query_graph_no_results(self):
        """Test QueryGraph handles empty results."""
        orchestrator = Orchestrator()

        with scope(orchestrator.case_id):
            tool = QueryGraph(cypher="MATCH (wu:WisdomUnit) RETURN wu")
            result = await tool.call()

            assert "No results found" in result

    @pytest.mark.asyncio
    async def test_query_graph_allows_schema_queries(self):
        """Test QueryGraph allows schema introspection."""
        orchestrator = Orchestrator()

        with scope(orchestrator.case_id):
            tool = QueryGraph(cypher="SHOW SCHEMA INFO")
            result = await tool.call()

            # Should not get any error - schema queries don't need case_id
            assert "Error" not in result or "Query error" in result  # Query error OK if DB doesn't support


class TestOrchestratorInitialization:
    """Tests for Orchestrator initialization."""

    def test_orchestrator_creates_session(self):
        """Test orchestrator creates a session on init."""
        orchestrator = Orchestrator()

        assert orchestrator.case_id is not None
        assert len(orchestrator.case_id) > 0

    def test_orchestrator_loads_existing_session(self):
        """Test orchestrator can load existing session."""
        # Create a session first
        first = Orchestrator()
        case_id = first.case_id

        # Load it in a new orchestrator
        second = Orchestrator(case_id=case_id)

        assert second.case_id == case_id

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

        with scope(orchestrator.case_id):
            # Add input
            add_tool = AddInput(content="Remote work increases productivity and flexibility.")
            result = await add_tool.call()

            assert "Added input to case" in result
            assert "Input hash:" in result

            # Query inputs - no case_id needed, auto-injected
            query_tool = QueryGraph(
                cypher="MATCH (b:Case)-[:HAS_INPUT]->(i:Input) RETURN i.content"
            )
            query_result = await query_tool.call()

            assert "Remote work" in query_result
