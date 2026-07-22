"""
Tests for ExpandPolarity's `count` parameter (batch tetrad generation).

`count > 1` must produce that many distinct Perspectives in a single call,
each generated sequentially so it can avoid the tetrads produced earlier in
the same call (`not_like_these`).

The mock brain auto-constructs identical aspect DTOs on every call, so a real
LLM path would collapse `count=2` into one Perspective via the duplicate-discard
guard. To exercise the count loop deterministically, we stub AspectGeneration to
emit distinct aspects per invocation and assert on ExpandPolarity's own
orchestration (loop count, not_like_these threading, dedup, commit).
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              AspectResult)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

# Arbitrary taxonomy pointers — Statement.commit() requires a non-empty meaning.
_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"
_ASPECT_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence"


def _make_polarity(sid: str) -> Polarity:
    """Create and commit a Polarity (T-A pair) in the given scope."""
    with scope(sid):
        t = Statement(text="Love", meaning=_T_MEANING)
        t.commit()
        a = Statement(text="Indifference", meaning=_A_MEANING)
        a.commit()

        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        return polarity


def _distinct_aspect_stub(sid: str):
    """Return an AspectGeneration.resolve stub that emits distinct aspects per call.

    Each invocation produces a fresh set of four aspects whose text is suffixed
    with a monotonic counter, so successive Perspectives never collide on hash
    (and thus are not discarded as duplicates).
    """
    call_index = {"n": 0}

    async def _resolve(self, perspective, positions=None, text="", not_like_these=None):
        # Record how many prior tetrads this call was asked to differ from.
        self._seen_not_like_these = len(not_like_these or [])
        i = call_index["n"]
        call_index["n"] += 1

        with scope(sid):
            results: list[AspectResult] = []
            for pos, label in (
                (POSITION_T_PLUS, "Bonding"),
                (POSITION_T_MINUS, "Enmeshment"),
                (POSITION_A_PLUS, "Autonomy"),
                (POSITION_A_MINUS, "Alienation"),
            ):
                comp = Statement(text=f"{label} v{i}", meaning=_ASPECT_MEANING)
                comp.commit()
                results.append(
                    AspectResult(
                        component=comp,
                        position=pos,
                        apex_concept="apex",
                        heuristic_similarity=0.8,
                        complementarity_t=0.7,
                        complementarity_a=0.7,
                    )
                )
        return results

    return _resolve, call_index


@pytest.mark.llm
class TestExpandPolarityCount:
    """ExpandPolarity honors the `count` parameter."""

    @pytest.mark.asyncio
    async def test_default_count_creates_one_perspective(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)

            stub, call_index = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert len(pps) == 1
            assert call_index["n"] == 1
            assert concern.report.artifacts["new_count"] == 1
            assert all(pp.is_complete() and pp.is_committed for pp in pps)

    @pytest.mark.asyncio
    async def test_count_generates_multiple_distinct_perspectives(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)

            stub, call_index = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash, count=3)
            pps = await concern.resolve()

            # Three distinct, complete, committed perspectives.
            assert len(pps) == 3
            assert call_index["n"] == 3
            assert concern.report.artifacts["new_count"] == 3
            assert len({pp.hash for pp in pps}) == 3
            assert all(pp.is_complete() and pp.is_committed for pp in pps)

    @pytest.mark.asyncio
    async def test_count_threads_prior_tetrads_into_not_like_these(self, monkeypatch):
        """Each sequential generation must see the previously completed tetrads."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)

            seen_counts: list[int] = []
            call_index = {"n": 0}

            async def _resolve(
                self, perspective, positions=None, text="", not_like_these=None
            ):
                seen_counts.append(len(not_like_these or []))
                i = call_index["n"]
                call_index["n"] += 1
                with scope(case_node.sid):
                    results: list[AspectResult] = []
                    for pos, label in (
                        (POSITION_T_PLUS, "Bonding"),
                        (POSITION_T_MINUS, "Enmeshment"),
                        (POSITION_A_PLUS, "Autonomy"),
                        (POSITION_A_MINUS, "Alienation"),
                    ):
                        comp = Statement(text=f"{label} v{i}", meaning=_ASPECT_MEANING)
                        comp.commit()
                        results.append(
                            AspectResult(
                                component=comp,
                                position=pos,
                                apex_concept="apex",
                                heuristic_similarity=0.8,
                                complementarity_t=0.7,
                                complementarity_a=0.7,
                            )
                        )
                return results

            monkeypatch.setattr(AspectGeneration, "resolve", _resolve)

            concern = ExpandPolarity(polarity_hash=polarity.hash, count=3)
            await concern.resolve()

            # 1st gen sees 0 prior tetrads, 2nd sees 1, 3rd sees 2.
            assert seen_counts == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_count_zero_clamps_to_one(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)

            stub, call_index = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash, count=0)
            pps = await concern.resolve()

            assert len(pps) == 1
            assert call_index["n"] == 1
