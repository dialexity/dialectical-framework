"""Re-read Ac-/Re- with the theory-faithful auditor: validate it, then re-score.

The endpoint auditor used through 2026-10-06 (the first app's, verbatim) failed
a minus line unless it VISIBLY started from the other side's strength. Three
independent theory reviewers, blind, on 15 staged Re- lines
(`fixtures/re_minus_theory_cases.jsonl`, their verdicts inside) found that
stricter than the papers: half its failures (5/10) were valid, and the real
failures LANDED wrong (in A-, not T-). `probe_transformation_sketch.TransitionVerdict`
encodes what they agreed the theory requires: lands in the right trap, is the
operation degenerated, the operation causing the landing (corrected 2026-10-07).

Two tests, nothing generated:

1. `test_the_auditor_agrees_with_the_theory_judges` — the new auditor, twice,
   on the 15 cases: agreement with the judges' consensus (valid / invalid; the
   two borderline cases reported apart) and with their landing, set beside the
   old auditor's agreement on the same cases.
2. `test_rescore_stored_outputs` — the stored outputs re-read: the staged run
   (`PROBE_STAGED_FILE`) and the one-shot arms (`PROBE_SKETCH_FILE`, paired
   against that file's `current` arm exactly as `probe_transformation_sketch`
   pairs them).

    poetry run pytest tests/e2e/probe_transition_rescore.py --real-llm -q -s \\
        -k agrees
    PROBE_STAGED_FILE=staged_endpoints-<stamp>.json PROBE_SKETCH_FILE=transformation_sketch-<stamp>.json \\
        poetry run pytest tests/e2e/probe_transition_rescore.py --real-llm -q -s -k rescore
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.probe_transformation_sketch import _paired, _transitions

_HERE = Path(__file__).resolve().parent
_RESULTS = _HERE / "results" / "tetrad_quality"
_CONCURRENCY = 6


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _corners_from_case(case: dict[str, Any]) -> tuple[dict[str, str], dict[str, str]]:
    t, tr = case["tension"], case["transformation"]
    corners = {"t": t["T"], "a": t["A"], "t_plus": t["T+"], "t_minus": t["T-"], "a_plus": t["A+"], "a_minus": t["A-"]}
    out = {"action": tr["Ac"], "reflection": tr["Re"], "ac_plus": tr["Ac+"], "ac_minus": tr["Ac-"],
           "re_plus": tr["Re+"], "re_minus": tr["Re-"]}
    return corners, out


async def _judge_all(pairs: list[tuple[dict[str, str], dict[str, str]]]) -> list[Any]:
    gate = asyncio.Semaphore(_CONCURRENCY)

    async def one(c: dict[str, str], o: dict[str, str]) -> Any:
        async with gate:
            return await _transitions(c, o)

    return list(await asyncio.gather(*(one(c, o) for c, o in pairs)))


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_auditor_agrees_with_the_theory_judges(di_container) -> None:
    """Both panels' fixtures, two passes each. Each fixture is set beside the
    auditor that preceded the current one on it: the app's strict auditor for
    the first panel (start must be NAMED), the "starts from T+" check for the
    second (2026-10-07)."""
    judge = E2EConfig.from_env().judge_model
    panels = (
        ("first panel", "re_minus_theory_cases.jsonl", lambda c: bool(c["strict_auditor_re_ends"])),
        ("second panel", "re_minus_tplus_theory_cases.jsonl", lambda c: not c["old_auditor_flagged_starts_from_t_plus"]),
    )
    out = _RESULTS / f"transition_auditor_validation-{time.strftime('%Y%m%d-%H%M%S')}.json"
    record: dict[str, Any] = {}
    print(f"\n--- {out.name} (judge {judge}) ---")
    for label, fixture, previous_pass in panels:
        cases = _read_jsonl(_HERE / "fixtures" / fixture)
        pairs = [_corners_from_case(c) for c in cases]
        with using_model(di_container, judge):
            runs = [await _judge_all(pairs) for _ in range(2)]
        rows = []
        for i, c in enumerate(cases):
            row = {"case": c["case"], "consensus": c["consensus"], "judges_ends_in": c["judges_ends_in"],
                   "previous_auditor_pass": previous_pass(c)}
            for k, run in enumerate(runs):
                v = run[i]
                row[f"run{k}"] = None if v is None else {**v.model_dump(), "re_valid": v.re_valid}
            rows.append(row)
        record[label] = rows
        clear = [r for r in rows if r["consensus"] in ("yes", "no")]

        def agree(pred) -> str:
            n = sum(1 for r in clear if pred(r) == (r["consensus"] == "yes"))
            return f"{n}/{len(clear)}"

        print(f"  {label} ({fixture}, {len(clear)} clear of {len(rows)}):")
        print(f"    previous auditor vs consensus: {agree(lambda r: r['previous_auditor_pass'])}")
        for k in range(2):
            print(f"    current auditor pass {k} vs consensus: {agree(lambda r, k=k: bool(r[f'run{k}'] and r[f'run{k}']['re_valid']))}"
                  f"   landing {sum(1 for r in rows if r[f'run{k}'] and r[f'run{k}']['re_minus_ends_in_t_minus'] == (r['judges_ends_in'] == 'T-'))}/{len(rows)}")
        stable = sum(1 for r in rows if r["run0"] and r["run1"] and r["run0"]["re_valid"] == r["run1"]["re_valid"])
        print(f"    self-agreement: {stable}/{len(rows)}")
        for r in rows:
            if r["consensus"] == "borderline":
                print(f"    borderline case {r['case']}: current auditor valid = {[r[f'run{k}']['re_valid'] if r[f'run{k}'] else None for k in range(2)]}")
        for r in clear:
            verdicts = [bool(r[f"run{k}"] and r[f"run{k}"]["re_valid"]) for k in range(2)]
            if any(v != (r["consensus"] == "yes") for v in verdicts):
                print(f"    disagreement case {r['case']}: consensus {r['consensus']}, auditor {verdicts}: "
                      f"{(r['run0'] or {}).get('reasoning', '')[:180]}")
    out.write_text(json.dumps(record, indent=2, ensure_ascii=False))


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_rescore_stored_outputs(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    out = _RESULTS / f"transition_rescore-{time.strftime('%Y%m%d-%H%M%S')}.json"
    report: dict[str, Any] = {}

    staged_name = os.getenv("PROBE_STAGED_FILE")
    sketch_name = os.getenv("PROBE_SKETCH_FILE")
    assert staged_name or sketch_name, "name a stored file to re-score"

    with using_model(di_container, judge):
        if staged_name:
            items = [i for i in json.loads((_RESULTS / staged_name).read_text()) if "corners" in i and "out" in i]
            verdicts = await _judge_all([(i["corners"], i["out"]) for i in items])
            for i, v in zip(items, verdicts):
                if v is not None:
                    i.update(ac_valid=float(v.ac_valid), re_valid=float(v.re_valid),
                             ac_lands=float(v.ac_minus_ends_in_a_minus), re_lands=float(v.re_minus_ends_in_t_minus),
                             transition_verdict=v.model_dump())
            report["staged"] = items
        if sketch_name:
            tetrads = {t["id"]: t for t in _read_jsonl(_HERE / "fixtures" / "transformation_tetrads.jsonl")}
            rows = [r for r in json.loads((_RESULTS / sketch_name).read_text()) if r.get("out") and "error" not in r["out"]]
            verdicts = await _judge_all([(tetrads[r["id"]], r["out"]) for r in rows])
            for r, v in zip(rows, verdicts):
                if v is not None:
                    r.update(ac_valid=float(v.ac_valid), re_valid=float(v.re_valid),
                             ac_lands=float(v.ac_minus_ends_in_a_minus), re_lands=float(v.re_minus_ends_in_t_minus),
                             transition_verdict=v.model_dump())
            report["sketch"] = rows
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    def rate(rows: list[dict[str, Any]], key: str) -> str:
        got = [r[key] for r in rows if key in r]
        return f"{100 * sum(got) / max(1, len(got)):.0f}%"

    print(f"\n--- {out.name} (judge {judge}) ---")
    if "staged" in report:
        s = report["staged"]
        print(f"  staged ({staged_name}): Ac- valid {rate(s, 'ac_valid')} (lands {rate(s, 'ac_lands')}) | "
              f"Re- valid {rate(s, 're_valid')} (lands {rate(s, 're_lands')})   [old auditor: Ac- {rate(s, 'ac_ends')}, Re- {rate(s, 're_ends')}]")
        for ori in ("T->A", "A->T"):
            sub = [i for i in s if i.get("orientation") == ori]
            print(f"    {ori}: Ac- valid {rate(sub, 'ac_valid')} | Re- valid {rate(sub, 're_valid')}")
    if "sketch" in report:
        rows = report["sketch"]
        for arm in dict.fromkeys(r["arm"] for r in rows):
            sub = [r for r in rows if r["arm"] == arm]
            print(f"  one-shot {arm:12} Ac- valid {rate(sub, 'ac_valid')} (lands {rate(sub, 'ac_lands')}) | "
                  f"Re- valid {rate(sub, 're_valid')} (lands {rate(sub, 're_lands')})   [old: {rate(sub, 'ac_ends')} / {rate(sub, 're_ends')}]")
        for arm in dict.fromkeys(r["arm"] for r in rows):
            if arm == "current":
                continue
            print(f"  {arm} - current: Ac- valid {_paired(rows, arm, 'ac_valid')} | Re- valid {_paired(rows, arm, 're_valid')}")
