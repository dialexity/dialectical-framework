"""
StreamEvent: Tagged-union protocol for real-time events from the agentic loop.

Consumers (Chainlit, CLI, test harness) iterate over these events to drive UX:
- TextDelta: token-by-token LLM output (during tool-calling rounds)
- ToolStart: LLM is invoking a tool
- ToolResult: tool execution completed (with optional graph effects)
- ResponseComplete: final structured response extracted
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, Union

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import ExecutionReport

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class TextDelta:
    """A token/chunk of text from the LLM response during tool rounds."""

    text: str


@dataclass(frozen=True, slots=True)
class ToolStart:
    """LLM is invoking a tool."""

    tool_name: str
    tool_args: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Tool execution completed.

    report is None for non-graph tools that return plain text
    (e.g., query_graph, get_scope_status).
    """

    tool_name: str
    report: ExecutionReport | None
    raw_output: str


@dataclass(frozen=True)
class ResponseComplete(Generic[T]):
    """Final structured response extracted from the conversation."""

    result: T

    @property
    def message(self) -> str:
        """Convenience accessor — returns .message if present on result, else JSON."""
        if hasattr(self.result, "message"):
            return self.result.message
        if hasattr(self.result, "model_dump_json"):
            return self.result.model_dump_json()
        return str(self.result)


StreamEvent = Union[TextDelta, ToolStart, ToolResult, ResponseComplete]
