"""Replay the first app's retry cards on a model and account for every draw.

Built for a host handoff (2026-10-09, framework 2.0.7 on Sonnet 5.5 / Opus 5.5)
that asked three things this probe answers in one run:

1. **Where do the lost draws go?** On Opus 5.5 the app's best-of-3 lost 8 of 240
   view-turn draws (6 cards drew 2, one drew 1) with no cause on record: the
   gather swallowed them and the census never saw a call it could not record.
   Every failed draw now lands on `ExplorationView.failed_draws` with its
   exception type (and refusal category), and this probe prints them.
2. **Do the JSON-mode parse re-asks stop?** On Sonnet 5.5 the app measured 32
   re-asks in 80 cards (25 on `TransformationSketchDto`, 7 on `ViewSketchDto`).
   JSON-mode calls on the 5.5 models are now sent as structured outputs
   (`format_compat.structured_output_format`); `DIALEXITY_PROBE_STRUCTURED=0`
   runs the same cards without it, for a before/after on the re-ask count.
3. **Where does an Opus 5.5 card's time go?** Per call type, from the census:
   the three view draws (parallel), the coherence judge (six calls, parallel),
   and `TransformationSketch` — the framework's share of the app's card. The
   app's own wisdom-text and shift-classifier calls are not here.

The cards are the app's FROZEN first cards (`alsotrue-app/backend/evals/
retry_routing/cases/cards/*.json`) and its case notes (`cases.jsonl`), replayed
as the app replays them: a new `Consultant(app_preamble=COUNSELOR_PERSONA)` over
the person's utterance plus the card's record, the app's retry ask (its v2 text,
copied here so no app code is on the path), `attempts=3`, then
`TransformationSketch` on the drawn tetrad.

    poetry run pytest tests/e2e/probe_card_replay.py --real-llm -q -s
    DIALEXITY_PROBE_MODELS=global.anthropic.claude-opus-5-5 \\
    DIALEXITY_PROBE_CASES=brother-none,manager-steer,parents-change \\
    DIALEXITY_PROBE_REPS=3 DIALEXITY_PROBE_CONCURRENCY=4 \\
    DIALEXITY_PROBE_THINKING=settings|low|none  DIALEXITY_PROBE_STRUCTURED=1|0 \\
    DIALEXITY_PROBE_JUDGE_MODEL=global.anthropic.claude-sonnet-5-5

Results: `tests/e2e/results/tetrad_quality/card_replay-<model>-<ts>.json`.
"""

from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any, Optional

import pytest

from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.concerns.transformation_sketch import TransformationSketch
from dialectical_framework.settings_context import using_settings
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.retry_accounting import retry_account

_HERE = Path(__file__).resolve().parent
_RESULTS = _HERE / "results" / "tetrad_quality"
_APP_CASES = Path(
    os.getenv(
        "ALSOTRUE_CASES_DIR",
        str(_HERE.parents[2] / "alsotrue-app" / "backend" / "evals" / "retry_routing" / "cases"),
    )
)

MODELS = [
    m.strip()
    for m in os.getenv("DIALEXITY_PROBE_MODELS", "global.anthropic.claude-opus-5-5").split(",")
    if m.strip()
]
REPS = int(os.getenv("DIALEXITY_PROBE_REPS", "2"))
CONCURRENCY = int(os.getenv("DIALEXITY_PROBE_CONCURRENCY", "4"))
#: The cards that lost draws in the app's Opus 5.5 run, by default.
CASES = [
    c.strip()
    for c in os.getenv(
        "DIALEXITY_PROBE_CASES",
        "brother-none,manager-steer,parents-change,quit-correction,quit-borderline,remote-borderline",
    ).split(",")
    if c.strip()
]
#: "settings" = as the app runs it (the deployment default, medium);
#: "none" = thinking off; any level name otherwise.
THINKING = os.getenv("DIALEXITY_PROBE_THINKING", "settings")
STRUCTURED = os.getenv("DIALEXITY_PROBE_STRUCTURED", "1") != "0"
#: A model for the coherence judge alone (`ControlStatementsCheck.score_texts`),
#: e.g. a Sonnet beside an Opus writer — TIME only; a cheaper judge's verdicts
#: are gated by `probe_joint_judge_stability.py`, not by this.
JUDGE_MODEL = os.getenv("DIALEXITY_PROBE_JUDGE_MODEL", "")


@pytest.fixture(autouse=True)
def cleanup_graph_db():
    yield


