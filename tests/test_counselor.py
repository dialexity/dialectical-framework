"""
Tests for the Advisor agent.

Verifies:
1. Advisor initialization and tool registration
2. System prompt construction with preamble and dialectical_context
3. Tool set is exactly ingest/anchor/explore/sync/inspect_node/read_digest
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.advisor import Advisor


class TestAdvisorInitialization:
    """Tests for Advisor initialization."""

    def test_tools(self):
        """Test advisor has exactly the seven internal tools."""
        advisor = Advisor()

        tool_names = [t.__name__ for t in advisor._tools]

        assert "ingest" in tool_names
        assert "anchor" in tool_names
        assert "explore" in tool_names
        assert "sync" in tool_names
        assert "inspect_node" in tool_names
        assert "read_digest" in tool_names
        assert "discard" in tool_names
        assert len(tool_names) == 7

    def test_no_analyst_explorer_tools(self):
        """Test advisor does NOT have analyst/explorer tools."""
        advisor = Advisor()

        tool_names = [t.__name__ for t in advisor._tools]

        assert "analyze" not in tool_names
        assert "surface_theses" not in tool_names
        assert "build_wheels" not in tool_names
        assert "present_analysis" not in tool_names
        assert "query_graph" not in tool_names

    def test_messages_loaded_on_init(self):
        """Test messages are loaded when provided."""
        fake_messages = [{"role": "user", "content": "hello"}]
        advisor = Advisor(messages=fake_messages)

        assert len(advisor.messages) >= 1

    def test_system_prompt_includes_preamble(self):
        """Test app_preamble is prepended to system prompt."""
        preamble = "## You are a business coach"
        advisor = Advisor(app_preamble=preamble)

        system_msg = advisor._conversation._messages[0]
        content = system_msg.content.text
        assert preamble in content

    def test_system_prompt_includes_dialectical_context(self):
        """Test dialectical_context is injected into system prompt."""
        context = "## Tensions Identified\n- Trust vs Control"
        advisor = Advisor(dialectical_context=context)

        system_msg = advisor._conversation._messages[0]
        content = system_msg.content.text
        assert "Trust vs Control" in content
        assert "{dialectical_context}" not in content

    def test_system_prompt_default_context_when_none(self):
        """Test default context message when no dialectical_context provided."""
        advisor = Advisor()

        system_msg = advisor._conversation._messages[0]
        content = system_msg.content.text
        assert "No prior understanding" in content
        assert "{dialectical_context}" not in content

    def test_agent_name(self):
        """Test AGENT_NAME is 'advisor'."""
        assert Advisor.AGENT_NAME == "advisor"

    def test_backcompat_constant_matches_default_render(self):
        """SYSTEM_PROMPT constant == system_prompt() default render."""
        from dialectical_framework.agents.advisor.system_prompts import (
            SYSTEM_PROMPT, system_prompt)

        assert SYSTEM_PROMPT == system_prompt()


class TestScopedAdvisor:
    """Nexus-scoped Advisor: scope enforced in code, not prompt."""

    @staticmethod
    def _new_scope_with_nexus():
        """Create a Case + committed Nexus; returns (sid, nexus_hash)."""
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.nexus import Nexus

        case = Case()
        case.commit()
        from dialectical_framework.graph.scope_context import scope

        with scope(case.sid):
            nexus = Nexus(intent="test exploration")
            nexus.save()
            nexus.commit()
            return case.sid, nexus.hash

    def test_raises_on_missing_nexus(self):
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.scope_context import scope

        case = Case()
        case.commit()
        with scope(case.sid):
            with pytest.raises(ValueError, match="Nexus not found"):
                Advisor(nexus_hash="deadbeef")

    def test_scoped_toolset(self):
        """Scoped Advisor keeps full analytical power (anchor + pinned
        explore) — only ingest is excluded (bulk extraction stays unscoped)."""
        from dialectical_framework.graph.scope_context import scope

        sid, nexus_hash = self._new_scope_with_nexus()
        with scope(sid):
            advisor = Advisor(nexus_hash=nexus_hash[:7])

        tool_names = [t.__name__ for t in advisor._tools]
        assert set(tool_names) == {
            "anchor", "sync", "inspect_node", "read_digest", "discard", "explore",
        }
        assert "ingest" not in tool_names

    def test_scoped_prompt_documents_only_wired_tools(self):
        from dialectical_framework.graph.scope_context import scope

        sid, nexus_hash = self._new_scope_with_nexus()
        with scope(sid):
            advisor = Advisor(nexus_hash=nexus_hash[:7])

        content = advisor._conversation._messages[0].content.text
        assert "`ingest`" not in content
        for name in (
            "anchor", "sync", "inspect_node", "read_digest", "discard", "explore",
        ):
            assert f"`{name}`" in content
        # scoped prompt carries the Scope section with the pinned hash
        assert "## Scope" in content
        assert nexus_hash[:7] in content

