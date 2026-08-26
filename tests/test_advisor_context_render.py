"""Tests for the Advisor's per-turn context refresh.

This file used to assert the opposite rule — "the system prompt is static
after its first render" — and the reversal is deliberate, so the old
reasoning is recorded here rather than deleted. It was:

    fresh graph state flows through the conversation (tool results + the
    model-invoked `sync` tool), never by rewriting the system prompt —
    rewrites would bust provider prompt caching every graph-mutating turn to
    re-present information the model already has in history.

Both halves failed in measurement:

1. **"Fresh state flows through the conversation."** It did not reach the
   reply. `probe_readside_reach` measured overlap between the rendered dump
   and the replies written with it: decision ledger 0.56, pathways 0.26,
   synthesis 0.21, and **0 hashes cited across 18 sessions**. Worse, the
   static prompt meant **14 of 18 first sessions built 390 transformations
   while the slot still read `EMPTY_UNDERSTANDING` for all 8 turns** — the
   prompt actively contradicted the history it sat on. Depth then failed to
   predict the score in either direction (corr -0.107 over 36 cells), which
   is what unread structure predicts. And `sync` cannot be the answer: it is
   elective, and across 55 weak-tier runs the model elected `explore` 6
   times. No amount of prompt text makes an elective call reliable.
2. **"Re-present information the model already has."** History carries the
   tool's REPORT. The dump carries derived structure that exists nowhere
   else: perspective indices (T1/A1), scores, validation flags, suppression
   counts.

The caching objection was real, though, and survives as the design: the
refresh re-reads every turn but only REWRITES the prompt when the rendered
dump changed. Unchanged turn → cache intact. A turn that built structure
loses the cache, having just spent tens of seconds in the tool that built it.
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
class TestTheContextIsRereadEveryTurn:
    async def test_an_unscoped_advisor_rereads_the_graph_each_turn(
        self, monkeypatch
    ):
        """The archive's read-side defect, inverted into a guard.

        UNSCOPED is the case that never rendered at all, and it is the case the
        bench's first sessions run in — so this is the test that would have
        caught 390 transformations built against `EMPTY_UNDERSTANDING`.
        Asserted by call count: the mocked submit path rewrites message history,
        so `_messages[0]` is unreliable after `chat`.
        """
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.scope_context import scope

        renders: list[int] = []

        async def counting_context(self):
            renders.append(1)
            # A DIFFERENT dump each time: two turns against one constant string
            # would pass even if the refresh only ever ran once and the second
            # call came from somewhere else.
            return f"# dump revision {len(renders)}"

        monkeypatch.setattr(DialecticalContext, "resolve", counting_context)

        advisor = Advisor()
        with scope("test-advisor-render-sid"):
            await advisor.chat(SUBSTANTIVE_MESSAGE)
            await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert len(renders) == 2, (
            f"{len(renders)} render(s) over two turns — an unscoped Advisor is "
            "back to building structure it cannot read."
        )
        assert advisor._last_context == "# dump revision 2"

    async def test_an_unchanged_dump_does_not_rewrite_the_prompt(
        self, monkeypatch
    ):
        """The caching objection, honoured. Re-READ every turn, re-WRITE only on
        change — so a turn that mutated nothing keeps its prefix cache."""
        from dialectical_framework.graph.scope_context import scope

        _install_fake_context(monkeypatch, "# a dump that never changes")

        advisor = Advisor()
        writes: list[str] = []
        original = advisor._conversation.set_system_prompt

        def counting_set(prompt: str):
            writes.append(prompt)
            return original(prompt)

        monkeypatch.setattr(
            advisor._conversation, "set_system_prompt", counting_set
        )

        with scope("test-advisor-render-sid"):
            await advisor.chat(SUBSTANTIVE_MESSAGE)
            await advisor.chat(SUBSTANTIVE_MESSAGE)
            await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert len(writes) == 1, (
            f"{len(writes)} prompt rewrites for an unchanging graph — every one "
            "after the first busts the provider's prefix cache for nothing."
        )

    async def test_a_changed_dump_does_rewrite_the_prompt(self, monkeypatch):
        from dialectical_framework.graph.scope_context import scope

        _install_fake_context(monkeypatch, "# first")

        advisor = Advisor()
        writes: list[str] = []
        original = advisor._conversation.set_system_prompt

        def counting_set(prompt: str):
            writes.append(prompt)
            return original(prompt)

        monkeypatch.setattr(
            advisor._conversation, "set_system_prompt", counting_set
        )

        with scope("test-advisor-render-sid"):
            await advisor.chat(SUBSTANTIVE_MESSAGE)
            _install_fake_context(monkeypatch, "# second, after a tool wrote")
            await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert len(writes) == 2
        assert "# second, after a tool wrote" in writes[-1]

    async def test_a_precomputed_context_seeds_but_does_not_freeze(
        self, monkeypatch
    ):
        """The half-fix this avoids.

        The e2e driver hands a session-start snapshot on returning sessions and
        nothing on first sessions, then holds it static for all 8 turns. If a
        construction-time context locked the slot, the bench would have kept
        exactly the staleness this change exists to remove.
        """
        from dialectical_framework.graph.scope_context import scope

        advisor = Advisor(dialectical_context="# session-start snapshot")
        assert advisor._last_context == "# session-start snapshot"
        assert "# session-start snapshot" in _system_prompt_text(advisor)

        _install_fake_context(monkeypatch, "# what the graph looks like NOW")
        with scope("test-advisor-render-sid"):
            await advisor.chat(SUBSTANTIVE_MESSAGE)

        assert advisor._last_context == "# what the graph looks like NOW"

    async def test_the_refresh_is_counted_against_the_reply_path(
        self, monkeypatch
    ):
        """The person waits for this read, so it must show up as their seconds.

        A per-turn cost that no record carries is how a framework gets slower
        for no visible reason — and `context_render_s` is deliberately a
        COMPONENT of `reply_path_s`, so the archive's
        `duration_s == reply_path_s + off_path_s` check keeps holding.
        """
        import asyncio

        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.scope_context import scope

        async def slow_context(self):
            await asyncio.sleep(0.05)
            return "# a dump that took a moment"

        monkeypatch.setattr(DialecticalContext, "resolve", slow_context)

        advisor = Advisor()
        with scope("test-advisor-render-sid"):
            await advisor.chat(SUBSTANTIVE_MESSAGE)

        timing = advisor.last_turn_timing
        assert timing is not None
        assert timing.context_render_s >= 0.05
        # Inside the reply path, not beside it.
        assert timing.reply_path_s >= timing.context_render_s


@pytest.mark.llm
class TestAppTools:
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

    async def test_app_tools_appended_to_tool_set(self):
        tool = self._make_app_tool()
        advisor = Advisor(app_tools=[tool])

        names = [t.__name__ for t in advisor._tools]
        assert "lookup_natal_chart" in names
        # Built-ins all still present
        for builtin in ("ingest", "anchor", "explore", "deepen", "sync"):
            assert builtin in names

    async def test_app_tools_reach_the_conversation(self):
        tool = self._make_app_tool()
        advisor = Advisor(app_tools=[tool])
        assert tool in advisor._conversation._tools

    async def test_app_tools_scoped_mode(self):
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="app tools scoped test")
            nexus.save()
            nexus.commit()

            tool = self._make_app_tool()
            advisor = Advisor(
                nexus_hash=nexus.hash[:7],
                dialectical_context="dump",
                app_tools=[tool],
            )

        assert "lookup_natal_chart" in [t.__name__ for t in advisor._tools]

    async def test_extra_tool_shadowing_builtin_rejected(self):
        from mirascope import llm

        @llm.tool
        async def sync() -> str:
            """Impostor sync."""
            return ""

        with pytest.raises(ValueError, match="shadow built-in"):
            Advisor(app_tools=[sync])

    async def test_engine_prompt_unaffected_by_unknown_tool_names(self):
        """The engine renders docs only for names it knows — an app tool
        must not corrupt or crash the prompt assembly."""
        tool = self._make_app_tool()
        with_extra = Advisor(app_tools=[tool])
        without = Advisor()
        assert "lookup_natal_chart" not in _system_prompt_text(with_extra)
        assert _system_prompt_text(with_extra) == _system_prompt_text(without)

    async def test_scoped_with_precomputed_context_renders_it_immediately(
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

        assert advisor._last_context == "precomputed dump"
        assert "precomputed dump" in _system_prompt_text(advisor)


@pytest.mark.llm
class TestScopedRefresh:
    async def test_a_scoped_advisor_sees_its_exploration_change(
        self, monkeypatch
    ):
        """Scoped used to render once, so anything built on turn 3 was invisible
        from turn 4 on. Counsel mode is exactly where that hurts: the person is
        debriefing a deliverable they are still editing."""
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        _install_fake_context(monkeypatch, "# Nexus [[scoped]] as first read")

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="refresh render test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(nexus_hash=nexus.hash[:7])
            await advisor._refresh_context()
            assert "# Nexus [[scoped]] as first read" in _system_prompt_text(
                advisor
            )

            # The exploration moved. The next turn must see it.
            _install_fake_context(monkeypatch, "# Nexus [[scoped]] now deeper")
            await advisor._refresh_context()
            assert "# Nexus [[scoped]] now deeper" in _system_prompt_text(advisor)

    async def test_a_transient_failure_keeps_the_last_good_context(
        self, monkeypatch
    ):
        """A crashing DialecticalContext must never break the chat path, and
        must never downgrade the prompt to `EMPTY_UNDERSTANDING` — that would
        throw away understanding the conversation already has."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="soft failure test")
            nexus.save()
            nexus.commit()

            good = "# Nexus [[good]] understanding worth keeping"
            _install_fake_context(monkeypatch, good)
            advisor = Advisor(nexus_hash=nexus.hash[:7])
            await advisor._refresh_context()

            async def broken(self):
                raise RuntimeError("context exploded")

            monkeypatch.setattr(DialecticalContext, "resolve", broken)
            reply = await advisor.chat(SUBSTANTIVE_MESSAGE)

            assert isinstance(reply, str)  # the turn survived
            # Kept, not blanked, and still eligible to retry next turn.
            assert advisor._last_context == good
            assert advisor._context_refresh_enabled is True

            recovered = "# Nexus [[recovered]] scoped dump"
            _install_fake_context(monkeypatch, recovered)
            await advisor._refresh_context()
            assert recovered in _system_prompt_text(advisor)

    async def test_a_vanished_nexus_stops_the_retrying(self, monkeypatch):
        """ValueError (nexus gone) is not transient. Re-reading it every turn
        would buy a guaranteed failure on the person's wait, forever."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            nexus = Nexus(intent="gone nexus test")
            nexus.save()
            nexus.commit()

            advisor = Advisor(
                nexus_hash=nexus.hash[:7],
                dialectical_context="# what we had before it vanished",
            )

            calls: list[int] = []

            async def gone(self):
                calls.append(1)
                raise ValueError("Nexus not found: whatever")

            monkeypatch.setattr(DialecticalContext, "resolve", gone)

            reply = await advisor.chat(SUBSTANTIVE_MESSAGE)
            assert isinstance(reply, str)
            assert advisor._context_refresh_enabled is False

            await advisor.chat(SUBSTANTIVE_MESSAGE)
            assert len(calls) == 1, "kept re-reading a nexus that is gone"
            # The prompt still carries what it had — no silent downgrade.
            assert advisor._last_context == "# what we had before it vanished"
