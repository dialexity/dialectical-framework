"""The view turn with `_OPPOSING_POSITION_ASK` in its request — before/after.

On the pipeline probe's auditors the Consultant's view turn drew a genuine
opposing POSITION for 30/40 antitheses and a plain mirror for 6 ("Saying no to
clients" for "I always say yes to clients"), where the one-shot build, whose
request carries `_OPPOSING_POSITION_ASK`, drew 36–38/40
(`probe_view_turn_audit.py`, 2026-10-02). The ask went into
`view_sketch_prompt` the same day; this re-draws the same 40 utterances the
way the pre-MVP does (`Consultant(app_preamble=COUNSELOR_PERSONA)`,
`exploration_view(focus=…)`), scores them with the same coherence judge and
the same three auditors, and pairs them against the pre-ask file.

    poetry run pytest tests/e2e/probe_view_turn_ask.py --real-llm -q -s

Knobs (env): `VIEW_TURN_ATTEMPTS=N` best-of-N; `VIEW_TURN_PROBE_TAG` names the
file; `VIEW_TURN_PIN=1` pins the utterance VERBATIM as the thesis
(`exploration_view(thesis=)`, the first app's contract); `VIEW_TURN_BLIND=1`
restores the selection as it was before 2026-10-13 (judge without context, DV
off the ranking). With N > 1 each row also records the runners-up (`spares`),
the chosen antithesis's lexical similarity to each spare's (`SequenceMatcher`
— NOT a read of sameness: identical draws reworded sit at a 0.55 median, the
read is `probe_spare_distinctness.py`) and the kind auditor's verdict on
every spare.

The different-opposition arm (2026-10-13, files `view_turn_pin_arm-*`): draw
2..N of a pinned request carried `DIFFERENT_OPPOSITION_ASK` below, so the
draws differed by the opposition and not by wording. Measured against the
identical-draw control the same afternoon and REJECTED on the pre-registered
"must not move" conditions (winner CC 19/40 against 27/40, positions 34
against 37, 1.26x the seconds); the per-draw request plumbing came out of
`src/` with it, so re-running that arm means restoring a `draw`/`drawn`
argument on `view_sketch_prompt` and the per-draw request list in
`Consultant.exploration_view` (this change's own commit has both) and
appending the ask for draw > 1.
"""

from __future__ import annotations

import asyncio
import os
import collections
import json
import time
from pathlib import Path

import pytest

from e2e.config import E2EConfig
from e2e.probe_aspect_variants import _judge
from e2e.probe_tetrad_quality import (SET_A, SET_B, _audit_kind,
                                      _audit_parentage, _audit_pluses, _wilson)

#: The rejected arm's ask, verbatim, for draw k of n (k >= 2). Kept here and
#: not in `src/`, like the rejected judges (`probe_joint_judge_stability.py`),
#: so nobody wires a measured-worse lever back in by finding it there.
#: {aside}: "the most direct one" for draw 2, "the 2 most direct" for draw 3.
DIFFERENT_OPPOSITION_ASK = (
    "This is draw {draw} of {drawn}, drawn at the same time over the same "
    "words. Draw 1 builds on the opposition that comes first; yours builds on "
    "a DIFFERENT one. Before choosing the antithesis, list the positions a "
    "reasonable person actually holds against the thesis, the most direct "
    "first; set {aside} aside and build the tetrad on the next. A different "
    "axis of disagreement, not the first opposition re-worded or softened; "
    "still a position someone holds, by the ask above; the thesis itself "
    "unchanged."
)

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_BEFORE = _RESULTS / "path_a_cc-20261001.json"

#: The pre-MVP's ask (`tests/probe_blindspot_paths.py`), verbatim.
FOCUS = (
    "the perspective for what I just said: my position, what it stands against, "
    "and above all the constructive side of that opposing view that I am not seeing"
)


def _fmt(k: int, n: int) -> str:
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)"


_POLES = ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")


