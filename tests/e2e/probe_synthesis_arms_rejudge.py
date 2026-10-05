"""Re-judge the S- pairs of the synthesis arms with EXACT crossed order.

The measurement review of 2026-10-05 found the 12-5 "arm 2 over machinery"
pairwise in `probe_synthesis_arms_theory2.py` was mostly slot bias: the RNG put
arm 2 in slot A in 12/17 pairs and slot A won 13/17. The bench's rule
(`tests/e2e/README.md`, exact X/Y split) was not followed there nor in
`probe_synthesis_rerun.py`. This judges every pair in BOTH orders and counts a
win only when both orders agree; disagreement is recorded as `order_bound`.

    poetry run pytest tests/e2e/probe_synthesis_arms_rejudge.py --real-llm -q -s
"""

from __future__ import annotations

import glob
import json
import os
import time
from pathlib import Path

import pytest

from e2e.config import E2EConfig
from e2e.probe_synthesis_arms_theory1 import _judge_sminus

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"


def _latest(prefix: str) -> dict:
    path = sorted(glob.glob(str(_RESULTS / f"{prefix}-*.json")), key=os.path.getmtime)[-1]
    return {it["utterance"]: it for it in json.loads(Path(path).read_text())}


async def _crossed(container, judge, x: str, y: str) -> str:
    """'x' / 'y' when both orders agree, else 'order_bound'; 'same' when both say same."""
    a = await _judge_sminus(container, judge, x, y)   # x in slot A
    b = await _judge_sminus(container, judge, y, x)   # y in slot A
    first = {"A": "x", "B": "y", "same": "same", None: None}[a.get("sharper")]
    second = {"A": "y", "B": "x", "same": "same", None: None}[b.get("sharper")]
    return first if first == second else "order_bound"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_rejudge_with_crossed_order(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    arm2 = _latest("wisdom_theory_prompt2"); rerun = _latest("synthesis_rerun")
    out = _RESULTS / f"synthesis_arms_rejudge-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rows = []
    for u, it in arm2.items():
        old = it["machinery"]["s_minus"]; a2 = it["prompt2"]["s_minus"]; new = rerun[u]["new_s_minus"]
        row = {"utterance": u, "old": old, "arm2": a2, "new": new}
        row["arm2_vs_old"] = await _crossed(di_container, judge, a2, old)      # x=arm2 y=old
        row["new_vs_old"] = await _crossed(di_container, judge, new, old)      # x=new  y=old
        row["new_vs_arm2"] = await _crossed(di_container, judge, new, a2)      # x=new  y=arm2
        rows.append(row); out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
        print(f"  {row['arm2_vs_old']:11} {row['new_vs_old']:11} {row['new_vs_arm2']:11}  «{u[:50]}»", flush=True)
    def tally(key, x, y):
        c = [r[key] for r in rows]
        return f"{x} {c.count('x')}, {y} {c.count('y')}, same {c.count('same')}, order-bound {c.count('order_bound')}"
    print("\n--- S- blind pairwise, exact crossed order (n=17) ---")
    print(f"  arm 2 vs old machinery : {tally('arm2_vs_old', 'arm2', 'old')}   (biased single-order read was 12-5)")
    print(f"  new machinery vs old   : {tally('new_vs_old', 'new', 'old')}   (single-order: 10-7)")
    print(f"  new machinery vs arm 2 : {tally('new_vs_arm2', 'new', 'arm2')}   (single-order: 7-10)")
    print(f"  → {out}")