@pytest.fixture(autouse=True)
def cleanup_test_graph_data():
    yield


# --- The app's retry ask (alsotrue-app `alsotrue/tetrad.py::focus_retry`, v2) ---


def _focus_retry(position: str, against: str, note: Optional[str]) -> str:
    shown = f'the card "{position}" against "{against}"'
    quote = f' — in their words: "{note.strip()}"' if note and note.strip() else ""
    lead = f"The person set aside {shown}{quote}. "
    if note and note.strip():
        return lead + (
            "Read their words first. If they state their position, take THAT as "
            "the position, find what it genuinely stands against, and draw that "
            "tetrad. If they ask for this same card changed — sharper, simpler, "
            "in other words, in their particulars, more concrete, what to actually "
            "do — keep BOTH the position and what it stands against exactly as "
            "they are; change only the four corners and the wording. Otherwise "
            "their words say what the next tension should be ABOUT: keep their "
            "position as it stands and find a different opposition to it in what "
            "they said — one they have not seen, not the shown one re-worded — and "
            "above all the constructive side of that opposing view. Their words "
            "are not the new position."
        )
    return lead + (
        "Draw one tension they have NOT seen yet: keep their position as it "
        "stands and find a different opposition to it in what they said — not "
        "the shown one re-worded — and above all the constructive side of the "
        "opposing view they are not seeing."
    )


def _load_cases() -> list[dict[str, Any]]:
    by_id = {}
    for line in (_APP_CASES / "cases.jsonl").read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            by_id[row["id"]] = row
    out = []
    for case_id in CASES:
        case = by_id[case_id]
        card = json.loads((_APP_CASES / "cards" / f"{case['card']}.json").read_text())
        out.append(
            {
                "id": case_id,
                "note": case.get("note"),
                "messages": [{"role": "user", "content": card["utterance"]}, *card["record"]],
                "focus": _focus_retry(card["payload"]["position"], card["payload"]["against"], case.get("note")),
                "utterance": card["utterance"],
            }
        )
    return out


def _phase(calls, label: str) -> dict[str, Any]:
    sel = [c for c in calls if c.format_name == label]
    if not sel:
        return {"n": 0}
    return {
        "n": len(sel),
        "provider_s": round(sum(c.seconds for c in sel), 1),
        "wall_s": round(max(c.ended for c in sel) - min(c.started for c in sel), 1),
        "median_s": round(statistics.median(c.seconds for c in sel), 1),
        "out_tokens": sum(c.output_tokens or 0 for c in sel),
    }


