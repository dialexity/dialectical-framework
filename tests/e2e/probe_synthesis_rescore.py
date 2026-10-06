"""Score a synthesis re-run against ITS OWN baseline: both sides audited, crossed order.

`probe_synthesis_rerun.py` audits only the NEW S- and prints the old side's
counts as constants from 2026-10-05, and its pairwise is single-order. That was
right for its first use (the old side was the 10-05 machinery, already
audited) and is wrong for any later one: on 2026-10-06 the wheels were rebuilt
(the DB had been wiped) under the then-current prompt, so the "old" S- of that
run had never been read by anyone. This reads one re-run file and judges both
sides the same way:

- the third-trap auditor (`probe_synthesis_arms_theory2._third_trap`) on the
  OLD S- and the NEW S-, each against that wheel's own T- and A-;
- the S- pairwise in BOTH slot orders, a win counted only when the orders
  agree (`probe_synthesis_arms_rejudge._crossed`, the bench's exact-split rule).

    PROBE_RERUN_FILE=synthesis_rerun-<stamp>.json PROBE_MACHINERY_FILE=wisdom_machinery-<stamp>.json \\
        poetry run pytest tests/e2e/probe_synthesis_rescore.py --real-llm -q -s

Caveat carried from the dev note: the auditor is saturated by the either/or
instruction both prompts now carry, so a tie on it says the two are equally
compliant, not equally insightful.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from e2e.config import E2EConfig
from e2e.probe_synthesis_arms_rejudge import _crossed
from e2e.probe_synthesis_arms_theory2 import _third_trap

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_rescore_both_sides(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    rerun = json.loads((_RESULTS / os.environ["PROBE_RERUN_FILE"]).read_text())
    wheels = {
        r["utterance"]: r
        for r in json.loads((_RESULTS / os.environ["PROBE_MACHINERY_FILE"]).read_text())
        if not r.get("error")
    }
    out = _RESULTS / f"synthesis_rescore-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rows = []
    for it in rerun:
        w = wheels[it["utterance"]]
        row = {
            "utterance": it["utterance"],
            "old": it["old_s_minus"],
            "new": it["new_s_minus"],
            "old_kind": (await _third_trap(di_container, judge, w["t_minus"], w["a_minus"], it["old_s_minus"])).get("kind"),
            "new_kind": (await _third_trap(di_container, judge, w["t_minus"], w["a_minus"], it["new_s_minus"])).get("kind"),
            "new_vs_old": await _crossed(di_container, judge, it["new_s_minus"], it["old_s_minus"]),
        }
        rows.append(row)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"  old {str(row['old_kind']):15} new {str(row['new_kind']):15} pair {row['new_vs_old']:11} «{row['utterance'][:50]}»", flush=True)

    def kinds(key: str) -> str:
        c = [r[key] for r in rows]
        return (f"third_failure {c.count('third_failure')}, traps_restated "
                f"{c.count('traps_restated')}, one_trap {c.count('one_trap')}")

    pair = [r["new_vs_old"] for r in rows]
    print(f"\n--- n={len(rows)}, judge {judge} ---")
    print(f"  third-trap, old S-: {kinds('old_kind')}")
    print(f"  third-trap, new S-: {kinds('new_kind')}")
    print(f"  pairwise new vs old, crossed: new {pair.count('x')}, old {pair.count('y')}, "
          f"same {pair.count('same')}, order-bound {pair.count('order_bound')}")
    print(f"  → {out}")
