"""Re-generate the synthesis on the 17 existing 1-PP wheels with the fixed prompt.

`probe_synthesis_arms_theory2.py` found the machinery's S- read as the two traps
restated in 10/17 (third-trap auditor) against 11/17 third failures for a one
call that was handed the Transformation AS a tetrad and told S- is one named
state. That instruction was the confound: `SynthesisGeneration` never had it.
This gives it the same statement of the node model and the same S- shape rule
(`synthesis_generation.SYSTEM_PROMPT`, "The shape of the inputs, exactly") and
re-runs ONLY the synthesis on the wheels the machinery run built (still in the
DB, cleanup off), reading the new S-/S+ with the same auditor and the same blind
pairwise judge against the old S- and against arm 2's.

    poetry run pytest tests/e2e/probe_synthesis_rerun.py --real-llm -q -s
"""

from __future__ import annotations

import glob
import json
import os
import random
import time
from pathlib import Path

import pytest

from dialectical_framework.concerns.synthesis_generation import \
    SynthesisGeneration
from dialectical_framework.graph.nodes.transformation import Transformation
from dialectical_framework.graph.rendering import \
    find_nexus_for_transformation
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.wheel_repository import \
    WheelRepository
from dialectical_framework.graph.scope_context import scope
from e2e.config import E2EConfig
from e2e.probe_synthesis_arms_theory1 import _judge_sminus
from e2e.probe_synthesis_arms_theory2 import _third_trap

_RESULTS = Path(__file__).resolve().parent / "results" / "tetrad_quality"
_MACHINERY = _RESULTS / "wisdom_machinery-20261005-082435.json"


def _latest(prefix: str) -> Path:
    return Path(sorted(glob.glob(str(_RESULTS / f"{prefix}-*.json")), key=os.path.getmtime)[-1])


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_synthesis_with_the_shape_rule(di_container) -> None:
    judge = E2EConfig.from_env().judge_model
    rows = [r for r in json.loads(_MACHINERY.read_text()) if not r.get("error")]
    arm2 = {it["utterance"]: it["prompt2"] for it in json.loads(_latest("wisdom_theory_prompt2").read_text())}
    out = _RESULTS / f"synthesis_rerun-{time.strftime('%Y%m%d-%H%M%S')}.json"
    rng = random.Random(20261005)
    results: list[dict] = []
    for i, r in enumerate(rows, 1):
        item = {"utterance": r["utterance"], "sid": r["sid"], "old_s_plus": r["s_plus"], "old_s_minus": r["s_minus"],
                "arm2_s_minus": arm2.get(r["utterance"], {}).get("s_minus")}
        started = time.perf_counter()
        try:
            with scope(r["sid"]):
                tr = NodeRepository().find_by_hash(r["pathways"][0]["hash"], Transformation)
                nexus = find_nexus_for_transformation(tr)
                wheels = [w for _c, w in WheelRepository().find_by_nexus(nexus)]
                wheel = wheels[0]
                result = await SynthesisGeneration().resolve(wheel=wheel, input_text=r["utterance"])
                item.update(new_s_plus=result.s_plus_statement.text, new_s_minus=result.s_minus_statement.text,
                            new_s_minus_why=result.s_minus_explanation, seconds=round(time.perf_counter() - started, 1))
        except Exception as exc:  # noqa: BLE001
            item["error"] = repr(exc)
            results.append(item); out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
            print(f"{i}. ERROR {exc!r}", flush=True)
            continue
        item["third_trap_new"] = await _third_trap(di_container, judge, r["t_minus"], r["a_minus"], item["new_s_minus"])
        flip = rng.random() < 0.5
        a, b = (item["new_s_minus"], item["old_s_minus"]) if flip else (item["old_s_minus"], item["new_s_minus"])
        v = await _judge_sminus(di_container, judge, a, b)
        item["vs_old"] = {"A": "new" if flip else "old", "B": "old" if flip else "new", "same": "same", None: None}[v.get("sharper")]
        if item["arm2_s_minus"]:
            flip = rng.random() < 0.5
            a, b = (item["new_s_minus"], item["arm2_s_minus"]) if flip else (item["arm2_s_minus"], item["new_s_minus"])
            v = await _judge_sminus(di_container, judge, a, b)
            item["vs_arm2"] = {"A": "new" if flip else "arm2", "B": "arm2" if flip else "new", "same": "same", None: None}[v.get("sharper")]
        results.append(item)
        out.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"\n{i}. **{r['utterance']}**  ({item['seconds']}s)\n   old S-: {item['old_s_minus']}\n   new S-: {item['new_s_minus']}   [{item['third_trap_new'].get('kind')}]  vs old: {item['vs_old']}  vs arm2: {item.get('vs_arm2')}\n   arm2  : {item['arm2_s_minus']}\n   new S+: {item['new_s_plus']}", flush=True)
    ok = [x for x in results if not x.get("error")]
    kinds = [x["third_trap_new"].get("kind") for x in ok]
    print(f"\n--- synthesis re-run with the shape rule (n={len(ok)}/{len(rows)})")
    print(f"    third-trap auditor, new machinery S-: third_failure {kinds.count('third_failure')}, traps_restated {kinds.count('traps_restated')}, one_trap {kinds.count('one_trap')}   (old machinery: 4/10/3; arm2: 11/2/4)")
    vo = [x["vs_old"] for x in ok]; va = [x.get("vs_arm2") for x in ok]
    print(f"    blind pairwise new vs old: new {vo.count('new')}, old {vo.count('old')}, same {vo.count('same')}")
    print(f"    blind pairwise new vs arm2: new {va.count('new')}, arm2 {va.count('arm2')}, same {va.count('same')}")
    print(f"    median {sorted(x['seconds'] for x in ok)[len(ok)//2]}s a synthesis  → {out}")