async def _card(case: dict[str, Any], rep: int) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if THINKING == "none":
        kwargs["thinking"] = None
    elif THINKING != "settings":
        kwargs["thinking"] = THINKING
    head = Consultant(app_preamble=COUNSELOR_PERSONA, messages=list(case["messages"]), **kwargs)
    started = time.monotonic()
    row: dict[str, Any] = {"case": case["id"], "rep": rep, "error": None, "sketch_error": None}
    with call_census() as census, retry_account() as retries:
        try:
            view = await head.exploration_view(focus=case["focus"], attempts=3)
            row["view_s"] = round(time.monotonic() - started, 1)
            row["drawn"] = len(view.perspectives)
            row["runners_up"] = len(view.runners_up)
            row["failed_draws"] = [f.to_dict() for f in view.failed_draws]
            first = view.perspectives[0] if view.perspectives else None
            row["position"] = first.t.text if first and first.t else None
            row["against"] = first.a.text if first and first.a else None
            sketch_started = time.monotonic()
            if first is not None and first.complete:
                try:
                    await TransformationSketch().resolve(first, material=case["utterance"])
                except Exception as exc:  # noqa: BLE001
                    row["sketch_error"] = f"{type(exc).__name__}: {exc}"
            row["sketch_s"] = round(time.monotonic() - sketch_started, 1)
        except Exception as exc:  # noqa: BLE001 - a failed card is a row
            row["error"] = f"{type(exc).__name__}: {exc}"
    row["seconds"] = round(time.monotonic() - started, 1)
    row["retries"] = dict(retries.kinds)
    row["calls"] = len(census.calls)
    row["phases"] = {
        "view": _phase(census.calls, "ViewSketchDto"),
        "judge": _phase(census.calls, "CoherenceEvaluationDto"),
        "sketch": _phase(census.calls, "TransformationSketchDto"),
    }
    row["output_tokens"] = sum(c.output_tokens or 0 for c in census.calls)
    return row


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in rows if not r["error"]]
    secs = sorted(r["seconds"] for r in ok)
    failed = [f for r in ok for f in r.get("failed_draws", [])]
    def med(key, phase=None):
        vals = [(r["phases"][phase][key] if phase else r[key]) for r in ok if (not phase or r["phases"][phase].get("n"))]
        return round(statistics.median(vals), 1) if vals else None
    return {
        "cards": len(rows),
        "errors": sum(1 for r in rows if r["error"]),
        "draws": sum(r["phases"]["view"]["n"] for r in ok),
        "failed_draws": len(failed),
        "failed_by_kind": {k: sum(1 for f in failed if f["kind"] == k) for k in {f["kind"] for f in failed}},
        "cards_short_of_3": sum(1 for r in ok if r.get("drawn", 0) + r.get("runners_up", 0) < 3),
        "parse_retries": sum(r["retries"].get("parse", 0) for r in ok),
        "view_calls_per_card": round(sum(r["phases"]["view"]["n"] for r in ok) / max(1, len(ok)), 2),
        "sketch_calls_per_card": round(sum(r["phases"]["sketch"]["n"] for r in ok) / max(1, len(ok)), 2),
        "card_s": {"median": med("seconds"), "p90": secs[int(0.9 * (len(secs) - 1))] if secs else None, "max": secs[-1] if secs else None},
        "view_wall_s": med("wall_s", "view"),
        "view_draw_median_s": med("median_s", "view"),
        "judge_wall_s": med("wall_s", "judge"),
        "judge_call_median_s": med("median_s", "judge"),
        "sketch_s": med("median_s", "sketch"),
        "output_tokens": med("output_tokens"),
    }


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_card_replay(di_container, monkeypatch) -> None:
    if not STRUCTURED:
        from dialectical_framework.utils import bedrock_provider

        monkeypatch.setattr(bedrock_provider, "structured_output_format", lambda *_: None)
    if JUDGE_MODEL:
        from dialectical_framework.concerns.control_statements_check import ControlStatementsCheck
        from dialectical_framework.settings_context import get_current_settings

        judged = ControlStatementsCheck.score_texts

        async def on_judge_model(self, *args, **kwargs):
            current = get_current_settings()
            with using_settings(current.model_copy(update={"reasoning_model": f"bedrock/{JUDGE_MODEL}"})):
                return await judged(self, *args, **kwargs)

        monkeypatch.setattr(ControlStatementsCheck, "score_texts", on_judge_model)
    cases = _load_cases()
    for model in MODELS:
        short = model.split("claude-")[-1]
        out = _RESULTS / f"card_replay-{short}-{time.strftime('%Y%m%d-%H%M%S')}.json"
        settings = di_container.settings().model_copy(update={"ai_model": f"bedrock/{model}", "reasoning_model": None})
        rows: list[dict[str, Any]] = []
        sem = asyncio.Semaphore(CONCURRENCY)

        async def one(case, rep):
            async with sem:
                row = await _card(case, rep)
            rows.append(row)
            fails = ", ".join(f"{f['kind']}{'(' + f['category'] + ')' if f.get('category') else ''}" for f in row.get("failed_draws", []))
            print(
                f"  {row['case']:18s} rep{rep} {row['seconds']:5.1f}s calls {row['calls']:2d} "
                f"view {row['phases']['view']['n']} judge {row['phases']['judge']['n']} sketch {row['phases']['sketch']['n']} "
                f"retries {row['retries'] or '-'} failed [{fails}] {('ERR ' + row['error']) if row['error'] else ''}",
                flush=True,
            )
            out.write_text(json.dumps({"model": model, "thinking": THINKING, "structured": STRUCTURED, "rows": rows}, indent=2, ensure_ascii=False, default=str))

        print(f"\n== {model} thinking={THINKING} structured={STRUCTURED} judge={JUDGE_MODEL or 'same'} cases={len(cases)} reps={REPS}")
        with using_settings(settings):
            await asyncio.gather(*(one(case, rep) for rep in range(REPS) for case in cases))
        summary = _summary(rows)
        out.write_text(json.dumps({"model": model, "thinking": THINKING, "structured": STRUCTURED, "judge_model": JUDGE_MODEL or None, "summary": summary, "rows": rows}, indent=2, ensure_ascii=False, default=str))
        print(f"--- {out.name}")
        print(json.dumps(summary, indent=1))
