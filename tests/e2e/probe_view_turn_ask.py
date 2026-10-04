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


async def _draw(text: str) -> dict:
    from dialectical_framework.agents.apps import COUNSELOR_PERSONA
    from dialectical_framework.agents.consultant.consultant import Consultant

    head = Consultant(
        app_preamble=COUNSELOR_PERSONA, messages=[{"role": "user", "content": text}]
    )
    started = time.perf_counter()
    try:
        attempts = int(os.environ.get("VIEW_TURN_ATTEMPTS", "1") or 1)
        view = await head.exploration_view(focus=FOCUS, attempts=attempts)
    except Exception as exc:  # noqa: BLE001 — a probe records failure
        return {"utterance": text, "error": repr(exc), "seconds": round(time.perf_counter() - started, 1)}
    first = view.perspectives[0] if view.perspectives else None
    row = {"utterance": text, "seconds": round(time.perf_counter() - started, 1), "drawn": first is not None}
    if first is not None:
        for name, pole in (
            ("thesis", first.t), ("antithesis", first.a), ("t_plus", first.t_plus),
            ("t_minus", first.t_minus), ("a_plus", first.a_plus), ("a_minus", first.a_minus),
        ):
            row[name] = pole.text if pole else None
    return row


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_view_turn_with_the_ask(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    utterances = list(SET_A) + list(SET_B)
    import os

    tag = os.environ.get("VIEW_TURN_PROBE_TAG", "ask")
    out = _RESULTS / f"view_turn_{tag}-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"\n=== view turn WITH the opposing-position ask: {len(utterances)} utterances → {out}", flush=True)

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
        print(f"  [{index}/{len(complete)}] {row.get('a_kind')} {'PASS' if row.get('pass') else 'fail'}  «{row['antithesis']}»", flush=True)
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
