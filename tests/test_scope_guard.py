"""
Agent chat turns must refuse to run unscoped.

Running a chat turn without `with scope(case.sid):` fails SILENTLY:
nodes save with sid=None (invisible to every sid-scoped repository
listing — work dropped while tool reports claim success), and commit-time
dedup falls back to an unscoped find_by_hash that can alias onto another
Case's nodes. The guard (`require_current_sid`) fails loud at the chat
boundary instead.

Deliberately NOT a BaseNode-level guard: sid-less orphan nodes are a
supported node-layer semantic (see TestOrphanNodes in
test_portable_identifiers.py).

DB-free: the guard raises before any LLM call or graph access.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.analyst import Analyst
from dialectical_framework.exceptions.node_errors import MissingScopeError
from dialectical_framework.graph.scope_context import (require_current_sid,
                                                       scope)


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield  # override: no DB needed


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield  # override: no DB needed


class TestRequireCurrentSid:
    def test_raises_without_scope(self):
        with pytest.raises(MissingScopeError, match="with scope"):
            require_current_sid()

    def test_returns_sid_within_scope(self):
        with scope("test-sid-123"):
            assert require_current_sid() == "test-sid-123"


class TestAgentChatGuard:
    @pytest.mark.asyncio
    async def test_analyst_chat_refuses_unscoped(self):
        analyst = Analyst()
        with pytest.raises(MissingScopeError):
            await analyst.chat("hello")

    @pytest.mark.asyncio
    async def test_analyst_chat_stream_refuses_unscoped(self):
        analyst = Analyst()
        with pytest.raises(MissingScopeError):
            async for _ in analyst.chat_stream("hello"):
                pass

    @pytest.mark.asyncio
    async def test_explorer_chat_refuses_unscoped(self, monkeypatch):
        from dialectical_framework.agents.explorer.explorer import Explorer

        # Explorer's constructor resolves its nexus from the DB — bypass it,
        # the guard under test sits in chat(), not construction.
        explorer = Explorer.__new__(Explorer)
        with pytest.raises(MissingScopeError):
            await explorer.chat("hello")

    @pytest.mark.asyncio
    async def test_advisor_chat_refuses_unscoped(self):
        from dialectical_framework.agents.advisor.advisor import Advisor

        advisor = Advisor(dialectical_context="No prior understanding.")
        with pytest.raises(MissingScopeError):
            await advisor.chat("hello")
