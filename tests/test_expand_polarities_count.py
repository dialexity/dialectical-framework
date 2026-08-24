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


@pytest.mark.llm
class TestAspectsNeverDedupIntoTheirOwnPoles:
    """An aspect must not be replaced by the T or A it develops.

    Rule 1 requires the four aspects to be distinct from the poles: T- is what
    T degenerates into when A+ is absent, not T itself. But an aspect is a
    development OF a pole, so it is by construction the most similar thing in
    the graph to that pole — and the aspect deduplicator was handed the full
    vocabulary, poles included. It then did exactly what it is built to do.

    Measured: a live weak-tier run recorded an `accepted_cost` on a Statement
    sitting at `T/T-` — one node serving as both the neutral thesis and its own
    overdevelopment. Same signature in `claim2-weak-r4` (`T/T-` on f142e3c).

    A collapsed tetrad breaks every consumer that reads the positions apart:
    the control statement degenerates to "T without A+ yields T", the diagonal
    contradictions vanish, `area`/`rectangularity` compare an aspect to itself,
    and a decision's accepted cost names the CHOICE instead of its price.
    """

    @pytest.mark.asyncio
    async def test_poles_are_excluded_from_the_aspect_dedup_vocabulary(
        self, monkeypatch
    ):
        from dialectical_framework.concerns.statement_deduplication import \
            StatementDeduplication

        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            t_node, _ = polarity.t.get()
            a_node, _ = polarity.a.get()

            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            offered: list[list[str]] = []

            async def _capture(self, *, extracted_hashes, vocabulary, text=""):
                offered.append([v["hash"] for v in vocabulary])
                from dialectical_framework.concerns.statement_deduplication import \
                    DedupResult

                return DedupResult(
                    replacements={}, deleted_count=0, originals=[]
                )

            monkeypatch.setattr(StatementDeduplication, "resolve", _capture)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            await concern.resolve()

            assert offered, "the aspect deduplicator was never consulted"
            for vocab_hashes in offered:
                assert t_node.hash not in vocab_hashes, (
                    "T was offered as a dedup target for its own tetrad's "
                    "aspects — an aspect can collapse into the pole it develops"
                )
                assert a_node.hash not in vocab_hashes, (
                    "A was offered as a dedup target for its own tetrad's "
                    "aspects — an aspect can collapse into the pole it develops"
                )

    @pytest.mark.asyncio
    async def test_committed_tetrad_keeps_aspects_distinct_from_poles(
        self, monkeypatch
    ):
        """The invariant itself, read off the committed graph.

        Asserted on the real dedup path (not stubbed) so it covers the whole
        chain, not just what the vocabulary filter was handed.
        """
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            t_node, _ = polarity.t.get()
            a_node, _ = polarity.a.get()
            pole_hashes = {t_node.hash, a_node.hash}

            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert pps
            for pp in pps:
                for position in (
                    POSITION_T_PLUS,
                    POSITION_T_MINUS,
                    POSITION_A_PLUS,
                    POSITION_A_MINUS,
                ):
                    manager = pp.get_relationship_manager_by_position(position)
                    for aspect, _rel in manager.all():
                        assert aspect.hash not in pole_hashes, (
                            f"{position} is the same node as a pole of its own "
                            f"tetrad: {aspect.text!r}"
                        )


@pytest.mark.llm
class TestExpandPolarityResumesAnInterruptedTetrad:
    """A crash mid-expansion must be finishable, not duplicated.

    `ExpandPolarity` creates the Perspective first (`save()`, uncommitted) and
    only then generates its four aspects, so a failure in between leaves a
    partial tetrad in the graph. `find_by_polarity` deliberately omits the
    committed-only filter precisely so the next call can SEE that partial and
    complete it — and `additional_needed = count - len(partial_pps)` means the
    survivor counts toward `count` instead of being joined by a fresh sibling.

    Both halves are pinned here because the resume path is invisible in normal
    use (it only fires after a failure) and nothing else in the suite exercises
    it: a regression would silently start producing a duplicate half-tetrad per
    interrupted run, and the orphan would keep the polarity looking developed.
    """

    @pytest.mark.asyncio
    async def test_partial_is_completed_and_counts_toward_count(self, monkeypatch):
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)

            # First run dies during aspect generation — after the Perspective
            # node was saved.
            async def _boom(self, perspective, positions=None, text="", not_like_these=None):
                raise RuntimeError("session closed mid-generation")

            monkeypatch.setattr(AspectGeneration, "resolve", _boom)
            with pytest.raises(RuntimeError):
                await ExpandPolarity(polarity_hash=polarity.hash).resolve()

            pp_repo = PerspectiveRepository()
            orphans = pp_repo.find_by_polarity(polarity)
            assert len(orphans) == 1
            assert not orphans[0].is_complete()
            assert not orphans[0].is_committed  # the interrupted state

            # Second run resumes it.
            stub, call_index = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert len(pps) == 1
            assert call_index["n"] == 1  # one generation, not two
            assert concern.report.artifacts["new_count"] == 1
            assert pps[0].is_complete() and pps[0].is_committed
            # The partial was completed in place, not abandoned beside a sibling.
            assert len(pp_repo.find_by_polarity(polarity)) == 1

    @pytest.mark.asyncio
    async def test_partial_absorbs_one_of_a_larger_count(self, monkeypatch):
        """`count=2` over one survivor generates one more, not two."""
        from dialectical_framework.graph.repositories.perspective_repository import \
            PerspectiveRepository

        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)

            async def _boom(self, perspective, positions=None, text="", not_like_these=None):
                raise RuntimeError("session closed mid-generation")

            monkeypatch.setattr(AspectGeneration, "resolve", _boom)
            with pytest.raises(RuntimeError):
                await ExpandPolarity(polarity_hash=polarity.hash, count=2).resolve()

            stub, call_index = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash, count=2)
            pps = await concern.resolve()

            assert len(pps) == 2
            assert call_index["n"] == 2
            assert len({pp.hash for pp in pps}) == 2
            assert len(PerspectiveRepository().find_by_polarity(polarity)) == 2
