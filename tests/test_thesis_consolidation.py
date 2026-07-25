"""
Tests for consolidating theses that are antitheses of each other.

`AntitheticalThesisDetection` detects, among a set of provided theses, which pairs
are genuine dialectical opposites, banded by HS:
- HS >= 0.7  → merge (create one Polarity)
- 0.1 < HS < 0.7 → suggest (surface for confirmation, don't merge)
- HS <= 0.1  → ignore (not an antithesis)

`FindPolarities` runs this in Phase 0: strong pairs are merged into a single
Polarity and removed from antithesis extraction; weak pairs are recorded as
suggestions while both theses proceed independently.

The mock brain returns identical DTOs every call, so tests that need distinct or
banded verdicts monkeypatch `ConversationFacilitator.submit` (candidate proposal)
and `AntithesisClassification.resolve` (HS scoring) directly.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns.antithesis_classification import (
    AntithesisClassification, AntithesisClassificationResult)
from dialectical_framework.concerns.antithetical_thesis_detection import (
    AntitheticalThesisDetection, CandidatePairDto, CandidatePairsDto,
    ConsolidationResult, ThesisPair)
from dialectical_framework.agents.analyst.skills.find_polarities import \
    FindPolarities
from dialectical_framework.concerns.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository
from dialectical_framework.graph.scope_context import scope

# Statement.commit() requires a non-empty meaning.
_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"


def _make_statement(text: str) -> Statement:
    stmt = Statement(text=text, meaning=_MEANING)
    stmt.commit()
    return stmt


def _candidate_stub(pairs: list[tuple[int, int]]):
    """Stub ConversationFacilitator.submit to propose the given index pairs."""

    async def _submit(self, response_model, user_content, max_tool_rounds=10):
        return CandidatePairsDto(
            pairs=[CandidatePairDto(index_a=a, index_b=b) for a, b in pairs]
        )

    return _submit


def _classification_stub(hs_by_thesis_text: dict[str, float]):
    """Stub AntithesisClassification.resolve keyed by the THESIS text.

    Lets a test give a pair asymmetric HS depending on which side is treated as
    the thesis (apex), so orientation logic can be exercised.
    """

    async def _resolve(self, thesis, antithesis_statement, text=""):
        hs = hs_by_thesis_text.get(thesis.text, 0.0)
        return AntithesisClassificationResult(
            statement=antithesis_statement,
            meaning="",
            mode_value=1.0,
            mode_label="negation",
            arousal_value=0.5,
            heuristic_similarity=hs,
            reasoning="stub",
        )

    return _resolve


@pytest.mark.llm
class TestAntitheticalThesisDetection:
    """Detection banding, boundaries, orientation, and read-only guarantee."""

    @pytest.mark.asyncio
    async def test_strong_pair_lands_in_merge(self, monkeypatch):
        case = Case()
        case.commit()
        with scope(case.sid):
            t1 = _make_statement("Centralization")
            t2 = _make_statement("Decentralization")

            monkeypatch.setattr(
                ConversationFacilitator, "submit", _candidate_stub([(0, 1)])
            )
            monkeypatch.setattr(
                AntithesisClassification,
                "resolve",
                _classification_stub({"Centralization": 0.85, "Decentralization": 0.85}),
            )

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(thesis_hashes=[t1.hash, t2.hash])

            assert len(result.merge_pairs) == 1
            assert not result.suggest_pairs
            pair = result.merge_pairs[0]
            assert {pair.thesis_hash, pair.antithesis_hash} == {t1.hash, t2.hash}
            # Read-only: no Polarity/Statement created beyond the two theses.
            assert not any(
                e.effect_type in ("node_created", "node_committed")
                for e in detector.report.effects
            )

    @pytest.mark.asyncio
    async def test_weak_pair_lands_in_suggest(self, monkeypatch):
        case = Case()
        case.commit()
        with scope(case.sid):
            t1 = _make_statement("Growth")
            t2 = _make_statement("Structure")

            monkeypatch.setattr(
                ConversationFacilitator, "submit", _candidate_stub([(0, 1)])
            )
            monkeypatch.setattr(
                AntithesisClassification,
                "resolve",
                _classification_stub({"Growth": 0.4, "Structure": 0.4}),
            )

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(thesis_hashes=[t1.hash, t2.hash])

            assert not result.merge_pairs
            assert len(result.suggest_pairs) == 1

    @pytest.mark.asyncio
    async def test_below_lower_threshold_is_ignored(self, monkeypatch):
        case = Case()
        case.commit()
        with scope(case.sid):
            t1 = _make_statement("Apples")
            t2 = _make_statement("Tuesday")

            monkeypatch.setattr(
                ConversationFacilitator, "submit", _candidate_stub([(0, 1)])
            )
            monkeypatch.setattr(
                AntithesisClassification,
                "resolve",
                _classification_stub({"Apples": 0.05, "Tuesday": 0.05}),
            )

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(thesis_hashes=[t1.hash, t2.hash])

            assert not result.merge_pairs
            assert not result.suggest_pairs

    @pytest.mark.asyncio
    async def test_exact_boundaries(self, monkeypatch):
        """HS == 0.7 merges (>=); HS == 0.1 is ignored (not > 0.1)."""
        case = Case()
        case.commit()
        with scope(case.sid):
            merge_t1 = _make_statement("Order")
            merge_t2 = _make_statement("Chaos")
            drop_t1 = _make_statement("Red")
            drop_t2 = _make_statement("Blue")

            monkeypatch.setattr(
                ConversationFacilitator, "submit", _candidate_stub([(0, 1), (2, 3)])
            )
            monkeypatch.setattr(
                AntithesisClassification,
                "resolve",
                _classification_stub(
                    {"Order": 0.7, "Chaos": 0.7, "Red": 0.1, "Blue": 0.1}
                ),
            )

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(
                thesis_hashes=[merge_t1.hash, merge_t2.hash, drop_t1.hash, drop_t2.hash]
            )

            assert len(result.merge_pairs) == 1
            assert {result.merge_pairs[0].thesis_hash} <= {merge_t1.hash, merge_t2.hash}
            assert not result.suggest_pairs

    @pytest.mark.asyncio
    async def test_orientation_follows_higher_hs(self, monkeypatch):
        """The direction with the higher HS defines which thesis is T."""
        case = Case()
        case.commit()
        with scope(case.sid):
            a = _make_statement("Alpha")
            b = _make_statement("Beta")

            monkeypatch.setattr(
                ConversationFacilitator, "submit", _candidate_stub([(0, 1)])
            )
            # thesis=Alpha → HS 0.9; thesis=Beta → HS 0.3. Alpha should be T.
            monkeypatch.setattr(
                AntithesisClassification,
                "resolve",
                _classification_stub({"Alpha": 0.9, "Beta": 0.3}),
            )

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(thesis_hashes=[a.hash, b.hash])

            assert len(result.merge_pairs) == 1
            pair = result.merge_pairs[0]
            assert pair.thesis_hash == a.hash
            assert pair.antithesis_hash == b.hash
            assert pair.heuristic_similarity == 0.9

    @pytest.mark.asyncio
    async def test_greedy_assignment_uses_thesis_once(self, monkeypatch):
        """A thesis antithetical to two others is consumed by only the higher-HS pair."""
        case = Case()
        case.commit()
        with scope(case.sid):
            hub = _make_statement("Freedom")
            strong = _make_statement("Control")
            weak = _make_statement("Restraint")

            monkeypatch.setattr(
                ConversationFacilitator, "submit", _candidate_stub([(0, 1), (0, 2)])
            )
            monkeypatch.setattr(
                AntithesisClassification,
                "resolve",
                _classification_stub(
                    {"Freedom": 0.95, "Control": 0.95, "Restraint": 0.8}
                ),
            )

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(
                thesis_hashes=[hub.hash, strong.hash, weak.hash]
            )

            # Only the Freedom/Control pair survives; Freedom is already consumed.
            assert len(result.merge_pairs) == 1
            pair = result.merge_pairs[0]
            assert {pair.thesis_hash, pair.antithesis_hash} == {hub.hash, strong.hash}

    @pytest.mark.asyncio
    async def test_single_thesis_no_detection(self, monkeypatch):
        case = Case()
        case.commit()
        with scope(case.sid):
            t1 = _make_statement("Solitary")

            called = {"n": 0}

            async def _submit(self, response_model, user_content, max_tool_rounds=10):
                called["n"] += 1
                return CandidatePairsDto(pairs=[])

            monkeypatch.setattr(ConversationFacilitator, "submit", _submit)

            detector = AntitheticalThesisDetection()
            result = await detector.resolve(thesis_hashes=[t1.hash])

            assert not result.merge_pairs
            assert not result.suggest_pairs
            assert called["n"] == 0  # no LLM call for <2 theses


def _detection_stub(result: ConsolidationResult):
    async def _resolve(self, thesis_hashes, text=""):
        self._report.ok = True
        self._report.artifacts["consolidation_suggestions"] = [
            p.as_dict() for p in result.suggest_pairs
        ]
        return result

    return _resolve


def _no_extraction_stub():
    """AntithesisExtraction that finds nothing (isolates consolidation behavior)."""

    async def _resolve(self, thesis, text="", not_like_these=None, count=5):
        return []

    return _resolve


@pytest.mark.llm
class TestFindPolaritiesConsolidation:
    """FindPolarities Phase 0: strong pairs merged, weak pairs suggested."""

    @pytest.mark.asyncio
    async def test_strong_pair_merged_into_single_polarity(self, monkeypatch):
        case = Case()
        case.commit()
        with scope(case.sid):
            t1 = _make_statement("Centralization")
            t2 = _make_statement("Decentralization")

            merge_result = ConsolidationResult(
                merge_pairs=[
                    ThesisPair(
                        thesis_hash=t1.hash,
                        antithesis_hash=t2.hash,
                        thesis_text=t1.text,
                        antithesis_text=t2.text,
                        heuristic_similarity=0.85,
                        mode_value=1.0,
                        arousal_value=0.5,
                    )
                ]
            )
            monkeypatch.setattr(
                AntitheticalThesisDetection, "resolve", _detection_stub(merge_result)
            )

            # Track whether extraction was asked to run on the merged theses.
            extracted_for: list[str] = []

            async def _extract(self, thesis, text="", not_like_these=None, count=5):
                extracted_for.append(thesis.text)
                return []

            monkeypatch.setattr(AntithesisExtraction, "resolve", _extract)

            skill = FindPolarities(thesis_hashes=[t1.hash, t2.hash])
            await skill.resolve()

            # Exactly one Polarity for the merged tension.
            pols = PolarityRepository().find_by_tension(t1, t2)
            assert len(pols) == 1
            # Neither merged thesis was sent to antithesis extraction.
            assert extracted_for == []
            # Report reflects the consolidation.
            assert skill.report.artifacts.get("consolidated_pairs") == 1
            pd = skill.report.artifacts.get("polarity_data", [])
            assert any(p.get("consolidated") for p in pd)

    @pytest.mark.asyncio
    async def test_weak_pair_is_suggested_not_merged(self, monkeypatch):
        case = Case()
        case.commit()
        with scope(case.sid):
            t1 = _make_statement("Growth")
            t2 = _make_statement("Structure")

            suggest_result = ConsolidationResult(
                suggest_pairs=[
                    ThesisPair(
                        thesis_hash=t1.hash,
                        antithesis_hash=t2.hash,
                        thesis_text=t1.text,
                        antithesis_text=t2.text,
                        heuristic_similarity=0.4,
                        mode_value=1.0,
                        arousal_value=0.5,
                    )
                ]
            )
            monkeypatch.setattr(
                AntitheticalThesisDetection, "resolve", _detection_stub(suggest_result)
            )

            extracted_for: list[str] = []

            async def _extract(self, thesis, text="", not_like_these=None, count=5):
                extracted_for.append(thesis.text)
                return []

            monkeypatch.setattr(AntithesisExtraction, "resolve", _extract)

            skill = FindPolarities(thesis_hashes=[t1.hash, t2.hash])
            await skill.resolve()

            # No consolidation Polarity created for the weak pair.
            assert not PolarityRepository().find_by_tension(t1, t2)
            # Both theses still went through independent extraction (non-destructive).
            assert set(extracted_for) == {"Growth", "Structure"}
            # Suggestion surfaced in the report.
            suggestions = skill.report.artifacts.get("consolidation_suggestions", [])
            assert len(suggestions) == 1
