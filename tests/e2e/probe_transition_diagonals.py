"""Rule 5.2's diagonals: does Ac+ contradict Re-, and Ac- contradict Re+?

[P0 p.17]: Ac+/Ac-/Re+/Re- form a tetrad "obedient to rules 3.1-3.3", so
"Ac+ must directly contradict Re-, while Ac- must directly contradict Re+".
The generation prompts ask for it (`transformation_generation`: "Re+ must
CONTRADICT Ac-", "Your Ac+ must CONTRADICT Re-"; the one-shot's
`TRANSFORMATION_POSITIONS`), and nothing checks it — the theory map's
"partial" for Rule 5.2. The aspect tetrad is in the same position by design
(`AspectGeneration`: diagonals enforced by the prompt, `DiagonalOppositionsCheck`
only where a person bypasses it), and a transformation has no edit path, so a
checker in src/ would have no caller. This MEASURES whether the prompt holds,
on outputs already stored — nothing generated.

The question is the aspect tetrad's own, word for word
(`DiagonalOppositionsCheck._evaluate_contradiction`, 0.7 = a valid
contradiction), asked of three pairs per Transformation:
- Ac+ vs Re-   (diagonal — should contradict)
- Ac- vs Re+   (diagonal — should contradict)
- Ac+ vs Re+   (CONTROL — the two that run together into S+; they should NOT
                contradict, and a judge that says they do is saying "yes" to
                anything)

Sources (env, defaults are the 2026-10-06/07 files):
- staged, one tension:  `PROBE_STAGED_FILE`  (staged_endpoints-*, items' `out`)
- one-shot, one tension: `PROBE_SKETCH_FILE` (transformation_sketch-*, arms)
- N = 2, both arms:      `PROBE_N2_FILE`     (n2_one_shot_edge-*, rows' `lines`)

    poetry run pytest tests/e2e/probe_transition_diagonals.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

import pytest

from dialectical_framework.concerns.diagonal_oppositions_check import \
    DiagonalOppositionsCheck
from e2e.config import E2EConfig
from e2e.modelctx import using_model

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_CONCURRENCY = 6
_VALID = 0.7  # the aspect tetrad's own line (DiagonalOppositionsCheckResult)

_PAIRS = (
    ("ac_plus_vs_re_minus", "ac_plus", "Ac+ (the constructive action)", "re_minus", "Re- (the degraded reflection)"),
    ("ac_minus_vs_re_plus", "ac_minus", "Ac- (the degraded action)", "re_plus", "Re+ (the constructive reflection)"),
    ("control_ac_plus_vs_re_plus", "ac_plus", "Ac+ (the constructive action)", "re_plus", "Re+ (the constructive reflection)"),
)


def _sources() -> list[tuple[str, dict[str, str]]]:
    """(group label, the six lines) for every Transformation in the named files."""
    out: list[tuple[str, dict[str, str]]] = []
    staged = os.getenv("PROBE_STAGED_FILE", "staged_endpoints-20261006-185109.json")
    for item in json.loads((_RESULTS / staged).read_text()):
        if isinstance(item.get("out"), dict):
            out.append(("staged, one tension", item["out"]))
    sketch = os.getenv("PROBE_SKETCH_FILE", "transformation_sketch-20261006-130616.json")
    for row in json.loads((_RESULTS / sketch).read_text()):
        o = row.get("out")
        # file 130616: `current` = text only (dd2be18), `ends_fields` = what ships
        if isinstance(o, dict) and "error" not in o and row["arm"] in ("current", "ends_fields"):
            label = "one-shot (shipped)" if row["arm"] == "ends_fields" else "one-shot (text only)"
            out.append((f"{label}, one tension", o))
    n2 = os.getenv("PROBE_N2_FILE", "n2_one_shot_edge-gen4-crossnote-20261007-073017.json")
    for row in json.loads((_RESULTS / n2).read_text()).get("rows", []):
        if row.get("lines") and not row.get("shared_statement"):
            out.append((f"{'staged' if row['arm'] == 'staged' else 'one-shot per edge'}, two tensions", row["lines"]))
    return out


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_transition_diagonals(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    items = [(g, lines) for g, lines in _sources() if all(lines.get(k) for k in ("ac_plus", "ac_minus", "re_plus", "re_minus"))]
    out = _RESULTS / f"transition_diagonals-{time.strftime('%Y%m%d-%H%M%S')}.json"
    gate = asyncio.Semaphore(_CONCURRENCY)
    checker = DiagonalOppositionsCheck()

    async def score(a: str, ra: str, b: str, rb: str) -> Optional[float]:
        async with gate:
            try:
                v = await checker._evaluate_contradiction(a, ra, b, rb, "")
                return v.contradiction_score
            except Exception:  # noqa: BLE001 - unjudged
                return None

    async def one(group: str, lines: dict[str, str]) -> dict[str, Any]:
        scores = await asyncio.gather(*(score(lines[a], ra, lines[b], rb) for _n, a, ra, b, rb in _PAIRS))
        return {"group": group, "lines": {k: lines[k] for k in ("ac_plus", "ac_minus", "re_plus", "re_minus")},
                **{name: s for (name, *_), s in zip(_PAIRS, scores)}}

    with using_model(di_container, judge):
        rows = list(await asyncio.gather(*(one(g, lines) for g, lines in items)))
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    print(f"\n--- {out.name} (judge {judge}; a pair 'holds' at >= {_VALID}) ---")
    for group in dict.fromkeys(r["group"] for r in rows):
        sel = [r for r in rows if r["group"] == group]

        def held(name: str) -> str:
            got = [r[name] for r in sel if r[name] is not None]
            return f"{100 * sum(1 for s in got if s >= _VALID) / max(1, len(got)):3.0f}% (mean {sum(got) / max(1, len(got)):.2f})"

        both = [r for r in sel if r["ac_plus_vs_re_minus"] is not None and r["ac_minus_vs_re_plus"] is not None]
        both_ok = sum(1 for r in both if r["ac_plus_vs_re_minus"] >= _VALID and r["ac_minus_vs_re_plus"] >= _VALID)
        print(f"  {group:34} n={len(sel):3}  Ac+/Re- {held('ac_plus_vs_re_minus')}  Ac-/Re+ {held('ac_minus_vs_re_plus')}  "
              f"both {100 * both_ok / max(1, len(both)):3.0f}%  | control Ac+/Re+ {held('control_ac_plus_vs_re_plus')}")
