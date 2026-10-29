"""
Does the fit judge's new A read see what the first app's judge saw — and how
often is A the granted view on the framework's own saved draws?

The handoff (2026-10-28, retired; its substance is in `docs/dev-notes/antithesis-selection.md`,
"A is the view the author granted"): on the 29
app rows whose conceded clause grants a POSITION, the card's A was that
granted view on 16 (an Opus judge, reviewed), A+ on 3. The framework's gate
(`probe_multiclaim_thesis.py`) had read only A+ against the clause, so the
2026-10-26 null on rule 2 says nothing about A. Two things are measured here,
NOTHING is drawn (~150 small judge calls):

1. THE FRAMEWORK'S SAVED DRAWS (`CONCEDED_A_RESCORE`, a `rules-*.json` of the
   first set, both arms, `attempts=1`): on every conceding case's row, the
   probe's own clause read (`_restates`) taken on A, and the shipped
   `ThesisFitCheck` with its three reads against the case text. Reported: A
   restates the clause per arm (does the prompt's mirror rule move the POLE,
   which the two runs never asked), the judge's `antithesis_already_granted`
   per arm, its agreement with the clause read, and how many rows the new
   read flips from fitting to not fitting under the shipped threshold.

2. THE APP'S ROWS (`CONCEDED_A_APP_ROWS`, its `results.jsonl`; optional): on
   the rows whose clause grants a position, the fit judge's A read against
   the app's `a_not_conceded` grade — agreement, the confusion table, and the
   disagreements listed for a hand read. The judge sees the petition text
   (the same text the app's writer saw) and the card's three texts.

3. THE RE-JUDGE (2026-10-29, the fourth handoff: a granted FACT is not a
   granted position; optional, both env vars):
   `CONCEDED_A_APP_REFERENCE` — a second app `results.jsonl` (the app's judge
   2) whose `clause_is_position` and `a_not_conceded` give the REFERENCE
   verdict per (petition, rep): A is the granted view iff the clause grants a
   position AND A is that view. The rows JUDGED still come from
   `CONCEDED_A_APP_ROWS` (judge 1's wider set), so the fact rows judge 2
   declassified are read too, and a false grant on them counts.
   `CONCEDED_A_PRIOR` — a previous `conceded-a-*.json` of this script; its
   stored fit-judge verdicts on the same rows (app rows by petition and rep,
   framework rows by arm and petition) are the PAIRED CONTROL, so a prompt
   change is read as flips against the reference, not as two unpaired rates.

The judge's model comes from the bench config (`FIT_TIER`, default strong),
as in `probe_thesis_fit_judge.py`; no model id is written here.

    CONCEDED_A_APP_ROWS=../alsotrue-app/.claude/hillclimb/multiclaim-sonnet-5-5/baseline/results.20261028-165702.jsonl \\
    CONCEDED_A_APP_REFERENCE=../alsotrue-app/.claude/hillclimb/multiclaim-sonnet-5-5/baseline/results.jsonl \\
    CONCEDED_A_PRIOR=tests/e2e/results/multiclaim/conceded-a-20261028-095957.json \\
      poetry run pytest tests/e2e/rescore_conceded_a.py --real-llm -q -s

Writes `conceded-a-<stamp>.json` beside the input; never overwrites it.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time
from typing import Any, Optional

import pytest

from e2e.multiclaim_cases import MULTI_CLAIM_CASES, MULTI_CLAIM_CASES_LATE
from e2e.probe_multiclaim_thesis import _restates, _sign_test
from e2e.probe_thesis_fit_judge import _arm_model, _fmt

pytestmark = [pytest.mark.llm]

DEFAULT = "tests/e2e/results/multiclaim/rules-20261026-155457.json"
_CONCURRENCY = 6


def _cases() -> dict[str, Any]:
    return {c.petition_id: c for c in MULTI_CLAIM_CASES + MULTI_CLAIM_CASES_LATE}


async def _fit(gate: asyncio.Semaphore, *, thesis: str, antithesis: str, a_plus: str, text: str) -> dict:
    from dialectical_framework.concerns.thesis_fit_check import ThesisFitCheck

    async with gate:
        try:
            dto = await ThesisFitCheck().score_texts(
                thesis=thesis, antithesis=antithesis, a_plus=a_plus, text=text
            )
        except Exception as exc:  # noqa: BLE001 — a probe records failure
            return {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
    return {
        "fit": round(dto.fit, 3),
        "claim": dto.thesis_is_the_claim,
        "a_granted": dto.antithesis_already_granted,
        "a_plus_granted": dto.a_plus_already_granted,
        "reasoning": (dto.reasoning or "")[:400],
    }


async def _clause(gate: asyncio.Semaphore, drawn: str, clause: str) -> Optional[bool]:
    async with gate:
        return await _restates(drawn, clause)


def _agreement(pairs: list[tuple[bool, bool]]) -> dict:
    """(reference, judge) pairs → the table and the agreement."""
    tp = sum(1 for r, j in pairs if r and j)
    fn = sum(1 for r, j in pairs if r and not j)
    fp = sum(1 for r, j in pairs if not r and j)
    tn = sum(1 for r, j in pairs if not r and not j)
    n = len(pairs)
    return {
        "n": n,
        "agree": f"{tp + tn}/{n}",
        "reference_yes_judge_yes": tp,
        "reference_yes_judge_no": fn,
        "reference_no_judge_yes": fp,
        "reference_no_judge_no": tn,
    }


def _reference(path: Optional[str]) -> Optional[dict[tuple[str, int], dict]]:
    """The app's judge-2 rows keyed by (petition, rep); None when not given."""
    if not path:
        return None
    rows = [json.loads(l) for l in pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]
    return {(r["prompt_id"], r["rep"]): r for r in rows}


