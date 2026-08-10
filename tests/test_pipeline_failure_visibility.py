"""
An analysis that produced nothing must not report success.

Measured, not hypothetical. In the `claim2-weak-r1` bench row two A2 cells
logged `anchor:ok` several times over and then summarised the graph as
`perspectives=0`, which reads as "the model declined to use its tools" — the
opposite of the truth ("every expansion failed"), and fatal to a claim whose
whole subject is whether a durable record beats a prose journal.

Two silent-success paths produced it, both fixed here:

1. `AnalysisPipeline.resolve` set `ok=True` unconditionally after the expansion
   gather and carried its `StepError`s home on `AnalysisResult`, which no tool
   renders — so the LLM saw neither the failure nor the count.
2. `ExpandPolarity.resolve` set `ok=True` even when it returned no
   Perspectives.

`anchor` composes both, and `str(report)` is the whole of what the model learns
about a mutating call, so either one alone is enough to make `anchor:ok` a lie.

DB-free and LLM-free: the defect is in how the report is composed, so the
sub-skill is stubbed and the graph steps are patched out.
"""

from __future__ import annotations

import pytest

from dialectical_framework.agents.analyst.analyst import AnalysisPipeline


# DB-free: override the autouse graph fixtures (per CLAUDE.md convention).
@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


class _FakeReport:
    """Just the two attributes the pipeline reads off a sub-report."""

    def __init__(self, ok: bool, summary: str = "") -> None:
        self.ok = ok
        self.summary = summary


def _polarity_data() -> list[dict]:
    return [
        {
            "polarity_hash": "aaa",
            "thesis_text": "Buy out the cofounder",
            "antithesis_text": "Keep the cofounder",
            "heuristic_similarity": 0.9,
        },
    ]


async def _run(monkeypatch, expand) -> AnalysisPipeline:
    """Drive resolve() from the find-polarities step onward."""

    class _FakeFind:
        def __init__(self, **kwargs) -> None:
            self.report = _FakeReport(True, "found")
            self.report.artifacts = {"polarity_data": _polarity_data()}

        async def resolve(self):
            return None

    monkeypatch.setattr(
        "dialectical_framework.agents.analyst.skills.find_polarities.FindPolarities",
        _FakeFind,
    )
    pipeline = AnalysisPipeline(thesis_hashes=["t1"])
    monkeypatch.setattr(pipeline, "_expand_one", expand)
    await pipeline.resolve()
    return pipeline


@pytest.mark.asyncio
async def test_pipeline_that_expanded_nothing_reports_failure(monkeypatch):
    """Every expansion raised -> the report must NOT say ok.

    This is the exact `anchor:ok` / `perspectives=0` pair from the bench row.
    """

    async def boom(polarity_hash: str):
        raise RuntimeError("aspect generation timed out")

    pipeline = await _run(monkeypatch, boom)

    assert pipeline.report.ok is False, (
        "A pipeline that produced no perspectives reported success — the "
        "`anchor` tool composing it then reports `anchor:ok` over an empty graph"
    )


@pytest.mark.asyncio
async def test_expansion_failures_reach_the_llm(monkeypatch):
    """The failure must be in `str(report)`, not only on AnalysisResult.

    `AnalysisResult.errors` is returned to Python callers; the LLM sees only
    the report. A failure visible in one and not the other is how the model
    kept anchoring against a graph that never grew.
    """

    async def boom(polarity_hash: str):
        raise RuntimeError("aspect generation timed out")

    pipeline = await _run(monkeypatch, boom)
    rendered = str(pipeline.report)

    assert "FAILED to expand" in pipeline.report.summary
    assert "aspect generation timed out" in rendered
    assert pipeline.report.artifacts["errors"], "errors must be a report artifact"


@pytest.mark.asyncio
async def test_sub_skill_reporting_not_ok_is_not_swallowed(monkeypatch):
    """A sub-skill that fails WITHOUT raising must still fail the pipeline.

    `_expand_one` returns `(hashes, report)`; a report with ok=False never
    raised, so before this the only trace was in `reports`, which the pipeline
    discards by design (see the AnalysisPipeline note on report merging).
    """

    async def quiet_failure(polarity_hash: str):
        return [], _FakeReport(False, "No Perspective produced for polarity")

    pipeline = await _run(monkeypatch, quiet_failure)

    assert pipeline.report.ok is False
    assert "No Perspective produced" in pipeline.report.summary


@pytest.mark.asyncio
async def test_successful_expansion_still_reports_ok(monkeypatch):
    """The guard must not flip healthy runs — ok tracks perspectives, not errors."""

    async def fine(polarity_hash: str):
        return ["pphash1"], _FakeReport(True, "1 Perspective")

    pipeline = await _run(monkeypatch, fine)

    assert pipeline.report.ok is True
    assert "FAILED" not in pipeline.report.summary
    assert "errors" not in pipeline.report.artifacts


@pytest.mark.asyncio
async def test_partial_success_reports_ok_but_names_the_loss(monkeypatch):
    """One tension expanded, one failed: usable result, visible loss.

    Failing the whole call here would be the opposite error — the perspective
    that WAS built is real and the agent should use it.
    """
    calls = {"n": 0}

    async def half(polarity_hash: str):
        calls["n"] += 1
        if calls["n"] == 1:
            return ["pphash1"], _FakeReport(True, "1 Perspective")
        raise RuntimeError("second tension timed out")

    data = _polarity_data() + [
        {
            "polarity_hash": "bbb",
            "thesis_text": "Stay solo",
            "antithesis_text": "Bring in an advisor",
            "heuristic_similarity": 0.8,
        },
    ]

    class _FakeFind:
        def __init__(self, **kwargs) -> None:
            self.report = _FakeReport(True, "found")
            self.report.artifacts = {"polarity_data": data}

        async def resolve(self):
            return None

    monkeypatch.setattr(
        "dialectical_framework.agents.analyst.skills.find_polarities.FindPolarities",
        _FakeFind,
    )
    pipeline = AnalysisPipeline(thesis_hashes=["t1"])
    monkeypatch.setattr(pipeline, "_expand_one", half)
    await pipeline.resolve()

    assert pipeline.report.ok is True, "A partial result is still a result"
    assert "1 tension(s) FAILED to expand" in pipeline.report.summary
    assert "second tension timed out" in str(pipeline.report)
