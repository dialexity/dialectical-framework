"""Do the STAGED generator's Ac-/Re- land where the theory says they go?

`probe_transformation_sketch.py` found (2026-10-06) that the one-shot writer,
given the definition in text, put Ac-/Re- on their ends (Ac- = T+ -> A-,
Re- = A+ -> T-) in only 22% / 18% of drafts — the line falls on T's OWN trap —
and that naming the ends first fixed it (60% / 58%). The graph path writes
Ac-/Re- in separate calls (`TransformationGeneration._generate_ac_minus`,
`_generate_re_side`), and the Advisor's and the Navigator's pathways, and the
decisions grounded on them, are THOSE. It was never instrumented: the stored
pathways of the machinery runs carry no edge orientation, and on a wheel's
reverse edge Ac- runs A+ -> T-, so a judge reading them against fixed corners
would score half of them against the wrong ends.

So this reads the wheels BACK from the graph. Per machinery row (built with
`DIALEXITY_TEST_CLEANUP=false` so the wheels survive): every Transformation of
the row's nexus (2 edges x 3 insight bands on a one-tension wheel), each of its
six positions' text (`Transition.summary`, the fuller line — up to
`transition_length` words, the length the one-shot's lines are written to;
`instruction` is the ~7-word headline), and the ORIENTATION read off the Ac-
transition's source statement: T+ means the edge runs T -> A and the corners are
used as given; A+ means A -> T and T/A are swapped, so the same verbatim judge
(`probe_transformation_sketch.EndpointsVerdict`) asks the same question on both
edges. The wiring itself is checked too (Ac- source/target are the oriented
T+/A-): that is structure, and should always hold.

Not paired with the one-shot arms (different generations of the same 25-ish
tetrads, a different writer shape), so read the rates side by side, not as a
delta.

Result (2026-10-06, Fable 5 judging, 17 wheels x 6 Transformations):
`staged_endpoints-20261006-151300.json`, read by the app's STRICT auditor at the
time — Ac- ends 74%, Re- ends 34%; wiring 102/102. That auditor required each
line to visibly start from the other side's strength, which three blind theory
reviewers found stricter than the papers (half its Re- failures were valid).
Re-read with the theory-faithful `TransitionVerdict`
(`transition_rescore-20261006-175449.json`): **Ac- valid 70% (lands 91%), Re-
valid 49% (lands 59%)**; T->A edges 53% / 27%, A->T edges 86% / 71%. The real Re-
defect is the LANDING: "reflection without action" read as "keep watching, do
nothing", which ends in A- wherever A is the passive pole. (An earlier reading
here, "lands right, starts wrong", was the strict auditor talking; corrected.)
Two `re_minus_from/_into` fields before the Re- lines (the one-shot's fix) gave
`staged_endpoints-20261006-154414.json`: +6 on the strict read (-6..+18), within
noise, the unchanged Ac- -2 — reverted; not re-read with the new auditor.
This probe now judges with `TransitionVerdict`. To compare two builds cell by
cell, pair the two result files on (utterance, orientation, category).

    PROBE_MACHINERY_FILE=wisdom_machinery-<stamp>.json \\
        poetry run pytest tests/e2e/probe_staged_endpoints.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

import pytest

from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.rendering import \
    find_nexus_for_transformation
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.transformation_repository import \
    TransformationRepository
from dialectical_framework.graph.scope_context import scope
from e2e.config import E2EConfig
from e2e.modelctx import using_model
from e2e.probe_transformation_sketch import _transitions

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_CONCURRENCY = 6
_POSITIONS = (("action", "ac"), ("reflection", "re"), ("ac_plus", "ac_plus"),
              ("ac_minus", "ac_minus"), ("re_plus", "re_plus"), ("re_minus", "re_minus"))


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", (text or "").lower()))


def _closest(text: str, candidates: dict[str, str]) -> str:
    """The corner whose words overlap `text` most — exact text first. Statement
    texts are the given corners (SketchTetrad(sketch=) persists them as drawn),
    so this is a guard against whitespace, not a fuzzy match doing real work;
    `orientation_exact` records which it was."""
    for name, corner in candidates.items():
        if text.strip() == corner.strip():
            return name
    return max(candidates, key=lambda n: len(_words(text) & _words(candidates[n])))


def _line(manager) -> Optional[str]:
    got = manager.get()
    if not got:
        return None
    return (got[0].summary or got[0].instruction or "").strip() or None


def _endpoints_of(manager) -> tuple[Optional[str], Optional[str]]:
    got = manager.get()
    if not got:
        return None, None
    tr = got[0]
    src, tgt = tr.source.get(), tr.target.get()
    return (src[0].text if src else None), (tgt[0].text if tgt else None)


def _read(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Every Transformation of the row's nexus, oriented."""
    corners = {"t": row["thesis"], "a": row["antithesis"], "t_plus": row["t_plus"],
               "t_minus": row["t_minus"], "a_plus": row["a_plus"], "a_minus": row["a_minus"]}
    swapped = {"t": corners["a"], "a": corners["t"], "t_plus": corners["a_plus"],
               "t_minus": corners["a_minus"], "a_plus": corners["t_plus"], "a_minus": corners["t_minus"]}
    out: list[dict[str, Any]] = []
    with scope(row["sid"]):
        first = NodeRepository().find_by_hash(row["pathways"][0]["hash"], Transformation)
        nexus = find_nexus_for_transformation(first) if first else None
        if nexus is None:
            return out
        for tr in TransformationRepository().find_by_nexus(nexus):
            text = {name: _line(getattr(tr, rel)) for name, rel in _POSITIONS}
            src, tgt = _endpoints_of(tr.ac_minus)
            if not src or not all(text.values()):
                out.append({"hash": tr.short_hash, "error": "incomplete transformation"})
                continue
            side = _closest(src, {"t_plus": corners["t_plus"], "a_plus": corners["a_plus"]})
            oriented = corners if side == "t_plus" else swapped
            out.append({
                "hash": tr.short_hash,
                "category": tr.insight_category,
                "orientation": "T->A" if side == "t_plus" else "A->T",
                "orientation_exact": src.strip() in (corners["t_plus"].strip(), corners["a_plus"].strip()),
                "wiring_ok": (tgt or "").strip() == oriented["a_minus"].strip(),
                "corners": oriented,
                "out": text,
            })
    return out


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_staged_endpoints(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    source = _RESULTS / os.environ["PROBE_MACHINERY_FILE"]
    rows = [r for r in json.loads(source.read_text()) if not r.get("error")]
    out = _RESULTS / f"staged_endpoints-{time.strftime('%Y%m%d-%H%M%S')}.json"

    items: list[dict[str, Any]] = []
    for r in rows:  # graph reads, sequential
        for t in _read(r):
            items.append({"utterance": r["utterance"], **t})
    judgeable = [i for i in items if "error" not in i]
    print(f"\n{len(rows)} wheels, {len(items)} transformations read, {len(judgeable)} judgeable; judge {judge}")
    assert judgeable, "no wheels in the DB: rebuild with DIALEXITY_TEST_CLEANUP=false"

    gate = asyncio.Semaphore(_CONCURRENCY)

    async def one(item: dict[str, Any]) -> None:
        async with gate:
            tv = await _transitions(item["corners"], item["out"])
        if tv is not None:
            item["transition_verdict"] = tv.model_dump()
            item.update(ac_valid=float(tv.ac_valid), re_valid=float(tv.re_valid),
                        ac_lands=float(tv.ac_minus_ends_in_a_minus), re_lands=float(tv.re_minus_ends_in_t_minus),
                        ac_own=float(tv.ac_minus_is_degenerated_action), re_own=float(tv.re_minus_is_degenerated_reflection))

    with using_model(di_container, judge):
        await asyncio.gather(*(one(i) for i in judgeable))
    out.write_text(json.dumps(items, indent=2, ensure_ascii=False))

    def rate(key: str, subset: list[dict[str, Any]]) -> str:
        got = [i[key] for i in subset if key in i]
        return f"{100 * sum(got) / max(1, len(got)):.0f}% ({int(sum(got))}/{len(got)})"

    print(f"--- {out.name} ---")
    print(f"  wiring ok (Ac- target is the oriented A-): {sum(1 for i in judgeable if i['wiring_ok'])}/{len(judgeable)}; "
          f"orientation by exact text {sum(1 for i in judgeable if i['orientation_exact'])}/{len(judgeable)}")
    for label, subset in (("all", judgeable),
                          ("T->A edges", [i for i in judgeable if i["orientation"] == "T->A"]),
                          ("A->T edges", [i for i in judgeable if i["orientation"] == "A->T"])):
        print(f"  {label:11} Ac- valid {rate('ac_valid', subset)} (lands {rate('ac_lands', subset)}) | "
              f"Re- valid {rate('re_valid', subset)} (lands {rate('re_lands', subset)}) | "
              f"Ac- own {rate('ac_own', subset)} | Re- own {rate('re_own', subset)}")
    for cat in sorted({i.get("category") or "?" for i in judgeable}):
        subset = [i for i in judgeable if (i.get("category") or "?") == cat]
        print(f"  {cat:11} Ac- valid {rate('ac_valid', subset)} | Re- valid {rate('re_valid', subset)}")
    print("  one-shot, same auditor (transition_rescore-20261006-175449): text alone 30% / 26%, with the from/into fields 56% / 62%")
