"""
The gate for the view turn's ONE re-ask (2026-10-28): when every draw's A is a
view the person's words already grant, one more request names it and asks for
the opposition to the claim actually made.

WHAT IS BEING MEASURED
======================
`Consultant.REDRAW_ON_GRANTED_OPPOSITION` — WITH (the constant on) against
WITHOUT (off, which is what ships since the first run below missed), paired
on the 22 CONCEDING cases of `MULTI_CLAIM_CASES`
(the ones with a `conceded` clause: the only cases the trigger can fire on),
through the view turn at the shipped default `attempts=3` (the trigger reads
the fit judge, which runs only with several draws), the probe's generic
focus, no `thesis=`. The app's run that found the defect pinned nothing
either. Nothing of the WITHOUT arm is new: it is the 2026-10-26 run's shape at
best-of-3.

Every read on the FINAL card is a FRESH judge call, never the selection's own
verdict (the systemic map's rule (d): the selection's verdict flatters its
winner, and on 2026-10-13 a different-opposition draw won the selection and
failed a fresh judge):
- the fit judge's A read (`ThesisFitCheck.antithesis_already_granted` ≥ 0.5),
  the primary — the same prompt the trigger reads, fresh;
- the probe's boolean clause read on A (`_restates`), a second instrument;
- coherence (`_judge`, the control statements) and the antithesis KIND
  (`_audit_kind`): excluding the conceded view can push the writer to the
  strawman end, and a re-draw that wins the selection must also hold on a
  fresh read.

PRE-REGISTERED, before the first call
=====================================
Primary: the final card's A is a granted view (fit judge's A read), counted
    over 22 paired cases. The WITH arm must be LOWER by at least 4 of 22,
    with the sign test over discordant pairs beside it.
Side conditions, both of which must hold or the primary does not count:
    coherence (fresh CC pass) must not fall by more than 3 of 22, and the
    antithesis being a genuine position must not fall by more than 3 of 22.
Reported, no bar: how often the re-ask fired, how often the re-draw was the
    card, the clause read, seconds per card.
A result that misses a bar is reported as a miss; the bars are pinned.

THE FIRST RUN (2026-10-28, Sonnet 5.5 writer, the bench's judge): MISSED.
Fired on 5 of 22; granted A 5 → 4 (discordant 1 win / 2 losses, p = 1.0);
coherence 21 → 18 (the whole allowance); kind 22 against 21. Of the five
re-draws, two became the card with a real opposition, one won still at the
line (0.5), two lost to the original. So the switch ships OFF; this file is
how it is re-measured.

THE SECOND RUN, the writer on Opus 5.5 (`REDRAW_WRITER_MODEL`, judges unchanged):
MISSED again, and the model is not the lever. Fired on 4; granted A 4 → 4
(discordant 1 / 1); coherence 21 against 16 (an arm-level swing four fires
cannot explain — Opus's cards are less stable on a fresh CC read); kind 20
against 20. WITHOUT the re-ask Opus drew the granted view on 4 of 22 against
Sonnet 5.5's 5 — the SAME four petitions (308917, 735371, 763504, 771145) on
both models, in every arm; told not to, Opus re-drew the identical A on two.

    poetry run pytest tests/e2e/probe_granted_opposition_redraw.py --real-llm -q -s

`REDRAW_LIMIT=n` runs the first n conceding cases as a smoke run (not the gate).
`REDRAW_WRITER_MODEL=<provider/model>` runs the WRITER (the view turn, both arms)
on that model while every judge stays on the deployment's default — the arm
that asks whether the model is the lever. Models otherwise come from the
environment and the bench config; none is written here.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time
from typing import Any

import pytest

from e2e.config import E2EConfig
from e2e.multiclaim_cases import MULTI_CLAIM_CASES, MultiClaimCase
from e2e.probe_aspect_variants import _judge
from e2e.probe_multiclaim_thesis import _restates, _sign_test
from e2e.probe_tetrad_quality import _audit_kind
from e2e.probe_view_turn_ask import FOCUS, _texts

pytestmark = [pytest.mark.llm]

RESULTS = pathlib.Path(__file__).parent / "results" / "multiclaim"

BARS: dict[str, int] = {
    "primary_granted_a_min_drop": 4,
    "max_coherence_loss": 3,
    "max_antithesis_kind_loss": 3,
}

CONCEDING: tuple[MultiClaimCase, ...] = tuple(c for c in MULTI_CLAIM_CASES if c.conceded)


async def _draw_one(case: MultiClaimCase, container=None, writer: str | None = None) -> dict[str, Any]:
    """One best-of-3 card over the case's argument. Never sees `case.demand`.
    With `writer`, the whole view turn — draws, selection judges and the
    re-ask — runs on that model (`using_model`); the fresh reads below do not."""
    from contextlib import nullcontext

    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant
    from e2e.modelctx import using_model

    head = Consultant(app_preamble=COUNSELOR_PERSONA, messages=[{"role": "user", "content": case.text}])
    started = time.perf_counter()
    scope = using_model(container, writer) if writer else nullcontext()
    try:
        with scope:
            view = await head.exploration_view(focus=FOCUS, attempts=3)
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        return {"petition_id": case.petition_id, "error": repr(exc),
                "seconds": round(time.perf_counter() - started, 1)}
    first = view.perspectives[0] if view.perspectives else None
    row: dict[str, Any] = {
        "petition_id": case.petition_id,
        "seconds": round(time.perf_counter() - started, 1),
        "drawn": first is not None,
        "reasked_about": head.last_view_redraw,
        "failed_draws": [f.kind for f in view.failed_draws],
        "runners_up": [_texts(p) for p in view.runners_up],
    }
    if first is not None:
        row.update(_texts(first))
        # Did the re-draw become the card? The re-draw is the last candidate;
        # when it wins, the winner's A is not among the originals' As... which
        # we cannot see from here. So: the card's A differs from the granted
        # view named, as a proxy, plus the fresh reads below.
    return row


async def _run_arm(name: str, cases: tuple[MultiClaimCase, ...], batch: int,
                   container=None, writer: str | None = None) -> list[dict]:
    from dialectical_framework.agents.consultant import consultant as module

    rows: list[dict] = []
    previous = module.REDRAW_ON_GRANTED_OPPOSITION
    module.REDRAW_ON_GRANTED_OPPOSITION = name == "with_redraw"
    try:
        for start in range(0, len(cases), batch):
            chunk = cases[start : start + batch]
            rows += await asyncio.gather(*(_draw_one(c, container, writer) for c in chunk))
            print(f"  {name}: drawn {len(rows)}/{len(cases)}", flush=True)
    finally:
        module.REDRAW_ON_GRANTED_OPPOSITION = previous
    return rows


async def _fresh_fit(row: dict, case: MultiClaimCase) -> dict:
    from dialectical_framework.concerns.thesis_fit_check import ThesisFitCheck

    try:
        dto = await ThesisFitCheck().score_texts(
            thesis=row["thesis"], antithesis=row["antithesis"], a_plus=row["a_plus"] or "", text=case.text)
    except Exception as exc:  # noqa: BLE001
        return {"fit_error": repr(exc)}
    return {"fit": round(dto.fit, 3), "a_granted_score": dto.antithesis_already_granted,
            "a_granted": dto.antithesis_already_granted >= 0.5,
            "a_plus_granted": dto.a_plus_already_granted >= 0.5, "fit_reasoning": dto.reasoning[:300]}


def _count(rows: list[dict], key: str) -> int:
    return sum(1 for r in rows if r.get(key) is True)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_one_reask_on_the_conceding_cases(di_container) -> None:
    limit = int(os.environ.get("REDRAW_LIMIT", "0")) or len(CONCEDING)
    cases = CONCEDING[:limit]
    batch = int(os.environ.get("REDRAW_BATCH", "4"))
    print(f"\n=== the one re-ask on {len(cases)} conceding cases, best-of-3, bars {BARS}", flush=True)
    if limit < len(CONCEDING):
        print(f"    SMOKE RUN on {limit} of {len(CONCEDING)} — not the gate")
    writer = os.environ.get("REDRAW_WRITER_MODEL") or None
    if writer:
        print(f"    WRITER on {writer}; judges on the default", flush=True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    tag = "-" + writer.rsplit("/", 1)[-1] if writer else ""
    out = RESULTS / f"redraw{tag}-{time.strftime('%Y%m%d-%H%M%S')}.json"

    arms = {name: await _run_arm(name, cases, batch, di_container, writer)
            for name in ("with_redraw", "without_redraw")}
    out.write_text(json.dumps({"bars": BARS, "arms": arms}, indent=1, ensure_ascii=False))

    by_id = {c.petition_id: c for c in cases}
    judge_model = E2EConfig.from_env().judge_model
    for name, rows in arms.items():
        full = [r for r in rows if r.get("thesis") and r.get("antithesis")
                and all(r.get(k) for k in ("t_plus", "t_minus", "a_plus", "a_minus"))]
        fits, clauses, ccs = await asyncio.gather(
            asyncio.gather(*(_fresh_fit(r, by_id[r["petition_id"]]) for r in full)),
            asyncio.gather(*(_restates(r["antithesis"], by_id[r["petition_id"]].conceded) for r in full)),
            asyncio.gather(*(_judge(r) for r in full)),
        )
        for r, f, c, cc in zip(full, fits, clauses, ccs):
            r.update(f)
            r["a_restates_clause"] = c
            r.update(cc)
        for r in full:  # `using_model` re-points the container: one at a time
            r.update(await _audit_kind(di_container, judge_model, r["thesis"], r["antithesis"]))
        print(f"  {name}: judged {len(full)} cards fresh", flush=True)

    w, wo = arms["with_redraw"], arms["without_redraw"]
    seconds = {k: sorted(r["seconds"] for r in v) for k, v in arms.items()}
    report = {
        "bars": BARS, "cases": len(cases), "is_the_gate": limit == len(CONCEDING),
        "writer_model": writer or "the deployment default",
        "drawn": {k: _count(v, "drawn") for k, v in arms.items()},
        "reask_fired": {k: sum(1 for r in v if r.get("reasked_about")) for k, v in arms.items()},
        # PRIMARY: the fresh fit judge's A read on the final card.
        "a_granted": {k: _count(v, "a_granted") for k, v in arms.items()},
        "sign_test_a_granted": _sign_test(w, wo, "a_granted"),
        "a_restates_clause": {k: _count(v, "a_restates_clause") for k, v in arms.items()},
        "a_plus_granted": {k: _count(v, "a_plus_granted") for k, v in arms.items()},
        "coherence_pass": {k: _count(v, "pass") for k, v in arms.items()},
        "antithesis_a_position": {k: sum(1 for r in v if r.get("a_kind") == "position") for k, v in arms.items()},
        "median_seconds": {k: (s[len(s) // 2] if s else None) for k, s in seconds.items()},
    }
    gain = report["a_granted"]["without_redraw"] - report["a_granted"]["with_redraw"]
    cc_loss = report["coherence_pass"]["without_redraw"] - report["coherence_pass"]["with_redraw"]
    kind_loss = report["antithesis_a_position"]["without_redraw"] - report["antithesis_a_position"]["with_redraw"]
    report["verdict"] = {
        "primary": "CLEARS" if gain >= BARS["primary_granted_a_min_drop"] else "MISSED",
        "primary_drop": gain,
        "coherence": "holds" if cc_loss <= BARS["max_coherence_loss"] else "FAILS",
        "antithesis_kind": "holds" if kind_loss <= BARS["max_antithesis_kind_loss"] else "FAILS",
    }
    out.write_text(json.dumps({"report": report, "arms": arms}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    print("\n=== WITH arm: the cards the re-ask fired on ===")
    for r in w:
        if r.get("reasked_about"):
            print(f"[{r['petition_id']}] re-asked about: {r['reasked_about']}\n   card A: {r.get('antithesis')}"
                  f"\n   fresh A granted={r.get('a_granted')} ({r.get('a_granted_score')}), CC pass={r.get('pass')}, kind={r.get('a_kind')}")
    print(f"\nwrote {out}", flush=True)


class TestTheInstrument:
    def test_registered_bars_cannot_drift(self):
        assert BARS == {"primary_granted_a_min_drop": 4, "max_coherence_loss": 3, "max_antithesis_kind_loss": 3}

    def test_the_shipped_switch_is_off_since_the_gate_missed(self):
        from dialectical_framework.agents.consultant import consultant as module

        assert module.REDRAW_ON_GRANTED_OPPOSITION is False

    def test_the_cases_are_the_conceding_ones(self):
        assert len(CONCEDING) == 22 and all(c.conceded for c in CONCEDING)

    def test_the_writer_never_sees_the_ground_truth(self):
        import ast
        import inspect
        import textwrap

        tree = ast.parse(textwrap.dedent(inspect.getsource(_draw_one)))
        read = {n.attr for n in ast.walk(tree)
                if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "case"}
        assert read == {"text", "petition_id"}
