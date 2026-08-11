"""One thesis fanning out to N polarities must expand into N perspectives.

This is the live shape from `claim2-weak-r6-grounding` (A2 / cofounder_equity /
rep 1 / `wobble_a` / turn 1): `anchor(thesis=..., antithesis=None)` →
`AnalysisPipeline` reported

    1 theses, 5 polarities, 0 perspectives
    — 5 tension(s) FAILED to expand (df60b61d94...: Perspective has no
      Polarity connected - cannot access T; ... ×5)

Five identical failures, one per polarity, with a stated cause that was not
true (see `tests/test_relationship_read_id_recovery.py` for the read-side
mechanism and its fix). Turn 2 of the same session succeeded, so the trigger is
state, not shape — which is exactly why the shape deserves a standing test.

The mock brain returns one identical DTO per call, so the default path yields a
single polarity and never fans out. `AntithesisExtraction` is patched to hand
back five DISTINCT antitheses for the one thesis (what the live weak-tier model
did) and everything downstream runs for real: `_create_polarities`, the gather in
`AnalysisPipeline`, `ExpandPolarity`'s complete/partial split, `AspectGeneration`,
aspect dedup, `commit()` hash dedup.

Five perspectives from five polarities is the whole claim. It fails loudly if
any of those stages starts dropping tetrads — including silently, via a
misreported structural verdict, which is how it failed in production.

Run: poetry run pytest tests/test_anchor_fanout_expansion.py
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.advisor.tools.anchor import anchor
from dialectical_framework.concerns.antithesis_extraction import (
    AntithesisExtraction, AntithesisProcessed)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository
from dialectical_framework.graph.scope_context import scope

BRANCH = "dx://taxonomy/System(General.v1)/Viability/Integrity"
A_MEANING = f"{BRANCH}/Separation"

THESIS = "Buy out the cofounder now"

ANTITHESES = [
    "Keep him and reset the terms",
    "Transfer the accounts before deciding",
    "Let the partnership run as is",
    "Hand him the customer relationships formally",
    "Sell the company instead",
]

CONTEXT = (
    "Cofounder holds 45% equity. Two anchor accounts are 60% of revenue and "
    "both CEOs call him, not me. Feedback given in March, no change since."
)


@pytest.fixture
def five_antitheses(monkeypatch):
    """One thesis → five distinct antitheses, so the pipeline actually fans out."""

    async def fake_extract(self, thesis, text="", not_like_these=None, count=5):
        out = []
        for name in ANTITHESES:
            stmt = Statement(text=name, meaning=A_MEANING)
            stmt.commit()
            out.append(
                AntithesisProcessed(
                    component=stmt,
                    mode_value=0.8,
                    arousal_value=0.6,
                    heuristic_similarity=0.85,
                )
            )
        return out

    monkeypatch.setattr(AntithesisExtraction, "resolve", fake_extract)


@pytest.mark.llm
@pytest.mark.asyncio
async def test_every_polarity_becomes_a_perspective(five_antitheses):
    case = Case()
    case.commit()

    with scope(case.sid):
        out = await anchor.fn(thesis=THESIS, antithesis=None, context=CONTEXT)

    # The exact live regression: the count reached 0 and the reason was false.
    assert "no Polarity connected" not in out
    assert "FAILED to expand" not in out
    assert "5 polarities, 5 perspectives" in out


@pytest.mark.llm
@pytest.mark.asyncio
async def test_the_perspectives_are_really_in_the_graph(five_antitheses):
    """The report is a string; the tetrads have to survive in the database.

    A report can claim perspectives that `commit()` deduped away or that never
    got their polarity edge — the graph is the authority.
    """
    case = Case()
    case.commit()

    with scope(case.sid):
        await anchor.fn(thesis=THESIS, antithesis=None, context=CONTEXT)

        pps = PerspectiveRepository().find_all_active()
        assert len(pps) == 5
        for pp in pps:
            assert pp.is_complete() is True
            assert pp.t.get() is not None
            assert pp.a.get() is not None