def _granted_in(row: dict, key: str) -> bool:
    """The app's verdict: the clause grants a POSITION and the card's pole is
    it. A fact row's grade is None in judge 2's file, so it reads False."""
    return bool(row.get("meta", {}).get("clause_is_position")) and row["grade"].get(key) == 0.0


def _prior(path: Optional[str]) -> tuple[dict[tuple[str, int], dict], dict[tuple[str, str], dict]]:
    """A previous run's stored fit-judge verdicts: app rows by (petition, rep),
    framework rows by (arm, petition). Empty when not given."""
    if not path:
        return {}, {}
    saved = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    app = {(a["petition_id"], a["rep"]): a["fit_judge"] for a in saved.get("app_rows", []) if "fit" in a.get("fit_judge", {})}
    fw = {
        (arm, r["petition_id"]): r["fit_judge"]
        for arm, rows in saved.get("arms", {}).items() for r in rows
        if r.get("fit_judge") and "fit" in r["fit_judge"]
    }
    return app, fw


def _flips(pairs: list[tuple[bool, bool, bool]]) -> dict:
    """(reference, prior, now) → how the paired change reads against the reference."""
    return {
        "n": len(pairs),
        "prior_agree": f"{sum(1 for r, p, _ in pairs if r == p)}/{len(pairs)}",
        "now_agree": f"{sum(1 for r, _, n in pairs if r == n)}/{len(pairs)}",
        "repaired": sum(1 for r, p, n in pairs if p != r and n == r),
        "broken": sum(1 for r, p, n in pairs if p == r and n != r),
        "unchanged_wrong": sum(1 for r, p, n in pairs if p != r and n != r),
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_a_read_on_the_saved_draws_and_the_apps_rows(di_container) -> None:
    from dialectical_framework.concerns.thesis_fit_check import THESIS_FIT_THRESHOLD

    from modelctx import using_model

    cases = _cases()
    model = _arm_model()
    gate = asyncio.Semaphore(_CONCURRENCY)
    report: dict[str, Any] = {"model": model}
    started = time.perf_counter()
    print(f"\n  judge model (bench tier): {model}", flush=True)

    # --- 1. the framework's saved draws ------------------------------------
    path = pathlib.Path(os.environ.get("CONCEDED_A_RESCORE", DEFAULT))
    saved = json.loads(path.read_text(encoding="utf-8"))
    arms = saved["arms"]
    with using_model(di_container, model):
        for name, rows in arms.items():
            conceding = [
                r for r in rows
                if r.get("antithesis") and cases.get(r["petition_id"]) and cases[r["petition_id"]].conceded
            ]
            clause_reads, fits = await asyncio.gather(
                asyncio.gather(*(
                    _clause(gate, r["antithesis"], cases[r["petition_id"]].conceded) for r in conceding
                )),
                asyncio.gather(*(
                    _fit(gate, thesis=r["thesis"], antithesis=r["antithesis"],
                         a_plus=r.get("a_plus") or "", text=cases[r["petition_id"]].text)
                    for r in conceding
                )),
            )
            for r, c, f in zip(conceding, clause_reads, fits):
                r["antithesis_already_granted"] = c
                r["fit_judge"] = f
            print(f"  {name}: {len(conceding)} conceding rows re-read", flush=True)

    w, wo = arms["with_rules"], arms["without_rules"]
    def _judged(rows: list[dict]) -> list[dict]:
        return [r for r in rows if r.get("fit_judge") and "fit" in r["fit_judge"]]
    framework: dict[str, Any] = {
        "file": str(path),
        "conceding_rows": {k: sum(1 for r in v if "antithesis_already_granted" in r) for k, v in arms.items()},
        # The prompt's mirror rule, read at the POLE for the first time.
        "a_restates_the_clause": {
            k: sum(1 for r in v if r.get("antithesis_already_granted") is True) for k, v in arms.items()
        },
        "sign_test_a_restates": _sign_test(w, wo, "antithesis_already_granted"),
        "judge_a_granted": {
            k: sum(1 for r in _judged(v) if r["fit_judge"]["a_granted"] >= 0.5) for k, v in arms.items()
        },
        "judge_a_plus_granted": {
            k: sum(1 for r in _judged(v) if r["fit_judge"]["a_plus_granted"] >= 0.5) for k, v in arms.items()
        },
    }
    pairs = [
        (r["antithesis_already_granted"] is True, r["fit_judge"]["a_granted"] >= 0.5)
        for v in arms.values() for r in _judged(v) if r.get("antithesis_already_granted") is not None
    ]
    framework["judge_against_clause_read"] = _agreement(pairs)
    # What the new read changes in the shipped verdict: rows that fitted on
    # the two old reads and do not on three.
    flipped = 0
    for v in arms.values():
        for r in _judged(v):
            fj = r["fit_judge"]
            old = min(fj["claim"], 1.0 - fj["a_plus_granted"]) >= THESIS_FIT_THRESHOLD
            new = fj["fit"] >= THESIS_FIT_THRESHOLD
            flipped += int(old and not new)
    framework["rows_flipped_fitting_to_not"] = f"{flipped}/{sum(len(_judged(v)) for v in arms.values())}"
    prior_app, prior_fw = _prior(os.environ.get("CONCEDED_A_PRIOR"))
    if prior_fw:
        moved = []
        for name, rows in arms.items():
            for r in _judged(rows):
                before = prior_fw.get((name, r["petition_id"]))
                if before is None:
                    continue
                was, now = before["a_granted"] >= 0.5, r["fit_judge"]["a_granted"] >= 0.5
                if was != now:
                    moved.append({"arm": name, "petition_id": r["petition_id"], "was": was, "now": now,
                                  "antithesis": r["antithesis"]})
        framework["against_prior"] = {
            "paired_rows": sum(1 for name, rows in arms.items() for r in _judged(rows) if (name, r["petition_id"]) in prior_fw),
            "granted_to_not": sum(1 for m in moved if m["was"] and not m["now"]),
            "not_to_granted": sum(1 for m in moved if not m["was"] and m["now"]),
            "moved": moved,
        }
    report["framework_draws"] = framework

    # --- 2. the app's rows -------------------------------------------------
    app_path = os.environ.get("CONCEDED_A_APP_ROWS")
    app_rows: list[dict] = []
    reference = _reference(os.environ.get("CONCEDED_A_APP_REFERENCE"))
    if app_path:
        rows = [json.loads(l) for l in pathlib.Path(app_path).read_text(encoding="utf-8").splitlines() if l.strip()]
        position_rows = [
            r for r in rows
            if r.get("meta", {}).get("clause_is_position") and r["meta"].get("card")
            and cases.get(r["prompt_id"].lstrip("p"))
        ]
        with using_model(di_container, model):
            fits, clause_reads = await asyncio.gather(
                asyncio.gather(*(
                    _fit(gate, thesis=r["meta"]["card"]["position"], antithesis=r["meta"]["card"]["against"],
                         a_plus=r["meta"]["card"]["missing"] or "", text=cases[r["prompt_id"].lstrip("p")].text)
                    for r in position_rows
                )),
                asyncio.gather(*(
                    _clause(gate, r["meta"]["card"]["against"], r["meta"]["conceded"]) for r in position_rows
                )),
            )
        for r, f, c in zip(position_rows, fits, clause_reads):
            # The reference verdict is the judge-2 row when one was given (a
            # fact row there reads "not granted"), else this row's own grade.
            ref = reference.get((r["prompt_id"], r["rep"]), r) if reference is not None else r
            app_rows.append({
                "petition_id": r["prompt_id"], "rep": r["rep"],
                "thesis": r["meta"]["card"]["position"], "antithesis": r["meta"]["card"]["against"],
                "a_plus": r["meta"]["card"]["missing"], "clause": r["meta"]["conceded"],
                "reference_clause_is_position": bool(ref.get("meta", {}).get("clause_is_position")),
                "app_a_conceded": _granted_in(ref, "a_not_conceded"),
                "app_a_plus_conceded": _granted_in(ref, "a_plus_not_conceded"),
                "app_reason": (ref.get("explanation") or {}).get("opposition") or "",
                "clause_read_a": c, "fit_judge": f,
                "prior_a_granted": (prior_app.get((r["prompt_id"], r["rep"])) or {}).get("a_granted"),
            })
        judged = [a for a in app_rows if "fit" in a["fit_judge"]]
        app: dict[str, Any] = {
            "file": app_path, "position_rows": len(position_rows), "judged": len(judged),
            "reference_file": os.environ.get("CONCEDED_A_APP_REFERENCE"),
            "reference_position_rows": sum(1 for a in app_rows if a["reference_clause_is_position"]),
            "app_a_conceded": sum(1 for a in app_rows if a["app_a_conceded"]),
            "judge_a_granted": sum(1 for a in judged if a["fit_judge"]["a_granted"] >= 0.5),
            "clause_read_a": sum(1 for a in app_rows if a["clause_read_a"] is True),
            "judge_against_app": _agreement([
                (a["app_a_conceded"], a["fit_judge"]["a_granted"] >= 0.5) for a in judged]),
            "clause_read_against_app": _agreement([
                (a["app_a_conceded"], a["clause_read_a"] is True) for a in app_rows if a["clause_read_a"] is not None]),
            "judge_a_plus_against_app": _agreement([
                (a["app_a_plus_conceded"], a["fit_judge"]["a_plus_granted"] >= 0.5) for a in judged]),
            "rows_not_fitting_under_the_new_read": sum(
                1 for a in judged if a["fit_judge"]["fit"] < THESIS_FIT_THRESHOLD),
            "rows_not_fitting_under_the_old_reads": sum(
                1 for a in judged
                if min(a["fit_judge"]["claim"], 1.0 - a["fit_judge"]["a_plus_granted"]) < THESIS_FIT_THRESHOLD),
        }
        paired = [
            (a["app_a_conceded"], a["prior_a_granted"] >= 0.5, a["fit_judge"]["a_granted"] >= 0.5)
            for a in judged if a["prior_a_granted"] is not None
        ]
        if paired:
            app["a_read_against_prior"] = _flips(paired)
        report["app_rows"] = app

    report["seconds"] = round(time.perf_counter() - started, 1)
    out = path.with_name(f"conceded-a-{time.strftime('%Y%m%d-%H%M%S')}.json")
    out.write_text(json.dumps({"report": report, "arms": arms, "app_rows": app_rows}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    if app_rows:
        print("\n=== app rows where the fit judge's A read and the app's judge disagree ===")
        for a in app_rows:
            if "fit" not in a["fit_judge"]:
                print(f"[{a['petition_id']} rep{a['rep']}] judge errored: {a['fit_judge'].get('error')}")
                continue
            judge_yes = a["fit_judge"]["a_granted"] >= 0.5
            if judge_yes != a["app_a_conceded"]:
                print(f"[{a['petition_id']} rep{a['rep']}] app conceded={a['app_a_conceded']} "
                      f"(position={a['reference_clause_is_position']}) judge a_granted={a['fit_judge']['a_granted']} "
                      f"prior={a['prior_a_granted']}"
                      f"\n   A: {a['antithesis']}\n   clause: {a['clause'][:160]}\n   app: {a['app_reason'][:200]}"
                      f"\n   judge: {a['fit_judge']['reasoning'][:300]}")
    print(f"\nwrote {out}", flush=True)
