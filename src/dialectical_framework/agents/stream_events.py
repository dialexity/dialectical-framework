"""
StreamEvent: Tagged-union protocol for real-time events from the agentic loop.

Consumers (Chainlit, CLI, test harness) iterate over these events to drive UX:
- ThinkingDelta: token-by-token extended thinking/reasoning from the LLM
- TextDelta: token-by-token LLM output (during tool-calling rounds)
- ToolStart: LLM is invoking a tool
- ToolResult: tool execution completed (with optional graph effects)
- ResponseComplete: the turn's final structured response

**Render the deltas; do not wait for `ResponseComplete` to show text.** On the
ordinary turn `ResponseComplete.streamed` is True and its `message` is exactly
the `TextDelta`s already yielded, so a host that waits pays the whole turn
(~18s measured) for text it could have started showing in about a second. See
`ResponseComplete` for the precise contract, including the turns where the
deltas are NOT the reply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar, Union

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import ExecutionReport

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ThinkingDelta:
    """A token/chunk of LLM reasoning/thinking (extended thinking output)."""

    text: str


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
    (e.g., query_graph).

    `error` carries the message when the tool RAISED. Mirascope catches the
    exception inside `Tool.execute` and returns `str(e)` as the result, so
    without this field a crashed tool is indistinguishable from a read-only one
    that returned prose: both give `report=None`, and no framework logger ever
    sees the traceback. Consumers must check `error` before treating
    `report=None` as "this tool just does not report".
    """

    tool_name: str
    report: ExecutionReport | None
    raw_output: str
    error: str | None = None


@dataclass(frozen=True)
class ResponseComplete(Generic[T]):
    """The turn's final structured response.

    `streamed` answers the one question a rendering host cannot answer for
    itself: **have I already shown this text?**

    True means `message` is byte-for-byte the `TextDelta`s yielded since the
    last `ToolResult` this turn (or since the turn began, if no tool ran) —
    built from those exact bytes, not merely expected to match. A host that
    rendered the deltas as they arrived is already done: it should persist
    `message` and render nothing further. That is the whole point of streaming,
    and it is why waiting for this event before showing anything costs the
    person the entire turn (~18s measured) instead of first-token latency.

    False means the deltas are NOT the reply and `message` must be rendered:
    either nothing streamed (the tool-free path calls the provider once, with
    format, and cannot stream), or the streamed text was not usable as the
    answer and a separate structured call produced this one — see
    `ConversationFacilitator._reuse_written_reply` for exactly when.

    Text yielded BEFORE a `ToolStart` is never part of `message`. It is the
    model narrating what it is about to do, and the reply is what it says
    afterwards; a host may keep it on screen as progress but must not persist it
    as counsel.
    """

    result: T
    streamed: bool = False

    @property
    def message(self) -> str:
        """Convenience accessor — returns .message if present on result, else JSON."""
        if hasattr(self.result, "message"):
            return self.result.message
        if hasattr(self.result, "model_dump_json"):
            return self.result.model_dump_json()
        return str(self.result)


StreamEvent = Union[ThinkingDelta, TextDelta, ToolStart, ToolResult, ResponseComplete]
