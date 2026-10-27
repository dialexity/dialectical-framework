"""Apply the attribution check to the saved WITH-arm draws of the holder-rule
gate (`probe_pasted_material.py`, 2026-10-27) and read it against the probe's
own text-grounded judge and the hand read.

Nothing is drawn. For every saved draw with a named holder on T or A, the
check is asked exactly as the view turn asks it (`AttributionCheck.score_texts`,
the case text as the words). Reads:

- `dropped`: holders the check would blank.
- against the probe's `*_falsely_attributed` flag (its judge + the same-party
  read): dropped & flagged = agreed misquotation; kept & flagged = missed by
  the check (or the probe's same-party strictness — listed for hand reading);
  dropped & grounded = OVER-blanking, the cost (a true holder lost).

    ATTRIBUTION_RESCORE=tests/e2e/results/pasted/holder-rule-20261027-132330.json \\
      poetry run pytest tests/e2e/rescore_attribution_check.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import time

import pytest

from e2e.pasted_material_cases import PASTED_MATERIAL_CASES

pytestmark = [pytest.mark.llm]

DEFAULT = "tests/e2e/results/pasted/holder-rule-20261027-132330.json"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_apply_the_attribution_check_to_the_saved_draws(di_container) -> None:
    from dialectical_framework.concerns.attribution_check import AttributionCheck

    path = pathlib.Path(os.environ.get("ATTRIBUTION_RESCORE", DEFAULT))
    saved = json.loads(path.read_text())
    arm = os.environ.get("ATTRIBUTION_ARM", "with")
    rows = saved["rows"][arm]
    by_id = {c.case_id: c for c in PASTED_MATERIAL_CASES}
    gate = asyncio.Semaphore(6)

    async def judge(row: dict, pole: str) -> dict:
        async with gate:
            try:
                dto = await AttributionCheck().score_texts(
                    position=row[pole], held_by=row[f"{'t' if pole == 'thesis' else 'a'}_held_by"],
                    text=by_id[row["case_id"]].text,
                )
                return {"verdict": dto.verdict, "reasoning": dto.reasoning[:200]}
            except Exception as exc:  # noqa: BLE001
                return {"verdict": None, "error": repr(exc)}

    jobs = [(r, pole) for r in rows if r.get("thesis")
            for pole in ("thesis", "antithesis") if r.get(f"{'t' if pole == 'thesis' else 'a'}_held_by") and r.get(pole)]
    verdicts = await asyncio.gather(*(judge(r, p) for r, p in jobs))
    report = {"file": str(path), "arm": arm, "named": len(jobs)}
    tally: dict[str, int] = {}
    listing: list[str] = []
    for (r, pole), v in zip(jobs, verdicts):
        k = "t" if pole == "thesis" else "a"
        r[f"{k}_check"] = v
        dropped = v["verdict"] == "not_attributed"
        flagged = r.get(f"{k}_falsely_attributed") is True
        key = f"{k}_" + ("dropped" if dropped else "kept") + "_" + ("flagged" if flagged else "grounded")
        tally[key] = tally.get(key, 0) + 1
        if dropped != flagged:
            listing.append(f"[{r['case_id']}#{r['draw']}] {pole} <{r[f'{k}_held_by']}> probe-in-text <{r.get(f'{k}_holder_in_text')}> "
                           f"check={v['verdict']} | {r[pole]} | {v.get('reasoning', v.get('error'))}")
    report["tally"] = dict(sorted(tally.items()))
    report["dropped_total"] = sum(n for k, n in tally.items() if "dropped" in k)
    out = path.with_name(path.stem + f"-attribution-check-{arm}-{time.strftime('%Y%m%d-%H%M%S')}.json")
    out.write_text(json.dumps({"report": report, "rows": rows}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    print("\n=== where the check and the probe's judge disagree ===")
    for line in listing:
        print(line)
    print(f"\nwrote {out}")
