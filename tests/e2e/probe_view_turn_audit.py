"""Put the Consultant's view-turn tetrads on the pipeline probe's own auditors.

`path_a_cc-20261001.json` holds the 40 tetrads the view turn drew (sets A+B)
with their coherence verdicts, but their antitheses were only ever read by
hand ("20/20 genuine, one rater") and their pluses never audited at all. The
one-shot build's figures (36–38/40 position, 6.9% restatement) come from
`probe_tetrad_quality`'s LLM auditors, so the two columns did not mean the
same thing. This runs the SAME three auditors over the view-turn rows.

Sequential per row on purpose: concurrent `using_model` blocks restore each
other's override (found by a subagent, 2026-10-01).

    poetry run pytest tests/e2e/probe_view_turn_audit.py --real-llm -q -s
"""

from __future__ import annotations

import collections
import json
import time
from pathlib import Path

import pytest

from e2e.config import E2EConfig
from e2e.probe_tetrad_quality import (_audit_kind, _audit_parentage,
                                      _audit_pluses, _wilson)

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_SOURCE = _RESULTS / "path_a_cc-20261001.json"


def _fmt(k: int, n: int) -> str:
    lo, hi = _wilson(k, n)
    return f"{k}/{n} ({100*k/max(n,1):.0f}%, 95% {100*lo:.0f}–{100*hi:.0f}%)"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_audit_view_turn_tetrads(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    source = json.loads(_SOURCE.read_text())
    rows: list[dict] = []
    for set_name, items in source.items():
        for item in items:
            if not item.get("drawn"):
                continue
            rows.append(
                {
                    "set": set_name,
                    "utterance": item["utterance"],
                    "thesis": item["t"],
                    "antithesis": item["a"],
                    "t_plus": item["t_plus"],
                    "t_minus": item["t_minus"],
                    "a_plus": item["a_plus"],
                    "a_minus": item["a_minus"],
                    "cc_pass": bool(item.get("pass")),
                }
            )
    out = _RESULTS / f"view_turn_audit-{time.strftime('%Y%m%d-%H%M%S')}.json"
    print(f"\n=== auditing {len(rows)} view-turn tetrads with {judge} → {out}", flush=True)
    for index, row in enumerate(rows, 1):
        row.update(await _audit_kind(di_container, judge, row["thesis"], row["antithesis"]))
        row.update(await _audit_parentage(di_container, judge, row))
        row.update(await _audit_pluses(di_container, judge, row))
        print(f"  [{index}/{len(rows)}] {row.get('a_kind')}  «{row['antithesis']}»", flush=True)
        out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    kinds = collections.Counter(r.get("a_kind") for r in rows)
    restated = sum(
        1
        for r in rows
        for side in ("t_plus", "a_plus")
        if r.get(f"{side}_parent") == "own_pole" and r.get(f"{side}_valence_ok") is False
    )
    relation = collections.Counter(r.get("plus_relation") for r in rows)
    print(f"\n--- the view turn's 40 tetrads on the pipeline probe's auditors ---")
    print(f"  CC pass (from the file) {_fmt(sum(r['cc_pass'] for r in rows), len(rows))}")
    print(f"  A kind        {dict(kinds)}   position {_fmt(kinds.get('position', 0), len(rows))}")
    print(f"  restatement   {restated}/{2*len(rows)} plus slots")
    print(f"  T+/A+ relation {dict(relation)}")
    print(f"  t_plus parentage {dict(collections.Counter(r.get('t_plus_parent') for r in rows))}")
    print(f"  a_plus parentage {dict(collections.Counter(r.get('a_plus_parent') for r in rows))}")
