"""
Tests for the Advisor's background-analysis hook (guaranteed graph-building).

Principle under test: prompts are for judgment, code is for invariants.
Graph-building must not depend on the model choosing to call tools — after a
counsel-shaped turn without a graph-building tool call, the Advisor runs
AnalysisPipeline itself as a background task, drained at the next turn.

Mock brain returns tool_calls=[] (no tool path), so these tests monkeypatch
AnalysisPipeline.resolve with recording stubs — the established pattern from
test_expand_polarities_count.py.
"""

from __future__ import annotations

import asyncio

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor
from dialectical_framework.agents.analyst.analyst import (AnalysisPipeline,
                                                          AnalysisResult)

SUBSTANTIVE_MESSAGE = (
    "I want to push my team hard toward the deadline, but I worry that the "
    "pressure is burning people out and quality is starting to slip."
)


def _system_prompt_text(advisor: Advisor) -> str:
    """Extract system-prompt text regardless of Mirascope content shape."""
    content = advisor._conversation._messages[0].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(getattr(part, "text", str(part)) for part in content)
    return content.text


def _install_recording_stub(monkeypatch, calls: list, perspective_hashes=None):
    """Replace AnalysisPipeline.resolve with a recorder returning a result."""

    async def stub(self):
        calls.append(self.text)
        return AnalysisResult(perspective_hashes=perspective_hashes or [])

    monkeypatch.setattr(AnalysisPipeline, "resolve", stub)


@pytest.mark.llm
class TestBackgroundAnalysisHook:
    async def test_hook_invoked_on_counsel_shaped_turn(self, monkeypatch):
        calls: list = []
        _install_recording_stub(monkeypatch, calls)

        advisor = Advisor()
        await advisor.chat(SUBSTANTIVE_MESSAGE)
        await advisor.flush_analysis()

        assert calls == [SUBSTANTIVE_MESSAGE]

    async def test_hook_skipped_for_short_message(self, monkeypatch):
        calls: list = []
        _install_recording_stub(monkeypatch, calls)

        advisor = Advisor()
        await advisor.chat("hi there")
        await advisor.flush_analysis()

        assert calls == []

    async def test_hook_skipped_when_graph_tool_fired(self, monkeypatch):
        calls: list = []
        _install_recording_stub(monkeypatch, calls)

        advisor = Advisor()

        # Mock brain can't produce tool calls, so simulate the seam directly:
        # wrap submit to leave a graph-building tool name in last_tool_calls.
        original_submit = advisor._conversation.submit

        async def submit_with_tool_call(*args, **kwargs):
            result = await original_submit(*args, **kwargs)
            advisor._conversation.last_tool_calls = ["anchor"]
            return result

        monkeypatch.setattr(advisor._conversation, "submit", submit_with_tool_call)

        await advisor.chat(SUBSTANTIVE_MESSAGE)
        await advisor.flush_analysis()

        assert calls == []
        # But the context must be marked stale (the model mutated the graph)...
        # flush_analysis() already consumed the dirty flag by refreshing:
        assert advisor._context_dirty is False

    async def test_hook_disabled_by_flag(self, monkeypatch):
        calls: list = []
        _install_recording_stub(monkeypatch, calls)

        advisor = Advisor(background_analysis=False)
        await advisor.chat(SUBSTANTIVE_MESSAGE)
        await advisor.flush_analysis()

        assert calls == []

    async def test_drain_before_next_turn(self, monkeypatch):
        """The background task must complete before the next submit begins."""
        order: list[str] = []
        release = asyncio.Event()

        async def slow_stub(self):
            order.append("analysis_started")
            await release.wait()
            order.append("analysis_finished")
            return AnalysisResult()

        monkeypatch.setattr(AnalysisPipeline, "resolve", slow_stub)

        advisor = Advisor()
        original_submit = advisor._conversation.submit

        async def tracking_submit(*args, **kwargs):
            order.append("submit")
            return await original_submit(*args, **kwargs)

        monkeypatch.setattr(advisor._conversation, "submit", tracking_submit)

        await advisor.chat(SUBSTANTIVE_MESSAGE)
        release.set()  # let the background task finish when drained
        await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert order == [
            "submit",
            "analysis_started",
            "analysis_finished",
            "submit",
        ]

    async def test_context_refresh_after_background_analysis(self, monkeypatch):
        """When background analysis yields perspectives, the next turn's
        system prompt is re-rendered from DialecticalContext."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        _install_recording_stub(
            monkeypatch, [], perspective_hashes=["abc1234"]
        )

        fresh_dump = "# Nexus [[fresh]] refreshed understanding"

        async def fake_context(self):
            return fresh_dump

        monkeypatch.setattr(DialecticalContext, "resolve", fake_context)

        advisor = Advisor()
        assert fresh_dump not in _system_prompt_text(advisor)

        await advisor.chat(SUBSTANTIVE_MESSAGE)
        # flush = drain the background task + refresh the system prompt
        # (asserting right after flush, because the mocked submit path wipes
        # message history — a mock-brain artifact, not real behavior)
        await advisor.flush_analysis()

        assert fresh_dump in _system_prompt_text(advisor)

    async def test_background_failure_is_soft(self, monkeypatch):
        """A crashing pipeline must never break the chat path."""

        async def broken(self):
            raise RuntimeError("pipeline exploded")

        monkeypatch.setattr(AnalysisPipeline, "resolve", broken)

        advisor = Advisor()
        first = await advisor.chat(SUBSTANTIVE_MESSAGE)
        second = await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert isinstance(first, str)
        assert isinstance(second, str)
