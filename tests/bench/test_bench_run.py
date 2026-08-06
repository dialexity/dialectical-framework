"""
Entry points that actually spend money. `--real-llm` only.

Two of them, deliberately:

- `test_bench_smoke` — one scenario, one tier, one arm pair, no judge. Proves
  the plumbing end to end for a few cents. Run this before anything else after
  touching the bench.
- `test_bench_matrix` — the real thing, configured by env so a run can be
  narrowed without editing code (see README).

Both are `pytest` tests rather than a script so they inherit `conftest.py`'s DI
wiring and the test-labelled graph DB — an ad-hoc script gets unresolved
`Provide` sentinels, and worse, would write bench graphs into production-labelled
nodes.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bench.config import BenchConfig
from bench.models import Arm
from bench.runner import DEFAULT_ARMS, JUDGED_PAIRS, BenchRun

pytestmark = pytest.mark.real_llm

#: Where reports land. Gitignored: the bench code is the deliverable, a
#: particular run's transcripts are not, and they can contain a lot of tokens.
OUTPUT_DIR = Path(__file__).parent / "results"


def _say(message: str) -> None:
    # print() rather than logging: with `-s` this is the live progress view of a
    # run that can take an hour, and pytest swallows log output by default.
    print(message, flush=True)


@pytest.mark.asyncio
async def test_bench_smoke(di_container):
    """Cheapest possible end-to-end proof that the harness runs.

    One counsel scenario, one tier, A1 vs A2, no judge. Asserts only on the
    plumbing — that both arms produced text, and that A2 actually used its
    tools. It does NOT assert the framework wins: that is the experiment's
    outcome, and a test that requires a win would be circular.
    """
    config = BenchConfig.from_env(tiers=["weak"])
    run = BenchRun(di_container, config)
    await run.run_matrix(
        arms=[Arm.A1, Arm.A2],
        scenario_keys=["agile_process"],
        replicates=1,
        progress=_say,
    )
    run.score_machine()
    _say(run.report())
    run.save(OUTPUT_DIR, stem="smoke")

    assert len(run.runs) == 2
    for record in run.runs:
        assert not record.error, record.error
        text = "".join(t.assistant for s in record.sessions for t in s.turns)
        assert text.strip(), f"{record.arm.value} produced no text"

    a2 = next(r for r in run.runs if r.arm is Arm.A2)
    assert not a2.collapsed_to_a1, (
        "A2 made no tool calls — it silently collapsed to A1, so no A2 result "
        "from this configuration can be trusted. Check the Advisor's tool "
        "wiring before interpreting any bench output."
    )


@pytest.mark.asyncio
async def test_bench_matrix(di_container):
    """The full run. Env-configurable so it can be narrowed without edits.

    DIALEXITY_BENCH_ARMS        comma-separated (default: A0,A1,A1.7,A2)
    DIALEXITY_BENCH_SCENARIOS   comma-separated keys (default: all)
    DIALEXITY_BENCH_TIERS       comma-separated labels (default: weak,strong)
    DIALEXITY_BENCH_REPLICATES  int (default: 1)
    DIALEXITY_BENCH_BRANCHES    comma-separated (default: all declared)
    DIALEXITY_BENCH_JUDGE_OFF   set to skip judging (machine scores only)
    DIALEXITY_BENCH_STEM        output filename stem (default: matrix)

    Asserts only that cells ran without erroring. Whether the framework wins is
    the report's content, not this test's pass condition — a bench that fails
    when the result is negative cannot report a negative result.
    """
    tiers = _csv("DIALEXITY_BENCH_TIERS")
    config = BenchConfig.from_env(tiers=tiers)
    arms = [Arm(a) for a in _csv("DIALEXITY_BENCH_ARMS") or [a.value for a in DEFAULT_ARMS]]
    scenarios = _csv("DIALEXITY_BENCH_SCENARIOS")
    branches = _csv("DIALEXITY_BENCH_BRANCHES")
    replicates = int(os.getenv("DIALEXITY_BENCH_REPLICATES", "1"))
    stem = os.getenv("DIALEXITY_BENCH_STEM", "matrix")

    _say(
        f"tiers={config.tiers} arms={[a.value for a in arms]} "
        f"scenarios={scenarios or 'all'} replicates={replicates} "
        f"branches={branches or 'all'}"
    )

    run = BenchRun(di_container, config)
    await run.run_matrix(
        arms=arms,
        scenario_keys=scenarios,
        replicates=replicates,
        branches=branches,
        progress=_say,
    )
    run.score_machine()
    # Save before judging: the matrix is the expensive part, and judging can be
    # redone from the saved records for a fraction of the cost.
    run.save(OUTPUT_DIR, stem=f"{stem}-runs")

    if not os.getenv("DIALEXITY_BENCH_JUDGE_OFF"):
        await run.judge_wobbles(progress=_say)
        pairs = [p for p in JUDGED_PAIRS if p[0] in arms and p[1] in arms]
        await run.judge_pairs(pairs=pairs, progress=_say)

    json_path, report_path = run.save(OUTPUT_DIR, stem=stem)
    _say(run.report())
    _say(f"\nrecords: {json_path}\nreport:  {report_path}")

    failed = [r for r in run.runs if r.error]
    assert not failed, "cells errored: " + "; ".join(
        f"{r.arm.value}/{r.tier}/{r.scenario_key}: {r.error}" for r in failed
    )


def _csv(name: str) -> list[str] | None:
    raw = os.getenv(name)
    if not raw:
        return None
    return [part.strip() for part in raw.split(",") if part.strip()]