def _texts(view) -> dict:
    return {
        name: (pole.text if pole else None)
        for name, pole in zip(_POLES, (view.t, view.a, view.t_plus, view.t_minus, view.a_plus, view.a_minus))
    }


def _similarity(a: str | None, b: str | None) -> float | None:
    from difflib import SequenceMatcher

    if not a or not b:
        return None
    return round(SequenceMatcher(None, a.lower(), b.lower()).ratio(), 2)


async def _draw(text: str) -> dict:
    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant

    head = Consultant(
        app_preamble=COUNSELOR_PERSONA, messages=[{"role": "user", "content": text}]
    )
    started = time.perf_counter()
    try:
        attempts = int(os.environ.get("VIEW_TURN_ATTEMPTS", "1") or 1)
        thesis = text if os.environ.get("VIEW_TURN_PIN") else None
        view = await head.exploration_view(focus=FOCUS, attempts=attempts, thesis=thesis)
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        return {"utterance": text, "error": repr(exc), "seconds": round(time.perf_counter() - started, 1)}
    first = view.perspectives[0] if view.perspectives else None
    row = {"utterance": text, "seconds": round(time.perf_counter() - started, 1), "drawn": first is not None}
    if first is not None:
        row.update(_texts(first))
        row["spares"] = [_texts(r) for r in view.runners_up]
        row["spare_a_similarity"] = [
            _similarity(row["antithesis"], spare["antithesis"]) for spare in row["spares"]
        ]
        row["failed_draws"] = [f.kind for f in view.failed_draws]
    return row


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_view_turn_with_the_ask(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    utterances = list(SET_A) + list(SET_B)
    import os

    tag = os.environ.get("VIEW_TURN_PROBE_TAG", "ask")
    out = _RESULTS / f"view_turn_{tag}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    if os.environ.get("VIEW_TURN_BLIND"):
        # The selection as it was before 2026-10-13: the judge called with no
        # context and DV absent from the ranking — so the control arm's own
        # two corrections can be read apart from the pin.
        from dialectical_framework.concerns import tetrad_candidates, view_sketch

        view_sketch.judge_context = lambda texts, budget=0: ""  # type: ignore[assignment]
        tetrad_candidates.SketchVerdict.dialectical_validity = property(lambda self: None)  # type: ignore[assignment]
    print(f"\n=== view turn WITH the opposing-position ask: {len(utterances)} utterances → {out}", flush=True)
    print(f"    attempts={os.environ.get('VIEW_TURN_ATTEMPTS', '1')} pin={bool(os.environ.get('VIEW_TURN_PIN'))} blind={bool(os.environ.get('VIEW_TURN_BLIND'))}", flush=True)

    rows: list[dict] = []
    # Ten draws in flight; with VIEW_TURN_ATTEMPTS=N each draw is N calls, so
    # the batch shrinks to keep the same number of provider calls in flight.
    batch = max(1, 10 // int(os.environ.get("VIEW_TURN_ATTEMPTS", "1") or 1))
    for start in range(0, len(utterances), batch):
        rows += await asyncio.gather(*(_draw(u) for u in utterances[start : start + batch]))
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"  drawn {len(rows)}/{len(utterances)}", flush=True)

    complete = [r for r in rows if all(r.get(k) for k in ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus"))]
    verdicts = await asyncio.gather(*(_judge(r) for r in complete))
    for row, verdict in zip(complete, verdicts):
        row.update(verdict)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    # Auditors run under `using_model`, which re-points the container: one at a time.
    for index, row in enumerate(complete, 1):
        row.update(await _audit_kind(di_container, judge, row["thesis"], row["antithesis"]))
        row.update(await _audit_parentage(di_container, judge, row))
        row.update(await _audit_pluses(di_container, judge, row))
        for spare in row.get("spares", []):
            if spare.get("thesis") and spare.get("antithesis"):
                spare.update(await _audit_kind(di_container, judge, spare["thesis"], spare["antithesis"]))
        print(f"  [{index}/{len(complete)}] {row.get('a_kind')} {'PASS' if row.get('pass') else 'fail'}  «{row['antithesis']}»  spares {[s.get('a_kind') for s in row.get('spares', [])]} sim {row.get('spare_a_similarity')}", flush=True)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    before: dict[str, dict] = {}
    if _BEFORE.exists():
        for items in json.loads(_BEFORE.read_text()).values():
            for item in items:
                before[item["utterance"]] = item
    kinds = collections.Counter(r.get("a_kind") for r in complete)
    restated = sum(
        1 for r in complete for s in ("t_plus", "a_plus")
        if r.get(f"{s}_parent") == "own_pole" and r.get(f"{s}_valence_ok") is False
    )
    paired = [0, 0, 0, 0]
    for r in complete:
        b = before.get(r["utterance"])
        if b is None:
            continue
        a_pass, b_pass = bool(r.get("pass")), bool(b.get("pass"))
        paired[0 if a_pass and b_pass else 1 if a_pass else 2 if b_pass else 3] += 1
    print("\n--- view turn WITH the ask (sets A+B) ---")
    print(f"  drawn complete  {len(complete)}/{len(utterances)}; errors {sum(1 for r in rows if r.get('error'))}")
    print(f"  CC pass         {_fmt(sum(bool(r.get('pass')) for r in complete), len(complete))}   (before the ask: 24/40)")
    print(f"  A kind          {dict(kinds)}   position {_fmt(kinds.get('position', 0), len(complete))}   (before: 30/40)")
    print(f"  restatement     {restated}/{2*len(complete)} plus slots   (before: 10/80)")
    print(f"  T+/A+ relation  {dict(collections.Counter(r.get('plus_relation') for r in complete))}")
    print(f"  paired CC vs before (both/only after/only before/neither) {paired}")
    # the latest earlier view-turn run of the OTHER tag, for a second baseline
    others = sorted(p for p in _RESULTS.glob("view_turn_*.json") if p != out and "audit" not in p.name)
    if others:
        prev = {r["utterance"]: r for r in json.loads(others[-1].read_text()) if r.get("thesis")}
        prev_restated = sum(1 for r in prev.values() for s in ("t_plus", "a_plus") if r.get(f"{s}_parent") == "own_pole" and r.get(f"{s}_valence_ok") is False)
        prev_cc = sum(bool(r.get("pass")) for r in prev.values())
        prev_pos = sum(1 for r in prev.values() if r.get("a_kind") == "position")
        print(f"  previous view-turn run {others[-1].name}: CC {prev_cc}/{len(prev)}  position {prev_pos}/{len(prev)}  restated {prev_restated}/{2*len(prev)}")
    print(f"  latency median  {sorted(r['seconds'] for r in rows)[len(rows)//2]}s")
    sims = [sim for r in complete for sim in r.get("spare_a_similarity", []) if sim is not None]
    if sims:
        # Did the draws differ? The identical-draw baseline is a 0.79 median
        # (the first app's handoff, 52 cards); a spare below 0.6 is read as a
        # different opposition — a lexical proxy, the kind auditor says if it
        # is a position.
        distinct = sum(1 for r in complete if any((s or 1.0) < 0.6 for s in r.get("spare_a_similarity", [])))
        spare_kinds = collections.Counter(s.get("a_kind") for r in complete for s in r.get("spares", []))
        print(f"  spare A similarity median {sorted(sims)[len(sims)//2]} over {len(sims)} spares   (identical draws: 0.79)")
        print(f"  cards with a distinct spare (sim < 0.6)  {_fmt(distinct, len(complete))}")
        print(f"  spare A kinds   {dict(spare_kinds)}   position {_fmt(spare_kinds.get('position', 0), sum(spare_kinds.values()))}")
        print(f"  failed draws    {sum(len(r.get('failed_draws', [])) for r in rows)}")
