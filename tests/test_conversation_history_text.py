"""
Tests for ConversationFacilitator._assistant_history_text.

Structured results land in conversation history as NATURAL TEXT, not a
Pydantic repr: the history is replayed to the provider every turn (and across
Explorer<->Advisor handovers), so "message='...'" repr syntax both wastes
tokens and invites the model to imitate it in its own replies.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator


# DB-free: override the autouse graph fixtures.
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _ChatLike(BaseModel):
    message: str


class _NoMessageDto(BaseModel):
    finding: str
    score: float


class _EmptyMessageDto(BaseModel):
    message: str = ""


class TestAssistantHistoryText:
    def test_chat_response_stores_plain_message(self):
        result = _ChatLike(message="Here is my counsel.")
        text = ConversationFacilitator._assistant_history_text(result)
        assert text == "Here is my counsel."
        assert "message=" not in text

    def test_dto_without_message_falls_back_to_str(self):
        result = _NoMessageDto(finding="tension", score=0.7)
        text = ConversationFacilitator._assistant_history_text(result)
        assert text == str(result)

    def test_empty_message_falls_back_to_str(self):
        """An empty message would create an empty assistant turn — fall back
        to the repr rather than storing nothing."""
        result = _EmptyMessageDto()
        text = ConversationFacilitator._assistant_history_text(result)
        assert text == str(result)

    @pytest.mark.llm
    async def test_history_after_submit_carries_no_repr_syntax(self):
        """End-to-end through the (mocked) submit path: the stored assistant
        turn is the message text itself."""
        facilitator = ConversationFacilitator()
        facilitator.set_system_prompt("You are a test assistant.")
        await facilitator.submit(_ChatLike, "hello")

        last = facilitator._messages[-1]
        content = last.content
        text = content if isinstance(content, str) else getattr(
            content, "text", str(content)
        )
        assert "message=" not in text
