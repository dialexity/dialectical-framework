"""
Tests for the Analyst agent.

These are integration tests that verify:
1. Analyst initialization and tool registration (default + advanced modes)
2. Analyst workflow (add input → query)
3. Analyst chat_stream delegates correctly
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.analyst.analyst import Analyst
from dialectical_framework.agents.orchestrator.tools.add_input import AddInput
from dialectical_framework.agents.orchestrator.tools.query_graph import \
    QueryGraph
from dialectical_framework.agents.stream_events import (ResponseComplete,
                                                        StreamEvent, TextDelta,
                                                        ToolResult, ToolStart)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    """Create a Case and return its sid."""
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


class MockResponseModel(BaseModel):
    message: str = Field(description="Response message")


class TestAnalystInitialization:
    """Tests for Analyst initialization."""

    def test_default_mode_tools(self):
        """Test default mode has autonomous pipeline + steering + query tools."""
        analyst = Analyst()

        tool_names = [t.__name__ for t in analyst._tools]

        assert "analyze" in tool_names
        assert "create_nexus" in tool_names
        assert "create_dx_input" in tool_names
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
        assert "create_dx_input" in tool_names
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

    def test_messages_loaded_on_init(self):
        """Test messages are loaded when provided."""
        fake_messages = [{"role": "user", "content": "hello"}]
        analyst = Analyst(messages=fake_messages)

        assert len(analyst.messages) >= 1

    def test_mode_property(self):
        """Test mode property reflects constructor arg."""
        assert Analyst().mode == "default"
        assert Analyst(mode="advanced").mode == "advanced"


class TestAnalystWorkflow:
    """Integration tests for analyst workflows."""

    @pytest.mark.asyncio
    async def test_add_input_workflow(self):
        """Test workflow: add input -> query inputs."""
        sid = _new_sid()

        with scope(sid):
            concern = AddInput()
            input_node = await concern.resolve(
                content="Remote work increases productivity and flexibility."
            )

            assert input_node.is_committed

            query_concern = QueryGraph()
            query_result = await query_concern.resolve(
                cypher="MATCH (b:Case)-[:HAS_INPUT]->(i:Input) RETURN i.content"
            )

            assert "Remote work" in query_result


@pytest.mark.llm
@pytest.mark.asyncio
class TestAnalystChatStream:
    """Test Analyst.chat_stream() delegates to submit_stream."""

    async def test_chat_stream_yields_events(self):
        """chat_stream should yield StreamEvent instances from submit_stream."""
        analyst = Analyst()

        async def mock_submit_stream(response_model, user_content, max_tool_rounds=10):
            yield TextDelta(text="Working...")
            yield ToolStart(tool_name="surface_theses", tool_args={"intent": "test"})
            yield ToolResult(tool_name="surface_theses", report=None, raw_output="done")
            yield ResponseComplete(result=MockResponseModel(message="Found theses."))

        with patch.object(analyst._conversation, "submit_stream", mock_submit_stream):
            events = []
            async for event in analyst.chat_stream("Hello"):
                events.append(event)

        assert len(events) == 4
        assert isinstance(events[0], TextDelta)
        assert isinstance(events[1], ToolStart)
        assert isinstance(events[2], ToolResult)
        assert isinstance(events[3], ResponseComplete)
        assert events[3].message == "Found theses."

    async def test_chat_stream_empty_response(self):
        """chat_stream handles no-tool path yielding just ResponseComplete."""
        analyst = Analyst()

        async def mock_submit_stream(response_model, user_content, max_tool_rounds=10):
            yield ResponseComplete(result=MockResponseModel(message="Simple answer."))

        with patch.object(analyst._conversation, "submit_stream", mock_submit_stream):
            events = []
            async for event in analyst.chat_stream("Hi"):
                events.append(event)

        assert len(events) == 1
        assert isinstance(events[0], ResponseComplete)
        assert events[0].message == "Simple answer."
