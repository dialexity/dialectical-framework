"""
Re-read a saved `probe_multiclaim_thesis.py` run with the CHOICE instrument.

The first run (2026-10-26, the first set) was scored by the boolean judge only.
Its draws are in the results file; re-drawing them costs ~$12 and changes the
draws, while re-judging costs ~$1 and changes nothing but the read. So the
second instrument is applied to the first run's saved draws here, and the two
sets become comparable on one read.

    MULTICLAIM_RESCORE=tests/e2e/results/multiclaim/rules-<stamp>.json \\
        poetry run pytest tests/e2e/rescore_multiclaim.py --real-llm -q -s

Writes `<stamp>-rescored.json` beside the input; never overwrites it.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib

import pytest

from e2e.multiclaim_cases import MULTI_CLAIM_CASES, MULTI_CLAIM_CASES_LATE
from e2e.probe_multiclaim_thesis import (_count, _label_demand, _sign_test,
                                         _which_claim)

pytestmark = [pytest.mark.real_llm, pytest.mark.llm]


@pytest.mark.asyncio
async def test_rescore_a_saved_run(di_container) -> None:
    path = pathlib.Path(os.environ["MULTICLAIM_RESCORE"])
    saved = json.loads(path.read_text(encoding="utf-8"))
    arms = saved["arms"]
    ids = {r["petition_id"] for rows in arms.values() for r in rows}
    cases = {
        c.petition_id: c
        for c in MULTI_CLAIM_CASES + MULTI_CLAIM_CASES_LATE
        if c.petition_id in ids
    }
    assert len(cases) == len(ids), "a saved row has no case in the module"

    labels = dict(
        zip(cases, await asyncio.gather(*(_label_demand(c) for c in cases.values())))
    )
    for rows in arms.values():
        complete = [r for r in rows if r.get("thesis")]
        picks = await asyncio.gather(
            *(_which_claim(r["thesis"], cases[r["petition_id"]].claims) for r in complete)
        )
        for row, pick in zip(complete, picks):
            row["thesis_claim_index"] = pick
            row["demand_claim_index"] = labels.get(row["petition_id"])
            row["thesis_picks_the_demand"] = (
                None if not pick or not row["demand_claim_index"]
                else pick == row["demand_claim_index"]
            )
    w, wo = arms["with_rules"], arms["without_rules"]
    report = {
        "rescored_from": path.name,
        "demand_located_in_claims": sum(1 for v in labels.values() if v),
        "thesis_picks_the_demand": {k: _count(v, "thesis_picks_the_demand") for k, v in arms.items()},
        "thesis_is_the_demand": {k: _count(v, "thesis_is_the_demand") for k, v in arms.items()},
        "sign_test_picks": _sign_test(w, wo, "thesis_picks_the_demand"),
    }
    out = path.with_name(path.stem + "-rescored.json")
    out.write_text(json.dumps({"report": report, "arms": arms}, indent=1, ensure_ascii=False))
    print("\n" + json.dumps(report, indent=1))
    print(f"wrote {out}")
