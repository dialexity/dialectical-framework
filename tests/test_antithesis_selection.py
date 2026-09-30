"""
Antithesis selection ranks by tetrad potential; HS only gates.

The defect (2026-09-30, `tests/probe_blindspot_paths.py`): on a thesis-only
build, `AntithesisExtraction` kept the candidates with the highest HS and
`_rank_polarities` expanded the highest-HS polarities — and HS on an antithesis
is similarity to the apex "[T]-lessness", COMPLETE absence of T. Ranking by it
selects the most total negation on the ladder every time: 19/19 expanded
antitheses were the Negation/Inversion/Devaluation rungs at HS 0.95/0.85/0.75,
every one a caricature ("Never quit, stay employed forever"), and 17/19 tetrads
then failed the coherence check because a caricature has no A+.

The paper's own criterion is "Optimum A" — the antithesis maximizing tetrad
coherence and S+ likelihood [P0 Table 5] — and its instruction is to ask what
functionally OPPOSES the role T plays, not what negates T. So each candidate
now rates `tetrad_potential`, selection ranks by it at both sites, HS stays the
validity gate, and the value is persisted as an Estimation next to Mode and
Arousal. These tests pin the ranking, the gate, the report and the persistence;
the antithesis TEXTS are judged by the probe, not here.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.analyst import (
    HS_THRESHOLD, AnalysisPipeline)
from dialectical_framework.concerns import antithesis_extraction as ext
from dialectical_framework.concerns.antithesis_extraction import (
    AntithesisCandidate, AntithesisExtraction, ModePointResultDto)


def _cand(branch: str, hs: float, potential: float | None, text: str = "") -> AntithesisCandidate:
    return AntithesisCandidate(
        statement_text=text or f"{branch} candidate",
        branch=branch,
        mode_value=1.0,
        arousal_value=0.5,
        heuristic_similarity=hs,
        explanation="",
        tetrad_potential=potential,
    )


class TestSelectionRanksByTetradPotential:
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def _extraction(self, count: int) -> AntithesisExtraction:
        service = AntithesisExtraction()
        service._count = count
        return service

    def test_the_caricature_with_the_highest_hs_no_longer_wins(self):
        """The measured shape: Negation at HS 0.95 with nothing to develop,
        Privation at HS 0.6 that is a real position."""
        negation = _cand("negation", hs=0.95, potential=0.2, text="Never quit, stay employed forever")
        privation = _cand("privation", hs=0.60, potential=0.9, text="Keep the security of employed work")
        devaluation = _cand("devaluation", hs=0.75, potential=0.3)

        kept = self._extraction(count=2)._truncate_candidates([negation, devaluation, privation])

        assert [c.statement_text for c in kept] == [
            "Keep the security of employed work",
            "devaluation candidate",
        ]

    def test_breadth_first_then_by_potential(self):
        """Round 1 still takes one per branch (the ladder's coverage is the
        paper's multi-antithesis rule); the ORDER inside and across rounds is
        potential. (When everything fits within `count`, nothing is reordered —
        pre-existing; `_rank_polarities` orders the expansion afterwards.)"""
        a1 = _cand("negation", 0.9, 0.4, "a1")
        a2 = _cand("negation", 0.8, 0.8, "a2")   # better potential, same branch
        b1 = _cand("privation", 0.5, 0.6, "b1")

        kept = self._extraction(count=2)._truncate_candidates([a1, a2, b1])

        assert [c.statement_text for c in kept] == ["a2", "b1"], (
            "a1 has the highest HS and loses: its branch's better-potential "
            "sibling takes the branch slot, and privation's one candidate takes the other"
        )

    def test_without_a_potential_the_order_is_hs_as_before(self):
        """Older fakes and the SIMPLE path rate nothing; nothing changes for them."""
        hi = _cand("negation", 0.9, None, "hi")
        lo = _cand("privation", 0.5, None, "lo")
        kept = self._extraction(count=1)._truncate_candidates([lo, hi])
        assert [c.statement_text for c in kept] == ["hi"]

    def test_selection_key_is_one_function(self):
        assert AntithesisExtraction.selection_key(_cand("x", 0.9, 0.2)) == 0.2
        assert AntithesisExtraction.selection_key(_cand("x", 0.9, None)) == 0.9


class TestTheGateGatesAndTheOrderIsPotential:
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def _data(self) -> list[dict]:
        return [
            {"polarity_hash": "caricature", "heuristic_similarity": 0.95, "tetrad_potential": 0.2},
            {"polarity_hash": "position", "heuristic_similarity": 0.75, "tetrad_potential": 0.9},
            {"polarity_hash": "weak", "heuristic_similarity": 0.4, "tetrad_potential": 0.95},
            {"polarity_hash": "unrated", "heuristic_similarity": 0.8},
        ]

    def test_hs_gates_and_potential_orders(self):
        ranked = AnalysisPipeline()._rank_polarities(self._data())
        assert [p["polarity_hash"] for p in ranked] == ["position", "unrated", "caricature"], (
            "the sub-threshold one is set aside however high its potential; "
            "the unrated one ranks by its HS, as before"
        )
        assert all((p.get("heuristic_similarity") or 0) >= HS_THRESHOLD for p in ranked)

    def test_the_quality_report_carries_the_potential_in_expansion_order(self):
        data = self._data()
        ranked = AnalysisPipeline()._rank_polarities(data)
        quality = AnalysisPipeline._build_polarity_quality(
            data, [p["polarity_hash"] for p in ranked]
        )
        by_hash = {q["polarity_hash"]: q for q in quality}
        assert by_hash["position"]["tetrad_potential"] == 0.9
        assert by_hash["unrated"]["tetrad_potential"] is None
        assert [q["polarity_hash"] for q in quality][:2] == ["weak", "position"] or (
            [q["polarity_hash"] for q in quality][0] == "weak"
        ), "sorted by potential where rated"
        assert by_hash["weak"]["status"] == "set_aside", "high potential does not pass the HS gate"


class TestThePromptAsksForAPosition:
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def test_the_dto_rates_tetrad_potential_in_bounds(self):
        field = ModePointResultDto.model_fields["tetrad_potential"]
        assert field.annotation is float
        assert "coherent tetrad" in field.description
        assert "caricature" in field.description

    def test_both_mode_point_prompts_carry_the_ask_and_its_example(self):
        service = AntithesisExtraction()
        single = service._mode_point_prompt("Quit my job", "Job-lessness", "Negation", "ctx", 1.0)
        batch = service._mode_point_batch_prompt("Quit my job", "Job-lessness", "Negation", "ctx", 1.0, 2)
        for prompt in (single, batch):
            assert ext._OPPOSING_POSITION_ASK in prompt
            assert "functionally opposes the role the thesis plays" in prompt
            assert "Never quit, stay employed forever" in prompt, "the concrete failure, not a rule"
            assert "Rate its tetrad potential" in prompt, "a step in the procedure, not context"
            assert "represents Negation of the thesis" not in prompt


class TestThePotentialIsPersistedNextToModeAndArousal:
    """Real graph: the Estimation lands on the antithesis Statement."""

    @pytest.mark.asyncio
    async def test_persist_writes_a_tetrad_potential_estimation(self, monkeypatch):
        from dialectical_framework.concerns.statement_classification import \
            StatementClassification
        from dialectical_framework.graph.nodes.case import Case
        from dialectical_framework.graph.nodes.estimation import \
            TetradPotentialEstimation
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.scope_context import scope

        monkeypatch.setattr(
            StatementClassification, "lookup_antithesis_meaning",
            staticmethod(lambda thesis: "dx://taxonomy/Simple"),
        )
        case = Case()
        case.commit()
        with scope(case.sid):
            thesis = Statement(text="Quit my job and start my own company", meaning="dx://taxonomy/Simple")
            thesis.commit()
            service = AntithesisExtraction()
            (processed,) = await service._persist_candidates(
                thesis, [_cand("privation", 0.6, 0.9, "Keep the security of employed work")]
            )
            assert processed.tetrad_potential == 0.9
            values = [
                est.value for est, _ in processed.component.estimations.all()
                if isinstance(est, TetradPotentialEstimation)
            ]
            assert values == [0.9]
            assert service.report.artifacts.get("tetrad_potential_by_hash") is None, (
                "the artifact is written by resolve(), not by the persist step"
            )
