"""
Tests for the Explorer agent.

These are integration tests that verify:
1. Explorer initialization and tool registration (default + advanced modes)
2. Explorer requires nexus_hash and resolves intent
3. Explorer chat_stream delegates correctly
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.explorer.explorer import Explorer
from dialectical_framework.agents.stream_events import (ResponseComplete,
                                                        TextDelta, ToolResult,
                                                        ToolStart)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope


def _new_sid() -> str:
    """Create a Case and return its sid."""
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _create_nexus(sid: str, intent: str = "test exploration") -> str:
    """Create a Nexus and return its hash."""
    from dialectical_framework.graph.nodes.nexus import Nexus

    nexus = Nexus(intent=intent)
    nexus.save()
    nexus.commit()
    return nexus.hash


class MockResponseModel(BaseModel):
    message: str = Field(description="Response message")


class TestExplorerInitialization:
    """Tests for Explorer initialization."""

    def test_default_mode_tools(self):
        """Test default mode has exploration tools."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            explorer = Explorer(nexus_hash=nexus_hash)

            tool_names = [t.__name__ for t in explorer._tools]

            assert "build_wheels" in tool_names
            assert "explore_transformations" in tool_names
            assert "present_exploration" in tool_names
            assert "inspect_node" in tool_names
            assert "query_graph" in tool_names
            assert "get_schema" in tool_names

            # Advanced-only tools NOT in default mode
            assert "create_nexus" not in tool_names

    def test_advanced_mode_tools(self):
        """Test advanced mode adds create_nexus."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            explorer = Explorer(nexus_hash=nexus_hash, mode="advanced")

            tool_names = [t.__name__ for t in explorer._tools]

            assert "build_wheels" in tool_names
            assert "explore_transformations" in tool_names
            assert "create_nexus" in tool_names
            assert "present_exploration" in tool_names
            assert "inspect_node" in tool_names
            assert "query_graph" in tool_names
            assert "get_schema" in tool_names

    def test_nexus_hash_property(self):
        """Test nexus_hash property."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            explorer = Explorer(nexus_hash=nexus_hash)

            assert explorer.nexus_hash == nexus_hash

    def test_mode_property(self):
        """Test mode property reflects constructor arg."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            assert Explorer(nexus_hash=nexus_hash).mode == "default"
            assert Explorer(nexus_hash=nexus_hash, mode="advanced").mode == "advanced"

    def test_messages_loaded_on_init(self):
        """Test messages are loaded when provided."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            fake_messages = [{"role": "user", "content": "hello"}]
            explorer = Explorer(nexus_hash=nexus_hash, messages=fake_messages)

            assert len(explorer.messages) >= 1

    def test_raises_on_invalid_nexus(self):
        """Test Explorer raises when nexus_hash doesn't resolve."""
        sid = _new_sid()
        with scope(sid):
            with pytest.raises(ValueError, match="Nexus not found"):
                Explorer(nexus_hash="nonexistent_hash")


@pytest.mark.llm
@pytest.mark.asyncio
class TestExplorerChatStream:
    """Test Explorer.chat_stream() delegates to submit_stream."""

    def _make_explorer(self) -> Explorer:
        """Create Explorer with a real Nexus."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            return Explorer(nexus_hash=nexus_hash)

    async def test_chat_stream_yields_events(self):
        """chat_stream should yield StreamEvent instances."""
        sid = _new_sid()
        with scope(sid):
            nexus_hash = _create_nexus(sid)
            explorer = Explorer(nexus_hash=nexus_hash)

            async def mock_submit_stream(
                response_model, user_content, max_tool_rounds=10
            ):
                yield TextDelta(text="Exploring...")
                yield ToolStart(
                    tool_name="build_wheels", tool_args={"nexus_hash": nexus_hash}
                )
                yield ToolResult(
                    tool_name="build_wheels", report=None, raw_output="done"
                )
                yield ResponseComplete(
                    result=MockResponseModel(message="Exploration complete.")
                )

            with patch.object(
                explorer._conversation, "submit_stream", mock_submit_stream
            ):
                events = []
                async for event in explorer.chat_stream("What paths do I have?"):
                    events.append(event)

            assert len(events) == 4
            assert isinstance(events[0], TextDelta)
            assert isinstance(events[1], ToolStart)
            assert isinstance(events[2], ToolResult)
            assert isinstance(events[3], ResponseComplete)
            assert events[3].message == "Exploration complete."
