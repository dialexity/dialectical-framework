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

            tools = build_scoped_tools(nexus.hash[:7])
            explore = _tool_by_name(tools, "explore")
            await explore(perspective_hashes=[pp.hash])

            all_nexuses = NexusRepository().find_all()
            assert len(all_nexuses) == 1
            member_ids = {m._id for m, _ in all_nexuses[0].perspectives.all()}
            assert pp._id in member_ids

    def test_scoped_explore_exposes_no_nexus_hash_param(self):
        """The LLM-facing signature must not accept a nexus_hash."""
        import inspect

        tools = build_scoped_tools("abc1234")
        explore = _tool_by_name(tools, "explore")
        params = inspect.signature(explore).parameters
        assert "nexus_hash" not in params
        assert "intent" not in params


class TestScopedDiscard:
    async def test_refuses_perspective_of_another_exploration(self):
        """Members of OTHER explorations are someone's deliverable — refused."""
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            member.nexus.connect(nexus)

            other_nexus = _create_nexus(intent="another exploration")
            outsider = _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )
            outsider.nexus.connect(other_nexus)

            discard = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "discard")
            result = await discard(hash=outsider.hash)

            assert "another" in result and "exploration" in result
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

    async def test_refuses_multi_membership_perspective(self):
        """A perspective in the pinned nexus AND another exploration is
        refused — Discard is global soft-discard and would prune the other
        deliverable too. (Kill the set-difference in _outside_scope_refusal
        and this fails.)"""
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            other_nexus = _create_nexus(intent="second exploration")
            shared = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            shared.nexus.connect(nexus)
            shared.nexus.connect(other_nexus)

            discard = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "discard")
            result = await discard(hash=shared.hash)

            assert "Refused" in result
            assert "also belongs to another" in result

            from dialectical_framework.graph.nodes.perspective import \
                Perspective
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            node = NodeRepository().find_by_hash(
                shared.hash, node_type=Perspective
            )
            assert node is not None
            assert node.discarded is None

    async def test_allows_standalone_perspective(self):
        """A perspective in NO exploration (e.g. this head's own rejected
        anchor) must be retractable — the pin protects explorations, not
        standalone garbage. Regression: previously refused, stranding
        rejected framings permanently."""
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects(
                thesis_text="Control", antithesis_text="Freedom"
            )
            member.nexus.connect(nexus)
            standalone = _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )

            discard = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "discard")
            result = await discard(hash=standalone.hash)

            assert "Refused" not in result

    async def test_allows_perspective_inside_nexus(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects()
            member.nexus.connect(nexus)

            discard = _tool_by_name(build_scoped_tools(nexus.hash[:7]), "discard")
            result = await discard(hash=member.hash)

            assert "outside this exploration" not in result


class TestScopedToolset:
    def test_full_analytical_power_no_ingest(self):
        """Scoped Advisor always carries anchor + pinned explore + deepen
        (it IS Analyst+Explorer behind one voice); only ingest is excluded."""
        tools = build_scoped_tools("abc1234")
        names = {t.__name__ for t in tools}
        assert names == {
            "anchor", "sync", "inspect_node", "read_digest", "discard",
            "explore", "deepen", "record_decision",
        }
        assert "ingest" not in names


class TestScopedDeepen:
    async def test_refuses_wheel_outside_nexus(self):
        """A wheel whose perspectives belong to a DIFFERENT exploration
        cannot be deepened from this counsel head."""
        from dialectical_framework.graph.nodes.cycle import Cycle
        from dialectical_framework.graph.nodes.transition import Transition
        from dialectical_framework.graph.nodes.wheel import Wheel

        sid = _new_sid()
        with scope(sid):
            pinned = _create_nexus("pinned exploration")
            other = _create_nexus("other exploration")

            outsider_pp = _create_perspective_with_aspects(
                thesis_text="Speed", antithesis_text="Thoroughness"
            )
            outsider_pp.nexus.connect(other)

            cycle = Cycle(intent="preset:balanced")
            cycle.set_perspectives([outsider_pp])
            cycle.commit()

            polarity, _ = outsider_pp.polarity.get()
            t_stmt, _ = polarity.t.all()[0]
            a_stmt, _ = polarity.a.all()[0]
            wheel = Wheel(intent="outsider wheel")
            wheel.save()
            tr1 = Transition(nonce="deepen_guard_1")
            tr1.set_source(t_stmt).set_target(a_stmt)
            tr1.commit()
            tr1.cycle.connect(wheel)
            tr2 = Transition(nonce="deepen_guard_2")
            tr2.set_source(a_stmt).set_target(t_stmt)
            tr2.commit()
            tr2.cycle.connect(wheel)
            cycle.wheels.connect(wheel)
            wheel.commit()

            deepen = _tool_by_name(
                build_scoped_tools(pinned.hash[:7]), "deepen"
            )
            result = await deepen(wheel_hash=wheel.hash)
            assert "outside this exploration" in result

    async def test_refuses_non_wheel_hash(self):
        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            pp = _create_perspective_with_aspects()
            pp.nexus.connect(nexus)

            deepen = _tool_by_name(
                build_scoped_tools(nexus.hash[:7]), "deepen"
            )
            result = await deepen(wheel_hash=pp.hash)
            assert "is not a wheel" in result

    async def test_deepens_wheel_inside_nexus(self, monkeypatch):
        """A wheel of the pinned exploration passes the guard and reaches
        run_deepen."""
        from dialectical_framework.agents.explorer.skills import \
            explore_transformations as et_mod
        from dialectical_framework.agents.explorer.skills import \
            generate_synthesis as gs_mod
        from dialectical_framework.graph.nodes.cycle import Cycle
        from dialectical_framework.graph.nodes.transition import Transition
        from dialectical_framework.graph.nodes.wheel import Wheel

        deepened: list[str] = []

        async def stub_transformations(self):
            deepened.append(self.wheel_hash)
            # The real result type: a hand-shaped stand-in only covers what the
            # caller read when it was written, and goes stale silently when the
            # caller reads one field more.
            return et_mod.ExploreTransformationsResult()

        async def stub_synthesis(self):
            return None

        monkeypatch.setattr(
            et_mod.ExploreTransformations, "resolve", stub_transformations
        )
        monkeypatch.setattr(gs_mod.GenerateSynthesis, "resolve", stub_synthesis)

        sid = _new_sid()
        with scope(sid):
            nexus = _create_nexus()
            member = _create_perspective_with_aspects()
            member.nexus.connect(nexus)

            cycle = Cycle(intent="preset:balanced")
            cycle.set_perspectives([member])
            cycle.commit()

            polarity, _ = member.polarity.get()
            t_stmt, _ = polarity.t.all()[0]
            a_stmt, _ = polarity.a.all()[0]
            wheel = Wheel(intent="member wheel")
            wheel.save()
            tr1 = Transition(nonce="deepen_ok_1")
            tr1.set_source(t_stmt).set_target(a_stmt)
            tr1.commit()
            tr1.cycle.connect(wheel)
            tr2 = Transition(nonce="deepen_ok_2")
            tr2.set_source(a_stmt).set_target(t_stmt)
            tr2.commit()
            tr2.cycle.connect(wheel)
            cycle.wheels.connect(wheel)
            wheel.commit()

            deepen = _tool_by_name(
                build_scoped_tools(nexus.hash[:7]), "deepen"
            )
            result = await deepen(wheel_hash=wheel.hash)

            assert deepened == [wheel.hash]
            assert "outside this exploration" not in result
