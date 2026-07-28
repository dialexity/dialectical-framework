"""
Tests for the Advisor's between-turn context refresh.

The Advisor's system prompt embeds a Current Understanding dump rendered at
construction. When a turn's tool calls mutate the graph (ingest/anchor/
explore/discard), the dump is stale — the Advisor re-renders it from
DialecticalContext at the start of the next turn, driven by the
ConversationFacilitator.last_tool_calls observation seam.

Mock brain returns tool_calls=[] (no tool path), so tool activity is
simulated by setting the seam directly.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor

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


def _install_fake_context(monkeypatch, dump: str) -> None:
    from dialectical_framework.concerns.dialectical_context import \
        DialecticalContext

    async def fake_context(self):
        return dump

    monkeypatch.setattr(DialecticalContext, "resolve", fake_context)


def _simulate_tool_calls(monkeypatch, advisor: Advisor, tool_names: list[str]):
    """Wrap submit so the turn appears to have invoked the given tools."""
    original_submit = advisor._conversation.submit

    async def submit_with_tool_calls(*args, **kwargs):
        result = await original_submit(*args, **kwargs)
        advisor._conversation.last_tool_calls = list(tool_names)
        return result

    monkeypatch.setattr(advisor._conversation, "submit", submit_with_tool_calls)


@pytest.mark.llm
class TestAdvisorContextRefresh:
    async def test_refresh_after_graph_mutating_tool(self, monkeypatch):
        """A turn that fired anchor marks the context dirty; the next turn
        re-renders the system prompt from DialecticalContext."""
        fresh_dump = "# Nexus [[fresh]] refreshed understanding"
        _install_fake_context(monkeypatch, fresh_dump)

        advisor = Advisor()
        _simulate_tool_calls(monkeypatch, advisor, ["anchor"])
        assert fresh_dump not in _system_prompt_text(advisor)

        await advisor.chat(SUBSTANTIVE_MESSAGE)  # fires "anchor" → dirty
        assert advisor._context_dirty is True

        # The next turn starts by refreshing; invoke that step directly
        # (asserting after a full chat() is impossible under mock brain —
        # the mocked submit path wipes message history).
        await advisor._refresh_context()
        assert fresh_dump in _system_prompt_text(advisor)
        assert advisor._context_dirty is False

    async def test_short_message_with_tool_call_still_marks_dirty(
        self, monkeypatch
    ):
        """Staleness tracking is unconditional — even a terse instruction
        like 'yes, explore those' that fires a tool marks the context dirty."""
        _install_fake_context(monkeypatch, "unused")

        advisor = Advisor()
        _simulate_tool_calls(monkeypatch, advisor, ["explore"])

        await advisor.chat("yes, explore those")
        assert advisor._context_dirty is True

    async def test_no_refresh_without_graph_mutation(self, monkeypatch):
        """Read-only tools (or no tools) leave the context clean — no
        re-render, no graph read."""
        _install_fake_context(monkeypatch, "should never render")

        advisor = Advisor()
        _simulate_tool_calls(monkeypatch, advisor, ["inspect_node"])

        await advisor.chat(SUBSTANTIVE_MESSAGE)
        assert advisor._context_dirty is False

        await advisor.chat(SUBSTANTIVE_MESSAGE)
        assert "should never render" not in _system_prompt_text(advisor)

    async def test_refresh_failure_is_soft(self, monkeypatch):
        """A crashing DialecticalContext must never break the chat path."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        async def broken(self):
            raise RuntimeError("context exploded")

        monkeypatch.setattr(DialecticalContext, "resolve", broken)

        advisor = Advisor()
        _simulate_tool_calls(monkeypatch, advisor, ["anchor"])

        first = await advisor.chat(SUBSTANTIVE_MESSAGE)
        second = await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert isinstance(first, str)
        assert isinstance(second, str)

    async def test_scoped_advisor_first_turn_renders_scoped_context(
        self, monkeypatch
    ):
        """Scoped construction without a precomputed context starts dirty and
        renders the scoped dump on turn 1."""
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        scoped_dump = "# Nexus [[scoped]] one exploration only"
        _install_fake_context(monkeypatch, scoped_dump)

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="scoped refresh test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(nexus_hash=nexus.hash[:7])
            assert advisor._context_dirty is True

            # Turn 1 begins with this refresh (direct invocation — the
            # mocked submit path wipes message history after it).
            await advisor._refresh_context()
            assert scoped_dump in _system_prompt_text(advisor)
            assert advisor._context_dirty is False
