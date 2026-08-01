"""
Tests for the live PerspectiveValidation wiring (task #4).

ExpandPolarity runs PerspectiveValidation after committing each new tetrad
and persists the verdict on Perspective.validation (metadata, hash-neutral,
non-blocking). The flag is rendered by dialectical_context, present_analysis
and inspect_node; a failed perspective stays usable but deprioritized.
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.control_statements_check import \
    ControlStatementsCheckResult
from dialectical_framework.concerns.perspective_validation import (
    EmpiricalInequalitiesResult, PerspectiveValidation,
    PerspectiveValidationResult)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.estimation import (
    ConceptualCoherenceEstimation, DialecticalValidityEstimation)
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.scope_context import scope
from test_dialectical_context import _create_perspective_with_aspects


def _new_sid() -> str:
    case = Case()
    case.commit()
    assert case.sid is not None
    return case.sid


def _fake_validation_result(
    coherent: bool, ei_valid: bool, reasons: list[str] | None = None
) -> PerspectiveValidationResult:
    score = 0.9 if coherent else 0.3
    estimation = ConceptualCoherenceEstimation(
        value=score,
        t_plus_without_a_plus_yields_t_minus=score,
        a_plus_without_t_plus_yields_a_minus=score,
    )
    dv_estimation = DialecticalValidityEstimation(
        value=score,
        t_plus_without_a_plus_yields_t_minus=score,
        a_plus_without_t_plus_yields_a_minus=score,
    )
    cs = ControlStatementsCheckResult(
        estimation=estimation,
        dv_estimation=dv_estimation,
        rationale=Rationale(text="stub"),
        t_plus_without_a_plus_yields_t_minus_statement="s1",
        t_plus_without_a_plus_yields_t_minus_score=score,
        t_plus_without_a_plus_yields_t_minus_reasoning="r1",
        a_plus_without_t_plus_yields_a_minus_statement="s2",
        a_plus_without_t_plus_yields_a_minus_score=score,
        a_plus_without_t_plus_yields_a_minus_reasoning="r2",
        t_plus_without_a_plus_yields_t_minus_dv=score,
        a_plus_without_t_plus_yields_a_minus_dv=score,
    )
    ei = EmpiricalInequalitiesResult(
        is_valid=ei_valid, failure_reasons=list(reasons or [])
    )
    return PerspectiveValidationResult(
        control_statements=cs,
        empirical_inequalities=ei,
        failure_reasons=list(reasons or []),
    )


def _patch_validation(monkeypatch, result_or_exc):
    async def stub(self, perspective, text=""):
        if isinstance(result_or_exc, Exception):
            raise result_or_exc
        return result_or_exc

    monkeypatch.setattr(PerspectiveValidation, "resolve", stub)


async def _expand(monkeypatch) -> Perspective:
    """Run ExpandPolarity over a fresh polarity; return the new perspective."""
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        ExpandPolarity
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.nodes.statement import Statement

    t = Statement(text="Discipline", meaning="test")
    t.commit()
    a = Statement(text="Spontaneity", meaning="test")
    a.commit()
    polarity = Polarity()
    polarity.set_t(t, heuristic_similarity=1.0)
    polarity.set_a(a, heuristic_similarity=0.8)
    polarity.commit()

    concern = ExpandPolarity(polarity_hash=polarity.hash)
    pps = await concern.resolve()
    assert len(pps) == 1
    return pps[0]


@pytest.mark.llm
class TestValidationWiring:
    async def test_passing_tetrad_flagged_passed(self, monkeypatch):
        _patch_validation(
            monkeypatch, _fake_validation_result(coherent=True, ei_valid=True)
        )
        sid = _new_sid()
        with scope(sid):
            pp = await _expand(monkeypatch)
            assert pp.validation == "passed"
            # persisted, not just in-memory
            reloaded = NodeRepository().find_by_hash(
                pp.hash, node_type=Perspective
            )
            assert reloaded.validation == "passed"

    async def test_failing_tetrad_flagged_with_reasons_but_kept(
        self, monkeypatch
    ):
        _patch_validation(
            monkeypatch,
            _fake_validation_result(
                coherent=False,
                ei_valid=False,
                reasons=["Conceptual coherence failed: ..."],
            ),
        )
        sid = _new_sid()
        with scope(sid):
            pp = await _expand(monkeypatch)
            assert pp.validation is not None
            assert pp.validation.startswith("failed:")
            assert "Conceptual coherence" in pp.validation
            # non-blocking: perspective committed and not discarded
            assert pp.is_committed
            assert pp.discarded is None

    async def test_inconclusive_ei_with_coherent_cc_stays_unvalidated(
        self, monkeypatch
    ):
        """Missing complementarity data + CC held → inconclusive, not failed."""
        _patch_validation(
            monkeypatch,
            _fake_validation_result(coherent=True, ei_valid=None),
        )
        sid = _new_sid()
        with scope(sid):
            pp = await _expand(monkeypatch)
            assert pp.validation is None

    async def test_validator_crash_is_soft(self, monkeypatch):
        _patch_validation(monkeypatch, RuntimeError("validator exploded"))
        sid = _new_sid()
        with scope(sid):
            pp = await _expand(monkeypatch)
            assert pp.validation is None
            assert pp.is_committed

    async def test_verdicts_land_in_report_artifacts(self, monkeypatch):
        from dialectical_framework.agents.analyst.skills.expand_polarities import \
            ExpandPolarity
        from dialectical_framework.graph.nodes.polarity import Polarity
        from dialectical_framework.graph.nodes.statement import Statement

        _patch_validation(
            monkeypatch, _fake_validation_result(coherent=True, ei_valid=True)
        )
        sid = _new_sid()
        with scope(sid):
            t = Statement(text="Order", meaning="test")
            t.commit()
            a = Statement(text="Chaos", meaning="test")
            a.commit()
            polarity = Polarity()
            polarity.set_t(t, heuristic_similarity=1.0)
            polarity.set_a(a, heuristic_similarity=0.8)
            polarity.commit()

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            await concern.resolve()

            summary = concern.report.artifacts.get("validation")
            assert summary and summary[0]["validation"] == "passed"


class TestValidationRendering:
    """The flag must be visible everywhere the LLM reads perspectives."""

    def _flagged_perspective(self, verdict: str) -> Perspective:
        pp = _create_perspective_with_aspects()
        pp.validation = verdict
        pp.save()
        return pp

    @pytest.mark.asyncio
    async def test_dialectical_context_renders_verdict_for_nexus_members(self):
        """A failed STANDALONE perspective is suppressed outright by the
        quality filter (task #5); nexus members are load-bearing and stay
        visible WITH their verdict line — that's where the flag renders."""
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.nodes.nexus import Nexus

        sid = _new_sid()
        with scope(sid):
            pp = self._flagged_perspective("failed: Differential minimum: ...")
            nexus = Nexus(intent="verdict rendering")
            nexus.save()
            nexus.commit()
            pp.nexus.connect(nexus)

            dump = await DialecticalContext().resolve()
            assert "Validation: failed" in dump

    @pytest.mark.asyncio
    async def test_dialectical_context_suppresses_failed_standalone(self):
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        sid = _new_sid()
        with scope(sid):
            self._flagged_perspective("failed: Differential minimum: ...")
            dump = await DialecticalContext().resolve()
            assert "Validation: failed" not in dump
            assert "suppressed" in dump

    @pytest.mark.asyncio
    async def test_present_analysis_renders_verdict(self):
        from dialectical_framework.agents.orchestrator.tools.present_analysis import \
            PresentAnalysis

        sid = _new_sid()
        with scope(sid):
            self._flagged_perspective("passed")
            out = await PresentAnalysis().resolve()
            assert "[validation: passed]" in out

    @pytest.mark.asyncio
    async def test_inspect_node_renders_verdict(self):
        from dialectical_framework.agents.orchestrator.tools.inspect_node import \
            InspectNode

        sid = _new_sid()
        with scope(sid):
            pp = self._flagged_perspective("passed")
            out = await InspectNode().resolve(node_hash=pp.hash)
            assert "Validation: passed" in out

    @pytest.mark.asyncio
    async def test_unvalidated_perspective_renders_no_flag(self):
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()
            dump = await DialecticalContext().resolve()
            assert "Validation:" not in dump


class TestMechanicalOppositionRendering:
    """SIMPLE-path antitheses carry hardcoded HS=1.0 — the dump must render
    them as mechanical opposition, not as a fake perfect score."""

    @pytest.mark.asyncio
    async def test_evaluated_antithesis_still_shows_numeric_hs(self):
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        sid = _new_sid()
        with scope(sid):
            _create_perspective_with_aspects()  # COMPLEX-style, HS=0.8
            dump = await DialecticalContext().resolve()
            assert "HS=0.80" in dump
            assert "mechanical opposition" not in dump

    @pytest.mark.asyncio
    async def test_mechanical_label_replaces_score(self):
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS,
            POSITION_T_PLUS)
        from dialectical_framework.graph.nodes.polarity import Polarity
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.relationships.polarity_relationship import (
            AMinusRelationship, APlusRelationship, HasPolarityRelationship,
            TMinusRelationship, TPlusRelationship)

        sid = _new_sid()
        with scope(sid):
            t = Statement(text="Presence", meaning="test")
            t.commit()
            # SIMPLE-path marker → mechanical negation, hardcoded HS=1.0
            a = Statement(text="Not-presence", meaning="dx://taxonomy/Simple")
            a.commit()
            polarity = Polarity()
            polarity.set_t(t, heuristic_similarity=1.0)
            polarity.set_a(a, heuristic_similarity=1.0)
            polarity.commit()

            pp = Perspective()
            pp.save()
            pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
            for text, rel_cls, alias in [
                ("Groundedness", TPlusRelationship, POSITION_T_PLUS),
                ("Clinging", TMinusRelationship, POSITION_T_MINUS),
                ("Freedom", APlusRelationship, POSITION_A_PLUS),
                ("Drift", AMinusRelationship, POSITION_A_MINUS),
            ]:
                s = Statement(text=text, meaning="test")
                s.commit()
                manager = getattr(
                    pp,
                    {
                        POSITION_T_PLUS: "t_plus",
                        POSITION_T_MINUS: "t_minus",
                        POSITION_A_PLUS: "a_plus",
                        POSITION_A_MINUS: "a_minus",
                    }[alias],
                )
                manager.connect(
                    s, relationship=rel_cls(alias=alias, heuristic_similarity=0.8)
                )
            pp.commit()

            dump = await DialecticalContext().resolve()
            assert "mechanical opposition" in dump
            assert '"Not-presence" (HS=' not in dump
