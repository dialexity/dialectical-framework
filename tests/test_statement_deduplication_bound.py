"""`StatementDeduplication`'s source context is bounded, and announces the cut.

The fourth unbounded raw-content consumer, with TWO prompt sites, and it was the
easiest to miss because none of its four callers looks like it is sending a
document: `surface_theses` and `find_polarities` pass the full concatenation of
every Input in scope, `expand_polarities` and `statement_placement` pass theirs.
The question being asked is "which of these dozen short statements restate each
other" — a 400 KB file is not an input to that.

Bounding it inside the concern rather than at the call sites is deliberate: one
change covers all four, and a fifth caller inherits it.
"""

from __future__ import annotations

from typing import Optional

import pytest

from dialectical_framework.concerns.statement_deduplication import (
    DEDUP_CONTEXT_LIMIT, IdeaMatchDto, SemanticDedupDto, StatementDeduplication,
    _bounded_context)


@pytest.fixture
def cleanup_graph_db():
    """DB-free: the graph reads are stubbed."""
    yield


@pytest.fixture
def cleanup_test_graph_data():
    yield


class _FakeConversation:
    def __init__(self, reply) -> None:
        self._reply = reply
        self.prompts: list[str] = []

    async def submit(self, response_model, user_content: str, **kwargs):
        self.prompts.append(user_content)
        return self._reply


class _FakeStatement:
    is_committed = True

    def __init__(self, text: str) -> None:
        self.prompt_text = text
        self.short_hash = "abc1234"
        self.meaning: Optional[str] = None


def _vocabulary() -> list[dict]:
    return [
        {
            "hash": "def456789",
            "statement": "Centralization erodes trust",
            "meaning": None,
            "discarded": None,
            "rationale": None,
        }
    ]


def _document(chars: int) -> str:
    return ("Governance concentrates decisions. " * ((chars // 35) + 2))[:chars]


class TestTheBoundItself:
    def test_a_short_context_is_untouched(self):
        text = "a short source"
        assert _bounded_context(text) == text

    def test_a_context_exactly_at_the_limit_is_untouched(self):
        text = "x" * DEDUP_CONTEXT_LIMIT
        assert _bounded_context(text) == text

    def test_a_long_context_is_cut_and_says_so(self):
        text = "x" * (DEDUP_CONTEXT_LIMIT + 5000)
        bounded = _bounded_context(text)

        assert len(bounded) == DEDUP_CONTEXT_LIMIT + 3
        assert bounded.endswith("...")
        assert bounded[:DEDUP_CONTEXT_LIMIT] == text[:DEDUP_CONTEXT_LIMIT]

    def test_the_limit_matches_the_sibling_using_the_same_header(self):
        """`StatementClassification` renders a `**Source Context:**` section of
        its own; two different caps under one header is a drift hotspot."""
        import inspect

        from dialectical_framework.concerns import statement_classification

        src = inspect.getsource(statement_classification)
        assert f"[:{DEDUP_CONTEXT_LIMIT}]" in src


class TestTheBatchDedupPrompt:
    @pytest.mark.asyncio
    async def test_a_document_does_not_reach_the_prompt_whole(self, monkeypatch):
        text = _document(400_000)
        concern = StatementDeduplication()
        concern._text = text
        conversation = _FakeConversation(SemanticDedupDto(matches=[]))
        concern._conversation = conversation
        monkeypatch.setattr(
            concern, "_resolve_component", lambda h: _FakeStatement("Trust is earned")
        )

        await concern._find_semantic_matches(["aaa111"], _vocabulary())

        prompt = conversation.prompts[0]
        assert text not in prompt
        assert len(prompt) < len(text) / 10
        assert "..." in prompt

    @pytest.mark.asyncio
    async def test_a_short_context_still_arrives_verbatim(self, monkeypatch):
        text = "The team argued about whether to centralize the roadmap."
        concern = StatementDeduplication()
        concern._text = text
        conversation = _FakeConversation(SemanticDedupDto(matches=[]))
        concern._conversation = conversation
        monkeypatch.setattr(
            concern, "_resolve_component", lambda h: _FakeStatement("Trust is earned")
        )

        await concern._find_semantic_matches(["aaa111"], _vocabulary())

        assert text in conversation.prompts[0]

    @pytest.mark.asyncio
    async def test_no_context_renders_no_section(self, monkeypatch):
        concern = StatementDeduplication()
        concern._text = ""
        conversation = _FakeConversation(SemanticDedupDto(matches=[]))
        concern._conversation = conversation
        monkeypatch.setattr(
            concern, "_resolve_component", lambda h: _FakeStatement("Trust is earned")
        )

        await concern._find_semantic_matches(["aaa111"], _vocabulary())

        assert "**Source Context:**" not in conversation.prompts[0]


class TestTheCheckIdeaPrompt:
    """The second site, reached from `statement_placement`. It takes the text as
    a parameter rather than off `self`, which is exactly how one of two identical
    interpolations gets fixed and the other does not."""

    @pytest.mark.asyncio
    async def test_a_document_does_not_reach_the_prompt_whole(self):
        text = _document(400_000)
        concern = StatementDeduplication()
        conversation = _FakeConversation(IdeaMatchDto(is_duplicate=False))
        concern._conversation = conversation

        await concern.check_idea(
            idea="Trust is earned", vocabulary=_vocabulary(), text=text
        )

        prompt = conversation.prompts[0]
        assert text not in prompt
        assert len(prompt) < len(text) / 10
        assert "..." in prompt

    @pytest.mark.asyncio
    async def test_a_short_context_still_arrives_verbatim(self):
        text = "The team argued about whether to centralize the roadmap."
        concern = StatementDeduplication()
        conversation = _FakeConversation(IdeaMatchDto(is_duplicate=False))
        concern._conversation = conversation

        await concern.check_idea(
            idea="Trust is earned", vocabulary=_vocabulary(), text=text
        )

        assert text in conversation.prompts[0]
