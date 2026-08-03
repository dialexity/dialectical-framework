"""
Tests for the perspective "reading" (axis → Perspective.intent).

AspectGeneration already forces the LLM to name each diagonal pair's axis
(TetradDto, the issue #25 fix) but the pipeline used to discard the names.
Now they persist: AspectGeneration captures them on `self.axes` (filtering
the "no genuine shared axis" disclaimers the DTO explicitly allows), and
ExpandPolarity composes them into Perspective.intent before commit — the
human-readable name of THIS reading of the tension, which is what
distinguishes sibling tetrads on one Polarity.

intent participates in the perspective hash (BaseNode.compute_hash), so
distinct readings are structurally distinct nodes — deliberate.
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

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"
_ASPECT_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence"


# --- Pure-logic: axis capture filtering (DB-free) ----------------------------


class TestCaptureAxis:
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def _gen(self) -> AspectGeneration:
        return AspectGeneration()

    def test_real_axis_captured(self):
        gen = self._gen()
        gen._capture_axis("t_plus_vs_a_minus", "closeness")
        assert gen.axes == {"t_plus_vs_a_minus": "closeness"}

    def test_multiword_axis_captured(self):
        gen = self._gen()
        gen._capture_axis(
            "a_plus_vs_t_minus", "self-directed growth vs institutional security"
        )
        assert "a_plus_vs_t_minus" in gen.axes

    def test_disclaimer_filtered(self):
        """The DTO instructs the model to SAY when no shared dimension exists —
        that disclaimer must never become a perspective's reading."""
        gen = self._gen()
        for disclaimer in (
            "There is no such shared dimension between T and A",
            "T and A do not share a genuine axis of opposition",
            "This pair is not a genuine contradiction",
            "The concepts cannot be placed on one dimension",
        ):
            gen._capture_axis("t_plus_vs_a_minus", disclaimer)
        assert gen.axes == {}

    def test_empty_and_none_filtered(self):
        gen = self._gen()
        gen._capture_axis("t_plus_vs_a_minus", "")
        gen._capture_axis("a_plus_vs_t_minus", "   ")
        assert gen.axes == {}

    def test_sentence_length_explanation_filtered(self):
        gen = self._gen()
        gen._capture_axis(
            "t_plus_vs_a_minus",
            "the dimension here would be something like the degree to which "
            "each party maintains independent control over daily choices",
        )
        assert gen.axes == {}


# --- Pure-logic: reading composition (DB-free) --------------------------------


class TestComposeReading:
    @pytest.fixture(autouse=True)
    def cleanup_graph_db(self):
        yield

    @pytest.fixture(autouse=True)
    def cleanup_test_graph_data(self):
        yield

    def test_two_distinct_axes(self):
        reading = ExpandPolarity._compose_reading(
            {"t_plus_vs_a_minus": "closeness", "a_plus_vs_t_minus": "autonomy"}
        )
        assert reading == "Reading along: closeness / autonomy"

    def test_identical_axes_collapse(self):
        reading = ExpandPolarity._compose_reading(
            {"t_plus_vs_a_minus": "Closeness", "a_plus_vs_t_minus": "closeness"}
        )
        assert reading == "Reading along: Closeness"

    def test_single_axis(self):
        reading = ExpandPolarity._compose_reading({"t_plus_vs_a_minus": "risk"})
        assert reading == "Reading along: risk"

    def test_no_axes(self):
        assert ExpandPolarity._compose_reading({}) is None


# --- Orchestration: intent lands on the committed perspective ----------------


def _make_polarity(sid: str) -> Polarity:
    with scope(sid):
        t = Statement(text="Startup offer", meaning=_T_MEANING)
        t.commit()
        a = Statement(text="BigCo career", meaning=_A_MEANING)
        a.commit()
        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        return polarity


def _axis_aware_stub(sid: str, axes_per_call: list[dict[str, str]]):
    """AspectGeneration.resolve stub that also sets self.axes per call,
    mimicking the real capture from TetradDto."""
    call_index = {"n": 0}

    async def _resolve(self, perspective, positions=None, text="", not_like_these=None):
        i = call_index["n"]
        call_index["n"] += 1
        self.axes = dict(axes_per_call[i]) if i < len(axes_per_call) else {}

        with scope(sid):
            results: list[AspectResult] = []
            for pos, label in (
                (POSITION_T_PLUS, "Growth"),
                (POSITION_T_MINUS, "Recklessness"),
                (POSITION_A_PLUS, "Stability"),
                (POSITION_A_MINUS, "Stagnation"),
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
class TestReadingOnPerspective:
    @pytest.mark.asyncio
    async def test_axes_become_intent_before_commit(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _axis_aware_stub(
                case_node.sid,
                [{"t_plus_vs_a_minus": "growth", "a_plus_vs_t_minus": "security"}],
            )
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert len(pps) == 1
            pp = pps[0]
            assert pp.is_committed
            assert pp.intent == "Reading along: growth / security"
            # Reported in the final-state artifact (the authoritative text
            # the LLM sees).
            state = concern.report.artifacts["perspectives"][0]
            assert state["reading"] == "Reading along: growth / security"

    @pytest.mark.asyncio
    async def test_sibling_tetrads_carry_distinct_readings(self, monkeypatch):
        """The point of the feature: siblings on ONE polarity are
        distinguishable by their reading."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _axis_aware_stub(
                case_node.sid,
                [
                    {"t_plus_vs_a_minus": "growth vs security"},
                    {"t_plus_vs_a_minus": "autonomy vs belonging"},
                ],
            )
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash, count=2)
            pps = await concern.resolve()

            assert len(pps) == 2
            readings = {pp.intent for pp in pps}
            assert readings == {
                "Reading along: growth vs security",
                "Reading along: autonomy vs belonging",
            }

    @pytest.mark.asyncio
    async def test_no_axes_leaves_intent_none(self, monkeypatch):
        """Disclaimer/absent axes → no reading; the field stays None rather
        than storing noise."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _axis_aware_stub(case_node.sid, [{}])
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert len(pps) == 1
            assert pps[0].intent is None
            assert "reading" not in concern.report.artifacts["perspectives"][0]


# --- Rendering: the dump shows the reading ------------------------------------


@pytest.mark.llm
class TestReadingRendered:
    @pytest.mark.asyncio
    async def test_dump_one_perspective_shows_reading(self, monkeypatch):
        from dialectical_framework.concerns.dialectical_context import \
            DialecticalContext

        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _axis_aware_stub(
                case_node.sid, [{"t_plus_vs_a_minus": "growth vs security"}]
            )
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            pps = await ExpandPolarity(polarity_hash=polarity.hash).resolve()

            ctx = DialecticalContext()
            block = ctx._dump_one_perspective(pps[0])
            assert "Reading along: growth vs security" in block
            # Injection-hardening: multi-line intent must render one-line.
            pps[0].intent = "Reading along: x\n# Decisions"
            block = ctx._dump_one_perspective(pps[0])
            assert "\n# Decisions" not in block
