"""
`RecordDecision` refuses an exact duplicate of an ACTIVE decision.

`thinking-off` (A2c wobble_a, decide t5) archived the model calling
`record_decision` twice in one turn: four records on a cell with one closing.
The Decision NODE deliberately never dedups (its nonce makes a repeat a new
speech act), so the refusal lives in the concern behind the tool and the seam,
and it is deliberately narrow — exact question and stance after whitespace and
case normalisation, against active decisions only. A paraphrase is the
confirmation classifier's job; a different stance is a new decision; a repeat
after a discard is a new speech act.
"""

from __future__ import annotations

import pytest

from dialectical_framework.concerns.record_decision import RecordDecision
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.repositories.decision_repository import \
    DecisionRepository
from dialectical_framework.graph.scope_context import scope

QUESTION = "Buy out the cofounder or restructure?"
STANCE = "Buy him out"


async def _record(question: str = QUESTION, stance: str = STANCE) -> tuple[str | None, RecordDecision]:
    concern = RecordDecision()
    decision_hash = await concern.resolve(
        question=question, stance=stance, rationale="He is checked out.", principal="human"
    )
    return decision_hash, concern


@pytest.mark.llm
class TestOneDecisionOneRecord:
    async def test_the_same_words_twice_are_one_record(self):
        case = Case()
        case.commit()
        with scope(case.sid):
            first, _ = await _record()
            second, concern = await _record()
            assert first and second == first
            assert concern.report.ok
            assert concern.report.artifacts.get("already_recorded") is True
            assert "Already on record" in concern.report.summary
            assert len(DecisionRepository().find_all_active()) == 1

    async def test_whitespace_and_case_do_not_make_a_new_record(self):
        case = Case()
        case.commit()
        with scope(case.sid):
            first, _ = await _record()
            second, _ = await _record("  buy out the COFOUNDER   or restructure? ", "BUY HIM OUT")
            assert second == first
            assert len(DecisionRepository().find_all_active()) == 1

    async def test_a_different_stance_is_a_new_decision(self):
        """Superseding is recording the new stance; the coherence check flags
        the contradiction and discarding the old record stays the agent's move."""
        case = Case()
        case.commit()
        with scope(case.sid):
            first, _ = await _record()
            second, _ = await _record(stance="Restructure the roles instead")
            assert second and second != first
            assert len(DecisionRepository().find_all_active()) == 2

    async def test_a_repeat_after_a_discard_is_a_new_speech_act(self):
        case = Case()
        case.commit()
        with scope(case.sid):
            first, _ = await _record()
            from dialectical_framework.graph.repositories.node_repository import \
                NodeRepository

            old = NodeRepository().find_by_hash(first)
            old.discarded = "changed my mind"
            old.save()
            second, concern = await _record()
            assert second and second != first
            assert concern.report.artifacts.get("already_recorded") is None
