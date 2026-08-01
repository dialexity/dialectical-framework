"""
Tests for the Advisor's static system prompt and one-shot deferred render.

The system prompt is static after its first render: fresh graph state flows
through the conversation (tool results + the model-invoked `sync` tool),
never by rewriting the system prompt — rewrites would bust provider prompt
caching every graph-mutating turn to re-present information the model
already has in history.

The one exception: a nexus-scoped Advisor constructed WITHOUT a precomputed
dialectical_context renders its scoped dump lazily on turn 1 (init is sync,
DialecticalContext.resolve() is async). One-shot — never repeated.
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


@pytest.mark.llm
class TestStaticSystemPrompt:
    async def test_no_rerender_after_graph_mutating_tool(self, monkeypatch):
        """Even when a turn fires a graph-building tool, DialecticalContext
        is never re-rendered — fresh state lives in tool results / sync.
        (Asserted via call-count: the mocked submit path rewrites message
        history, so comparing _messages[0] text is unreliable here.)"""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        render_calls: list[int] = []

        async def counting_context(self):
            render_calls.append(1)
            return "should never render"

        monkeypatch.setattr(DialecticalContext, "resolve", counting_context)

        advisor = Advisor()
        original_submit = advisor._conversation.submit

        async def submit_with_tool_calls(*args, **kwargs):
            result = await original_submit(*args, **kwargs)
            advisor._conversation.last_tool_calls = ["anchor", "explore"]
            return result

        monkeypatch.setattr(
            advisor._conversation, "submit", submit_with_tool_calls
        )

        await advisor.chat(SUBSTANTIVE_MESSAGE)
        await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert render_calls == []

    async def test_unscoped_has_no_pending_render(self):
        advisor = Advisor()
        assert advisor._pending_context_render is False


@pytest.mark.llm
class TestExtraTools:
    """App-provided @llm.tool functions wire in through the constructor —
    the seam through which an app adds domain resources (chart lookups,
    methodology references) alongside the built-in dialectical tools."""

    @staticmethod
    def _make_app_tool():
        from mirascope import llm

        @llm.tool
        async def lookup_natal_chart(person: str) -> str:
            """Look up the natal chart for a person."""
            return f"chart for {person}"

        return lookup_natal_chart

    async def test_extra_tools_appended_to_tool_set(self):
        tool = self._make_app_tool()
        advisor = Advisor(extra_tools=[tool])

        names = [t.__name__ for t in advisor._tools]
        assert "lookup_natal_chart" in names
        # Built-ins all still present
        for builtin in ("ingest", "anchor", "explore", "deepen", "sync"):
            assert builtin in names

    async def test_extra_tools_reach_the_conversation(self):
        tool = self._make_app_tool()
        advisor = Advisor(extra_tools=[tool])
        assert tool in advisor._conversation._tools

    async def test_extra_tools_scoped_mode(self):
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="extra tools scoped test")
            nexus.save()
            nexus.commit()

            tool = self._make_app_tool()
            advisor = Advisor(
                nexus_hash=nexus.hash[:7],
                dialectical_context="dump",
                extra_tools=[tool],
            )

        assert "lookup_natal_chart" in [t.__name__ for t in advisor._tools]

    async def test_extra_tool_shadowing_builtin_rejected(self):
        from mirascope import llm

        @llm.tool
        async def sync() -> str:
            """Impostor sync."""
            return ""

        with pytest.raises(ValueError, match="shadow built-in"):
            Advisor(extra_tools=[sync])

    async def test_engine_prompt_unaffected_by_unknown_tool_names(self):
        """The engine renders docs only for names it knows — an app tool
        must not corrupt or crash the prompt assembly."""
        tool = self._make_app_tool()
        with_extra = Advisor(extra_tools=[tool])
        without = Advisor()
        assert "lookup_natal_chart" not in _system_prompt_text(with_extra)
        assert _system_prompt_text(with_extra) == _system_prompt_text(without)

    async def test_scoped_with_precomputed_context_has_no_pending_render(
        self,
    ):
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="precomputed context test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(
                nexus_hash=nexus.hash[:7],
                dialectical_context="precomputed dump",
            )

        assert advisor._pending_context_render is False
        assert "precomputed dump" in _system_prompt_text(advisor)


@pytest.mark.llm
class TestScopedDeferredRender:
    async def test_scoped_first_turn_renders_scoped_dump_once(
        self, monkeypatch
    ):
        """Scoped construction without a precomputed context renders the
        scoped dump on turn 1 — and only once."""
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        scoped_dump = "# Nexus [[scoped]] one exploration only"
        _install_fake_context(monkeypatch, scoped_dump)

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="deferred render test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(nexus_hash=nexus.hash[:7])
            assert advisor._pending_context_render is True

            await advisor._render_pending_context()
            assert scoped_dump in _system_prompt_text(advisor)
            assert advisor._pending_context_render is False

            # One-shot: a second render changes nothing even if the
            # underlying context differs now.
            _install_fake_context(monkeypatch, "a different dump")
            await advisor._render_pending_context()
            assert "a different dump" not in _system_prompt_text(advisor)

    async def test_deferred_render_transient_failure_retries_next_turn(
        self, monkeypatch
    ):
        """A crashing DialecticalContext must never break the chat path —
        and a TRANSIENT failure keeps the render pending so the next turn
        retries (a turn-1 DB blip must not leave the whole session with a
        prompt claiming rich understanding over an empty slot)."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        async def broken(self):
            raise RuntimeError("context exploded")

        monkeypatch.setattr(DialecticalContext, "resolve", broken)

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="soft failure test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(nexus_hash=nexus.hash[:7])
            reply = await advisor.chat(SUBSTANTIVE_MESSAGE)

            assert isinstance(reply, str)
            # transient failure → still pending, retried next turn
            assert advisor._pending_context_render is True

            # recovery: the next render succeeds and consumes the flag
            # (asserted via direct render — the mocked submit path rewrites
            # message history, making _messages[0] unreliable after chat)
            recovered = "# Nexus [[recovered]] scoped dump"
            _install_fake_context(monkeypatch, recovered)
            await advisor._render_pending_context()
            assert advisor._pending_context_render is False
            assert recovered in _system_prompt_text(advisor)

    async def test_deferred_render_missing_nexus_does_not_retry(
        self, monkeypatch
    ):
        """ValueError (nexus gone) is not transient — consumed, no retry."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        async def gone(self):
            raise ValueError("Nexus not found: whatever")

        monkeypatch.setattr(DialecticalContext, "resolve", gone)

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="gone nexus test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(nexus_hash=nexus.hash[:7])
            reply = await advisor.chat(SUBSTANTIVE_MESSAGE)

            assert isinstance(reply, str)
            assert advisor._pending_context_render is False
