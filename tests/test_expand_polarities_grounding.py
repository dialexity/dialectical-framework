"""ExpandPolarity carries the anchor's `context` into the graph as grounding.

`anchor(thesis, antithesis, context=...)` documents `context` as "conversational
context that grounds this tension", and until this wiring existed it did not: the
string reached `IntroducePolarity`, informed classification and headlining, and
was then dropped. Nothing about the person's actual situation survived into the
tetrad, whose poles are capped near seven words and deduped against every other
case in the scope.

These tests pin the write path:
  * one extraction per call, reused across the tetrads it produced (the
    particulars describe the situation, not one reading of it);
  * every new tetrad gets its own edge, reported in `artifacts["grounded"]`;
  * no context → no LLM call and no nodes;
  * extraction failure leaves the tetrads intact — grounding is enrichment,
    never a gate.

Grounding runs BEFORE validation on purpose, and `test_grounding_survives_a_
validation_crash` is why: the tetrad is already committed by then, so a
validation blow-up must not cost the case particulars.

Run: poetry run pytest tests/test_expand_polarities_grounding.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              AspectResult)
from dialectical_framework.concerns.tetrad_grounding import (GroundingDto,
                                                             TetradGrounding)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.rendering import grounding_line
from dialectical_framework.graph.scope_context import scope

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"
_ASPECT_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Coherence"

CONTEXT = (
    "I hold 55% and he holds 45%. He closed both of our major customers and "
    "he's on every call with them — I've been in three as a plus-one. I raised "
    "it in March, he agreed, nothing changed."
)

PARTICULARS = (
    "Equity 55/45. Cofounder closed both major customers, on every call; "
    "founder attended three as plus-one. Raised in March, agreed, no change."
)


def _make_polarity(sid: str) -> Polarity:
    with scope(sid):
        t = Statement(text="Buy him out", meaning=_T_MEANING)
        t.commit()
        a = Statement(text="Keep the partnership", meaning=_A_MEANING)
        a.commit()

        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        return polarity


def _distinct_aspect_stub(sid: str):
    """Emit distinct aspects per call so `count>1` does not collapse via dedup.

    The mock brain returns identical DTOs every call (CLAUDE.md), which the
    duplicate-discard guard would fold into one perspective.
    """
    call_index = {"n": 0}

    async def _resolve(self, perspective, positions=None, text="", not_like_these=None):
        i = call_index["n"]
        call_index["n"] += 1
        with scope(sid):
            results: list[AspectResult] = []
            for pos, label in (
                (POSITION_T_PLUS, "Decisive ownership"),
                (POSITION_T_MINUS, "Isolated overreach"),
                (POSITION_A_PLUS, "Shared accountability"),
                (POSITION_A_MINUS, "Deadlocked deference"),
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


def _fixed_extraction(monkeypatch, text: str = PARTICULARS) -> dict:
    """Stub the grounding LLM call, counting invocations."""
    calls = {"n": 0, "material": []}

    async def _extract(self, material: str) -> str:
        calls["n"] += 1
        calls["material"].append(material)
        return text

    monkeypatch.setattr(TetradGrounding, "_extract", _extract)
    return calls


@pytest.mark.llm
class TestExpandPolarityGrounding:
    @pytest.mark.asyncio
    async def test_context_is_attached_to_the_new_tetrad(self, monkeypatch):
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert len(pps) == 1
            assert calls["n"] == 1
            assert CONTEXT in calls["material"][0]

            line = grounding_line(pps[0])
            assert line is not None
            assert "55/45" in line
            assert concern.report.artifacts["grounded"] == [pps[0].short_hash]

    @pytest.mark.asyncio
    async def test_one_extraction_is_reused_across_all_tetrads(self, monkeypatch):
        """N tetrads from one context cost ONE LLM call, not N.

        The particulars describe the situation; each tetrad is a different
        reading OF it. Re-extracting per perspective would spend N calls
        producing the same text from the same material.
        """
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, count=3, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert len(pps) == 3
            assert calls["n"] == 1, "grounding re-extracted per perspective"

            for pp in pps:
                line = grounding_line(pp)
                assert line is not None, f"{pp.short_hash} was left ungrounded"
                assert "55/45" in line

            assert set(concern.report.artifacts["grounded"]) == {
                pp.short_hash for pp in pps
            }

    @pytest.mark.asyncio
    async def test_no_context_means_no_call_and_no_grounding(self, monkeypatch):
        """The Analyst path passes no context; it must stay exactly as it was."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(polarity_hash=polarity.hash)
            pps = await concern.resolve()

            assert calls["n"] == 0
            assert grounding_line(pps[0]) is None
            assert "grounded" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_blank_context_is_treated_as_absent(self, monkeypatch):
        """`anchor`'s `context` defaults to "" — whitespace must not trigger a call."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            calls = _fixed_extraction(monkeypatch)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context="   \n  "
            )
            pps = await concern.resolve()

            assert calls["n"] == 0
            assert grounding_line(pps[0]) is None

    @pytest.mark.asyncio
    async def test_empty_extraction_grounds_nothing(self, monkeypatch):
        """Material with no particulars must not create an empty Rationale."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            _fixed_extraction(monkeypatch, text="")

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert pps
            assert grounding_line(pps[0]) is None
            assert "grounded" not in concern.report.artifacts

    @pytest.mark.asyncio
    async def test_extraction_failure_leaves_the_tetrad_intact(self, monkeypatch):
        """Grounding is enrichment: its failure must not fail the expansion."""
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)

            async def _boom(self, material: str) -> str:
                raise RuntimeError("provider exploded")

            monkeypatch.setattr(TetradGrounding, "_extract", _boom)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            pps = await concern.resolve()

            assert len(pps) == 1
            assert pps[0].is_complete() and pps[0].is_committed
            assert concern.report.ok is True
            assert grounding_line(pps[0]) is None

    @pytest.mark.asyncio
    async def test_grounding_survives_a_validation_crash(self, monkeypatch):
        """Order matters: grounding lands before the validation pass runs.

        Validation is already fail-soft, but it is also the later and more
        elaborate step. Attaching first means a bug there cannot cost the case
        particulars of an already-committed tetrad.
        """
        case_node = Case()
        case_node.commit()

        with scope(case_node.sid):
            polarity = _make_polarity(case_node.sid)
            stub, _ = _distinct_aspect_stub(case_node.sid)
            monkeypatch.setattr(AspectGeneration, "resolve", stub)
            _fixed_extraction(monkeypatch)

            async def _boom(self, perspectives, input_text):
                raise RuntimeError("validation exploded")

            monkeypatch.setattr(ExpandPolarity, "_validate_and_flag", _boom)

            concern = ExpandPolarity(
                polarity_hash=polarity.hash, grounding_context=CONTEXT
            )
            with pytest.raises(RuntimeError):
                await concern.resolve()

            # The tetrad committed and was grounded before validation ran.
            pps = polarity.perspectives.all()
            assert pps
            grounded = [
                grounding_line(pp) for pp, _ in pps if grounding_line(pp) is not None
            ]
            assert grounded and "55/45" in grounded[0]


@pytest.mark.llm
class TestGroundingDtoShape:
    def test_particulars_is_the_only_field(self):
        """Flat single-field DTO — the real LLM drops branches the mock fills in."""
        assert list(GroundingDto.model_fields) == ["particulars"]
