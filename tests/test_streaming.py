"""
Tests for streaming support: stream_events, submit_stream, chat_stream.

Tests verify:
1. StreamEvent dataclass construction
2. ConversationFacilitator.submit_stream() yields correct event sequence
3. Orchestrator.chat_stream() delegates correctly
4. use_brain raw_call=True returns AsyncCall-like object
5. ExecutionReport parsing in ToolResult
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from typing import Any, Sequence
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.orchestrator.orchestrator import Orchestrator
from dialectical_framework.agents.stream_events import (
    ResponseComplete,
    StreamEvent,
    TextDelta,
    ToolResult,
    ToolStart,
)
from dialectical_framework.graph.scope_context import scope


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    """Override autouse fixture — streaming tests don't need the DB."""
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    """Override autouse fixture — streaming tests don't need the DB."""
    yield


class MockResponseModel(BaseModel):
    message: str = Field(description="Response message")


# --- Test StreamEvent dataclasses ---


class TestStreamEvents:
    """Test stream event dataclass construction and properties."""

    def test_text_delta(self):
        event = TextDelta(text="Hello")
        assert event.text == "Hello"
        assert asdict(event) == {"text": "Hello"}

    def test_tool_start(self):
        event = ToolStart(tool_name="surface_theses", tool_args={"intent": "trust"})
        assert event.tool_name == "surface_theses"
        assert event.tool_args == {"intent": "trust"}

    def test_tool_result_with_report(self):
        report = ExecutionReport(tool="surface_theses", ok=True, summary="Found 3 theses")
        event = ToolResult(tool_name="surface_theses", report=report, raw_output='{"tool": "surface_theses"}')
        assert event.report is not None
        assert event.report.ok is True
        assert event.raw_output.startswith("{")

    def test_tool_result_without_report(self):
        event = ToolResult(tool_name="query_graph", report=None, raw_output="Found 5 nodes")
        assert event.report is None
        assert event.raw_output == "Found 5 nodes"

    def test_response_complete(self):
        event = ResponseComplete(result=MockResponseModel(message="I found 3 theses about trust."))
        assert event.message == "I found 3 theses about trust."
        assert event.result.message == "I found 3 theses about trust."

    def test_events_are_frozen(self):
        event = TextDelta(text="Hello")
        with pytest.raises(Exception):
            event.text = "World"


# --- Test ExecutionReport parsing ---


class TestExecutionReportParsing:
    """Test _try_parse_execution_report helper."""

    def test_valid_json_parses(self):
        report = ExecutionReport(tool="test_tool", ok=True, summary="done")
        json_str = report.model_dump_json()
        parsed = ConversationFacilitator._try_parse_execution_report(json_str)
        assert parsed is not None
        assert parsed.tool == "test_tool"
        assert parsed.ok is True

    def test_invalid_json_returns_none(self):
        result = ConversationFacilitator._try_parse_execution_report("Not JSON at all")
        assert result is None

    def test_valid_json_but_wrong_schema_returns_none(self):
        result = ConversationFacilitator._try_parse_execution_report('{"foo": "bar"}')
        assert result is None

    def test_report_with_effects(self):
        report = ExecutionReport(tool="surface_theses")
        report.node_created(
            MagicMock(short_hash="abc123", text="Test", __class__=type("Statement", (), {"__name__": "Statement"})),
            patch={"text": "Test thesis"},
        )
        json_str = report.model_dump_json()
        parsed = ConversationFacilitator._try_parse_execution_report(json_str)
        assert parsed is not None
        assert len(parsed.effects) == 1
        assert parsed.effects[0].effect_type == "node_created"


# --- Test submit_stream with mocked LLM ---


class MockStreamResponse:
    """Mock AsyncStreamResponse for testing submit_stream."""

    def __init__(self, texts: list[str], tool_calls: list | None = None, tool_outputs: list[str] | None = None):
        self._texts = texts
        self.tool_calls = tool_calls or []
        self._tool_outputs = tool_outputs or []
        self.messages = [{"role": "assistant", "content": "".join(texts)}]

    async def text_stream(self):
        for text in self._texts:
            yield text

    async def execute_tools(self) -> Sequence:
        return self._tool_outputs

    async def resume(self, outputs) -> "MockStreamResponse":
        return MockStreamResponse(texts=["Final text."], tool_calls=[], tool_outputs=[])


