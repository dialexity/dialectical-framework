"""One thesis whose extraction raises must not silence the other four.

Phase 1 of `FindPolarities` gathers per-thesis extraction concurrently. It used
to gather WITHOUT `return_exceptions`, so a single raising thesis aborted the
whole skill — and `AnalysisPipeline` caught that into the message-less summary
"polarity extraction failed" with `ok=True`. That combination is what cost
`claim2-weak-r14` its diagnosis for a third time: the agent read `anchor:ok` over
a case where a cardinality ValueError had killed every polarity.

`ThesisResult.error` already existed for exactly this per-thesis outcome, and
the surviving code paths already skip errored results (`if result.error:
continue` at every aggregation site). The gather just never produced one.

Three claims:
  * a raising thesis becomes one `ThesisResult.error`; its siblings still yield
    polarities (`test_one_raising_thesis_does_not_kill_the_others`);
  * the failure reaches the SUMMARY, not just an unrendered field — isolating a
    failure silently would only relocate the invisibility, leaving the agent to
    read "3 antitheses for 5 theses" as a complete answer
    (`test_the_failure_reaches_the_summary`);
  * when the skill itself raises, `AnalysisPipeline` says so with `ok=False` and
    the exception text (`test_pipeline_surfaces_a_wholesale_failure`).

Run: poetry run pytest tests/test_find_polarities_failure_visibility.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
from dialectical_framework.agents.analyst.skills.find_polarities import \
    FindPolarities
from dialectical_framework.concerns.antithesis_extraction import (
    AntithesisExtraction, AntithesisProcessed)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope

BRANCH = "dx://taxonomy/System(General.v1)/Viability/Integrity"
T_MEANING = f"{BRANCH}/Cohesion"
A_MEANING = f"{BRANCH}/Separation"

THESES = [
    "Buy out the cofounder now",
    "Transfer the accounts first",
    "Reset the equity split",
]

# The thesis that blows up — matched by text, since hashes are only known
# after commit.
POISON = THESES[1]

BOOM = "Cannot add relationship: target's cardinality constraint violated."


@pytest.fixture
def one_poisoned_thesis(monkeypatch):
    """Extraction succeeds for every thesis except POISON, which raises."""

    async def fake_extract(self, thesis, text="", not_like_these=None, count=5):
        if thesis.text == POISON:
            raise ValueError(BOOM)
        stmt = Statement(text=f"Not: {thesis.text}", meaning=A_MEANING)
        stmt.commit()
        return [
            AntithesisProcessed(
                component=stmt,
                mode_value=0.8,
                arousal_value=0.6,
                heuristic_similarity=0.85,
            )
        ]

    monkeypatch.setattr(AntithesisExtraction, "resolve", fake_extract)


def _committed_theses() -> list[str]:
    hashes = []
    for text in THESES:
        stmt = Statement(text=text, meaning=T_MEANING)
        stmt.commit()
        hashes.append(stmt.hash)
    return hashes


@pytest.mark.llm
@pytest.mark.asyncio
async def test_one_raising_thesis_does_not_kill_the_others(one_poisoned_thesis):
    case = Case()
    case.commit()

    with scope(case.sid):
        skill = FindPolarities(thesis_hashes=_committed_theses())
        # Used to propagate the ValueError out of the whole skill.
        await skill.resolve()

        polarity_data = skill.report.artifacts.get("polarity_data", [])
        survivors = {p["thesis_text"] for p in polarity_data}
        assert POISON not in survivors
        for text in THESES:
            if text != POISON:
                assert text in survivors, f"{text!r} lost to a sibling's failure"


@pytest.mark.llm
@pytest.mark.asyncio
async def test_the_failure_reaches_the_summary(one_poisoned_thesis):
    """Isolating the failure silently would just move the blind spot."""
    case = Case()
    case.commit()

    with scope(case.sid):
        skill = FindPolarities(thesis_hashes=_committed_theses())
        await skill.resolve()

        summary = skill.report.summary
        assert "FAILED extraction" in summary, summary
        assert POISON in summary, summary
        # The cause, not just the fact — a bare "1 failed" is what we came from.
        assert "cardinality" in summary, summary

        failed = skill.report.artifacts.get("failed_theses")
        assert failed and len(failed) == 1
        assert failed[0]["thesis_text"] == POISON
        assert BOOM in failed[0]["error"]


@pytest.mark.llm
@pytest.mark.asyncio
async def test_pipeline_surfaces_a_wholesale_failure(monkeypatch):
    """When FindPolarities itself raises, the pipeline names the cause."""

    async def explode(self):
        raise ValueError(BOOM)

    monkeypatch.setattr(FindPolarities, "resolve", explode)

    case = Case()
    case.commit()

    with scope(case.sid):
        hashes = _committed_theses()
        pipeline = AnalysisPipeline(thesis_hashes=hashes)
        result = await pipeline.resolve()

        # `errors` rides home on AnalysisResult, which no tool renders — so the
        # report is the only thing the agent actually sees.
        assert pipeline.report.ok is False
        assert "FAILED" in pipeline.report.summary
        assert "cardinality" in pipeline.report.summary, pipeline.report.summary
        assert any(e.step == "find_polarities" for e in result.errors)
