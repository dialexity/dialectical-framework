"""
Tests for the nexus-scoped Advisor tool factory (tools/scoped.py).

The invariant under test: scope is enforced IN CODE. The pinned nexus hash is
closed over by the tools — the LLM cannot create sibling nexuses (no
nexus_hash/intent parameters exposed) and cannot discard perspectives outside
the exploration.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.tools.scoped import \
    build_scoped_tools
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.repositories.nexus_repository import \
    NexusRepository
from dialectical_framework.graph.scope_context import scope

# Reuse the committed-perspective helper from the context tests.
from test_dialectical_context import _create_perspective_with_aspects


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _create_nexus(intent: str = "scoped tools test") -> Nexus:
    nexus = Nexus(intent=intent)
    nexus.save()
    nexus.commit()
    return nexus


def _tool_by_name(tools: list, name: str):
    return next(t for t in tools if t.__name__ == name)


class TestScopedSync:
    async def test_scoped_sync_pinned_to_nexus(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            member.nexus.connect(nexus)
            _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )

            sync = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "sync")
            dump = await sync()

            assert "Control" in dump
            assert "Speed" not in dump


class TestScopedExplore:
    async def test_scoped_explore_cannot_create_sibling_nexus(self, monkeypatch):
        """explore always expands the pinned nexus — CreateNexus unreachable."""
        from dialectical_framework.agents.explorer.explorer import (
            ExplorationPipeline, ExplorationResult)

        async def stub_pipeline(self):
            return ExplorationResult(nexus_hash=self.nexus_hash)

        monkeypatch.setattr(ExplorationPipeline, "resolve", stub_pipeline)

        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            pp = _create_perspective_with_aspects()

            tools = build_scoped_tools(nexus.hash[:7], enrichment=True)
            explore = _tool_by_name(tools, "explore")
            await explore(perspective_hashes=[pp.hash])

            all_nexuses = NexusRepository().find_all()
            assert len(all_nexuses) == 1
            member_ids = {m._id for m, _ in all_nexuses[0].perspectives.all()}
            assert pp._id in member_ids

    def test_scoped_explore_exposes_no_nexus_hash_param(self):
        """The LLM-facing signature must not accept a nexus_hash."""
        import inspect

        tools = build_scoped_tools("abc1234", enrichment=True)
        explore = _tool_by_name(tools, "explore")
        params = inspect.signature(explore).parameters
        assert "nexus_hash" not in params
        assert "intent" not in params


class TestScopedDiscard:
    async def test_refuses_perspective_outside_nexus(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            member.nexus.connect(nexus)
            outsider = _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )

            discard = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "discard")
            result = await discard(hash=outsider.hash)

            assert "outside this exploration" in result
            # node untouched
            from dialectical_framework.graph.nodes.perspective import \
                Perspective
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            node = NodeRepository().find_by_hash(
                outsider.hash, node_type=Perspective
            )
            assert node is not None
            assert node.discarded is None

    async def test_allows_perspective_inside_nexus(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects()
            member.nexus.connect(nexus)

            discard = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "discard")
            result = await discard(hash=member.hash)

            assert "outside this exploration" not in result


class TestScopedToolsets:
    def test_read_mostly_default(self):
        tools = build_scoped_tools("abc1234")
        names = {t.__name__ for t in tools}
        assert names == {"sync", "inspect_node", "read_digest", "discard"}

    def test_enrichment_adds_anchor_and_explore(self):
        tools = build_scoped_tools("abc1234", enrichment=True)
        names = {t.__name__ for t in tools}
        assert names == {
            "anchor", "sync", "inspect_node", "read_digest", "discard", "explore",
        }
        assert "ingest" not in names