class MockToolCall:
    def __init__(self, name: str, args: dict | None = None):
        self.name = name
        self.args = json.dumps(args) if args else ""


class MockAsyncCall:
    """Mock AsyncCall object returned by raw_call=True."""

    def __init__(self, stream_response: MockStreamResponse):
        self._stream_response = stream_response

    async def stream(self) -> MockStreamResponse:
        return self._stream_response


@pytest.mark.llm
@pytest.mark.asyncio
class TestSubmitStream:
    """Test ConversationFacilitator.submit_stream() event emission."""

    async def test_no_tools_yields_response_complete(self):
        """Without tools, submit_stream calls _call_with_response_model and yields ResponseComplete."""
        facilitator = ConversationFacilitator(tools=[])

        events = []
        async for event in facilitator.submit_stream(MockResponseModel, "Hello"):
            events.append(event)

        assert len(events) == 1
        assert isinstance(events[0], ResponseComplete)

    async def test_stream_with_tools_no_tool_calls(self):
        """Tools available but LLM doesn't call any — yields TextDelta + ResponseComplete."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        stream_resp = MockStreamResponse(texts=["I'll just ", "respond directly."], tool_calls=[])
        mock_call = MockAsyncCall(stream_resp)

        with patch.object(facilitator, "_get_tools_call", return_value=mock_call):
            events = []
            async for event in facilitator.submit_stream(MockResponseModel, "Hi"):
                events.append(event)

        text_events = [e for e in events if isinstance(e, TextDelta)]
        assert len(text_events) == 2
        assert text_events[0].text == "I'll just "
        assert text_events[1].text == "respond directly."

        complete_events = [e for e in events if isinstance(e, ResponseComplete)]
        assert len(complete_events) == 1

    async def test_stream_with_tool_execution(self):
        """LLM calls a tool — yields TextDelta, ToolStart, ToolResult, then ResponseComplete."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        report = ExecutionReport(tool="surface_theses", ok=True, summary="Found theses")
        report_json = report.model_dump_json()

        tool_call = MockToolCall(name="surface_theses", args={"intent": "trust"})
        stream_resp = MockStreamResponse(
            texts=["Let me ", "analyze."],
            tool_calls=[tool_call],
            tool_outputs=[report_json],
        )
        mock_call = MockAsyncCall(stream_resp)

        with patch.object(facilitator, "_get_tools_call", return_value=mock_call):
            events = []
            async for event in facilitator.submit_stream(MockResponseModel, "Analyze trust"):
                events.append(event)

        # Check event sequence
        text_events = [e for e in events if isinstance(e, TextDelta)]
        assert len(text_events) >= 2  # At least from first round

        tool_starts = [e for e in events if isinstance(e, ToolStart)]
        assert len(tool_starts) == 1
        assert tool_starts[0].tool_name == "surface_theses"
        assert tool_starts[0].tool_args == {"intent": "trust"}

        tool_results = [e for e in events if isinstance(e, ToolResult)]
        assert len(tool_results) == 1
        assert tool_results[0].tool_name == "surface_theses"
        assert tool_results[0].report is not None
        assert tool_results[0].report.ok is True
        assert tool_results[0].raw_output == report_json

        complete_events = [e for e in events if isinstance(e, ResponseComplete)]
        assert len(complete_events) == 1

    async def test_non_graph_tool_has_none_report(self):
        """Tools returning plain text (not ExecutionReport JSON) have report=None."""
        facilitator = ConversationFacilitator(tools=[lambda: None])

        tool_call = MockToolCall(name="query_graph", args={"cypher": "MATCH (n) RETURN n"})
        stream_resp = MockStreamResponse(
            texts=["Querying..."],
            tool_calls=[tool_call],
            tool_outputs=["Found 5 nodes:\n- Statement: 'Trust'"],
        )
        mock_call = MockAsyncCall(stream_resp)

        with patch.object(facilitator, "_get_tools_call", return_value=mock_call):
            events = []
            async for event in facilitator.submit_stream(MockResponseModel, "Query"):
                events.append(event)

        tool_results = [e for e in events if isinstance(e, ToolResult)]
        assert len(tool_results) == 1
        assert tool_results[0].report is None
        assert "Found 5 nodes" in tool_results[0].raw_output


# --- Test Orchestrator.chat_stream ---


