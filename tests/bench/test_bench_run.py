"""
Entry points that actually spend money. `--real-llm` only.

Three of them, deliberately:

- `test_bench_preflight` — seconds, cents. Every configured model must actually
  answer under the current settings. Run it FIRST.
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
async def test_bench_preflight(di_container):
    """Every configured model must produce non-empty text under current settings.

    This exists because of a real two-hour loss. An extended-thinking request
    shape unsupported by one tier made every strong-tier Advisor turn 400; the
    turns recorded EMPTY TEXT, so the arm looked like a model that declined to
    use its tools rather than one that was never reached.

    Empty text is the signal, and it needs no Advisor: the fault is in the
    request, so one plain chat turn per model reproduces it. Deliberately NOT
    asserting a tool call — the Advisor often asks a clarifying question before
    anchoring, so "no tools on turn 1" is normal behaviour and asserting it
    would make this fail on healthy configurations. Whether A2 ever builds a
    graph is `collapsed_to_a1`'s job, over a whole run.

    Cheap by construction: one short turn per distinct model, no graph, no
    pipeline. Run it before spending a matrix.
    """
    from bench.arms import PromptArm
    from bench.driver import BENCH_PERSONA
    from bench.modelctx import using_model
    from bench.models import Arm

    config = BenchConfig.from_env()
    roles: dict[str, list[str]] = {}
    for label, model in config.tiers.items():
        roles.setdefault(model, []).append(f"tier:{label}")
    roles.setdefault(config.simulator_model, []).append("simulator")
    roles.setdefault(config.judge_model, []).append("judge")

    failures: list[str] = []
    for model, model_roles in roles.items():
        who = ",".join(model_roles)
        arm = PromptArm(Arm.A0, BENCH_PERSONA)
        with using_model(di_container, model):
            try:
                text = await arm.reply("Reply with the single word: ready.")
            except Exception as e:  # noqa: BLE001 - report all, not just first
                failures.append(f"{who} ({model}): {type(e).__name__}: {e}")
                continue
        _say(f"{who:20} {model}\n  chars={len(text)} {text[:60]!r}")
        if not text.strip():
            failures.append(
                f"{who} ({model}): answered with EMPTY TEXT — the request is "
                f"being rejected; check thinking/settings compatibility"
            )

    assert not failures, (
        "preflight failed; do NOT spend a matrix until these are fixed:\n  "
        + "\n  ".join(failures)
    )


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
