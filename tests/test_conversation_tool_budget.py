"""
History stays API-valid when the agentic tool loop hits its round budget.

The loop in `submit`/`submit_stream` stops after `max_tool_rounds` even if the
model just asked for another tool. Because `self._messages` is then reassigned
from the response chain, an unanswered `tool_use` does not merely fail one
call — it is PERSISTED and replayed forever after:

    messages.22: `tool_use` ids were found without `tool_result` blocks
    immediately after: toolu_bdrk_01Grxx45A

Observed in the bench as an Advisor session where all six turns failed citing
that same stale id, after ~103 minutes of real tool work whose output was then
unreachable. The turn recorded no text, which reads as "the model collapsed"
rather than "its history was malformed" — the recurring misdiagnosis this
suite exists to prevent (see test_llm_transport_resilience).
"""

from __future__ import annotations

import pytest
from mirascope.llm.content import ToolCall

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _FakeResponse:
    """Minimal stand-in for the shape `_close_dangling_tool_calls` reads."""

    def __init__(self, tool_calls: list[ToolCall]) -> None:
        self.tool_calls = tool_calls


def _tool_call(id_: str, name: str = "explore") -> ToolCall:
    return ToolCall(id=id_, name=name, args="{}")


def _content_parts(message) -> list:
    content = message.content
    return list(content) if isinstance(content, (list, tuple)) else [content]


class TestDanglingToolCallClosure:
    def test_unanswered_tool_call_gets_a_tool_result(self):
        """The invariant the API enforces: every tool_use is answered."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse([_tool_call("toolu_1")])
        )

        assert len(facilitator._messages) == 1
        last = facilitator._messages[-1]
        assert last.role == "user"
        parts = _content_parts(last)
        assert [p.type for p in parts] == ["tool_output"]
        assert parts[0].id == "toolu_1"

    def test_every_parallel_call_is_answered(self):
        """Anthropic requires ALL ids from one assistant turn answered — a
        partial answer is rejected exactly like no answer."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse(
                [_tool_call("toolu_a", "explore"), _tool_call("toolu_b", "sync")]
            )
        )

        parts = _content_parts(facilitator._messages[-1])
        assert [p.id for p in parts] == ["toolu_a", "toolu_b"]
        assert [p.name for p in parts] == ["explore", "sync"]

    def test_synthetic_result_says_the_tool_did_not_run(self):
        """The model must not read this as a real tool result — otherwise it
        reports invented findings as verified."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse([_tool_call("toolu_1")])
        )

        result = _content_parts(facilitator._messages[-1])[0].result
        assert "not executed" in result.lower()
        assert "do not call more tools" in result.lower()

    def test_no_tool_calls_leaves_history_untouched(self):
        """The overwhelmingly common path: the loop ended because the model was
        done. Appending anything here would corrupt a healthy conversation."""
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.add_user_message("hello")
        before = list(facilitator._messages)

        facilitator._close_dangling_tool_calls(_FakeResponse([]))

        assert facilitator._messages == before

    def test_history_ends_on_user_so_no_filler_text_is_added(self):
        """`_call_with_response_model` appends "Provide your structured
        response." only when history ends on an assistant turn. The closure
        message must satisfy that check itself, so the extraction call sees the
        tool_result as the final turn rather than a text message wedged between
        the tool_use and its answer.
        """
        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator._close_dangling_tool_calls(
            _FakeResponse([_tool_call("toolu_1")])
        )

        assert facilitator._messages[-1].role == "user"


class TestBudgetExhaustionEndToEnd:
    """Through `submit`, with a model that never stops asking for tools."""

    @pytest.mark.llm
    async def test_persistent_tool_calls_leave_valid_history(self, monkeypatch):
        """The regression itself: a model that always wants another tool must
        not leave a `tool_use` unanswered at the end of history.

        Guards the *persisted* state, not just the immediate call — the bench
        failure was every LATER turn dying on a stale id from this turn.
        """
        from pydantic import BaseModel

        class _Chat(BaseModel):
            message: str

        facilitator = ConversationFacilitator(tools=[lambda: None])
        facilitator.set_system_prompt("You are a test assistant.")

        rounds = {"n": 0}

        class _LoopingResponse:
            """Always asks for one more tool, as a runaway model would."""

            def __init__(self) -> None:
                self.tool_calls = [_tool_call(f"toolu_{rounds['n']}")]
                self.messages = []

            async def execute_tools(self):
                return []

            async def resume(self, _outputs):
                rounds["n"] += 1
                return _LoopingResponse()

        async def _fake_call_with_tools(self):
            return _LoopingResponse()

        monkeypatch.setattr(
            ConversationFacilitator, "_call_with_tools", _fake_call_with_tools
        )

        await facilitator.submit(_Chat, "go", max_tool_rounds=3)

        # Find the last tool_use/tool_output pairing in the persisted history.
        outputs: list[str] = []
        for msg in facilitator._messages:
            for part in _content_parts(msg):
                if getattr(part, "type", None) == "tool_output":
                    outputs.append(part.id)

        assert outputs, "the unanswered tool call was never closed"
        assert f"toolu_{rounds['n']}" in outputs