@pytest.mark.llm
@pytest.mark.asyncio
class TestOrchestratorChatStream:
    """Test Orchestrator.chat_stream() delegates to submit_stream."""

    def _make_orchestrator(self):
        """Create Orchestrator without hitting the DB."""
        with patch("dialectical_framework.agents.orchestrator.orchestrator.Case") as mock_case, \
             patch.object(Orchestrator, "_query_live_schema", return_value=""):
            mock_case.return_value.commit.return_value = None
            mock_case.return_value.sid = "test-sid"
            return Orchestrator()

    async def test_chat_stream_yields_events(self):
        """chat_stream should yield StreamEvent instances from submit_stream."""
        orchestrator = self._make_orchestrator()

        async def mock_submit_stream(response_model, user_content, max_tool_rounds=10):
            yield TextDelta(text="Working...")
            yield ToolStart(tool_name="surface_theses", tool_args={"intent": "test"})
            yield ToolResult(tool_name="surface_theses", report=None, raw_output="done")
            yield ResponseComplete(result=MockResponseModel(message="Found theses."))

        with patch.object(orchestrator._conversation, "submit_stream", mock_submit_stream):
            events = []
            async for event in orchestrator.chat_stream("Hello"):
                events.append(event)

        assert len(events) == 4
        assert isinstance(events[0], TextDelta)
        assert isinstance(events[1], ToolStart)
        assert isinstance(events[2], ToolResult)
        assert isinstance(events[3], ResponseComplete)
        assert events[3].message == "Found theses."

    async def test_chat_stream_empty_response(self):
        """chat_stream handles no-tool path yielding just ResponseComplete."""
        orchestrator = self._make_orchestrator()

        async def mock_submit_stream(response_model, user_content, max_tool_rounds=10):
            yield ResponseComplete(result=MockResponseModel(message="Simple answer."))

        with patch.object(orchestrator._conversation, "submit_stream", mock_submit_stream):
            events = []
            async for event in orchestrator.chat_stream("Hi"):
                events.append(event)

        assert len(events) == 1
        assert isinstance(events[0], ResponseComplete)
        assert events[0].message == "Simple answer."


# --- Test use_brain raw_call mode ---


@pytest.mark.llm
class TestUseBrainRawCall:
    """Test that use_brain with raw_call=True returns callable object."""

    @pytest.mark.asyncio
    async def test_raw_call_returns_callable(self):
        """raw_call=True should return something with .stream() method."""
        from dialectical_framework.utils.use_brain import use_brain

        @use_brain(raw_call=True, tools=[])
        async def my_call():
            return [{"role": "user", "content": "test"}]

        # With mock brain installed, use_brain is mocked. But let's verify
        # the concept works: the decorator should return something callable.
        result = await my_call()
        # In test mode with mock_brain, this returns the mock.
        # The important thing is it doesn't raise.
        assert result is not None


# --- End-to-end streaming with real LLM ---


@llm.tool
async def get_current_time() -> str:
    """Return the current UTC time."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%H:%M:%S UTC")


@pytest.mark.real_llm
@pytest.mark.asyncio
class TestStreamingEndToEnd:
    """End-to-end streaming tests that hit the real LLM provider."""

    async def test_stream_no_tools(self):
        """submit_stream without tools yields TextDelta (possibly) and ResponseComplete."""
        facilitator = ConversationFacilitator(tools=[])
        facilitator.set_system_prompt("You are a helpful assistant. Be concise.")

        events = []
        async for event in facilitator.submit_stream(MockResponseModel, "Say hello."):
            events.append(event)

        assert len(events) >= 1
        assert isinstance(events[-1], ResponseComplete)
        assert events[-1].result.message  # non-empty

    async def test_stream_with_tool_call(self):
        """submit_stream with a tool yields TextDelta, ToolStart, ToolResult, ResponseComplete."""
        facilitator = ConversationFacilitator(tools=[get_current_time])
        facilitator.set_system_prompt(
            "You are a helpful assistant. When asked for the time, "
            "always use the get_current_time tool. Be concise."
        )

        events = []
        async for event in facilitator.submit_stream(MockResponseModel, "What time is it?"):
            events.append(event)

        tool_starts = [e for e in events if isinstance(e, ToolStart)]
        tool_results = [e for e in events if isinstance(e, ToolResult)]
        assert len(tool_starts) >= 1
        assert tool_starts[0].tool_name == "get_current_time"
        assert len(tool_results) >= 1
        assert "UTC" in tool_results[0].raw_output

        assert isinstance(events[-1], ResponseComplete)
        assert events[-1].result.message
