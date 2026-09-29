"""
Probe: the two ways a blindspot app can get its tetrad, side by side.

For each utterance a person might type into a blindspot app:
  A. `Consultant.exploration_view(focus=…)` — one structured turn, no graph.
  B. the headless pipeline `anchor` runs (`AnchorTheses` → `AnalysisPipeline`
     → `ExpandPolarity`) in a scratch Case, then `perspective_view(pp)`.

Prints T / A / A+ / T- / A- for both with latency, and writes every item to
JSON so the verdict can be re-read. The decision this feeds: which path the
first app's backend runs. Real provider and Memgraph; run explicitly:

    poetry run pytest tests/probe_blindspot_paths.py --real-llm -q -s
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from dialectical_framework.agents.advisor.tools.anchor import _anchor
from dialectical_framework.agents.apps import COUNSELOR_PERSONA
from dialectical_framework.agents.consultant.consultant import Consultant
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.graph.views import PerspectiveView, perspective_view

UTTERANCES = [
    "I should quit my job and start my own company.",
    "My co-founder never listens to me.",
    "Should I move to Berlin for this job offer?",
    "Remote work is killing our culture.",
    "I need to be more disciplined.",
    "We're going to cut the marketing budget in half.",
    "My teenage son spends all his time gaming and I have to stop it.",
    "I always say yes to my clients and it's exhausting.",
    "The team needs a proper process; everything is chaos.",
    "I don't trust my new manager.",
    "We should hire senior people only, juniors slow us down.",
    "I want to move my parents into a care home.",
    "I keep postponing the difficult conversation with my partner.",
    "Our product needs more features to compete.",
    "I think I should stop lending money to my brother.",
    "Why does every meeting end without a decision?",
    "I'm going to homeschool my kids.",
    "My best engineer wants to become a manager and I think it's a mistake.",
    "I should stop checking work email on weekends.",
    "We need to raise prices, we're too cheap.",
]

FOCUS = (
    "the perspective for what I just said: my position, what it stands against, "
    "and above all the constructive side of that opposing view that I am not seeing"
)

OUT = Path(
    os.environ.get(
        "BLINDSPOT_PROBE_OUT",
        "/private/tmp/claude-501/-Users-evaldas-src-dialexity-dialectical-framework/"
        "3949bc20-4e96-417d-ac2a-bb1eac6b09b9/scratchpad/blindspot_probe.json",
    )
)


def _flat(view: PerspectiveView | None) -> dict:
    if view is None:
        return {}
    return {
        name: (pole.text if pole else None)
        for name, pole in (
            ("t", view.t), ("a", view.a), ("t_plus", view.t_plus),
            ("t_minus", view.t_minus), ("a_plus", view.a_plus), ("a_minus", view.a_minus),
        )
    } | {
        "intent": view.intent,
        "complete": view.complete,
        "a_hs": view.a.hs if view.a else None,
        "validation": view.validation,
    }


async def _path_a(text: str) -> dict:
    head = Consultant(app_preamble=COUNSELOR_PERSONA, messages=[{"role": "user", "content": text}])
    t0 = time.perf_counter()
    try:
        view = await head.exploration_view(focus=FOCUS)
        first = view.perspectives[0] if view.perspectives else None
        return {"seconds": round(time.perf_counter() - t0, 1), "n": len(view.perspectives), **_flat(first)}
    except Exception as e:  # a probe records failure, never hides it
        return {"seconds": round(time.perf_counter() - t0, 1), "error": repr(e)}


async def _path_b(text: str) -> dict:
    case = Case()
    case.commit()
    t0 = time.perf_counter()
    with scope(case.sid):
        try:
            report = json.loads(await _anchor(thesis=text, antithesis=None, context=""))
            hashes = (report.get("artifacts") or {}).get("perspective_hashes") or []
            if not hashes:
                return {"seconds": round(time.perf_counter() - t0, 1), "n": 0,
                        "summary": report.get("summary")}
            pp = NodeRepository().find_by_hash(hashes[0], node_type=Perspective)
            view = perspective_view(pp) if pp else None
            return {"seconds": round(time.perf_counter() - t0, 1), "n": len(hashes), **_flat(view)}
        except Exception as e:
            return {"seconds": round(time.perf_counter() - t0, 1), "error": repr(e)}


def _show(label: str, r: dict) -> None:
    if "error" in r:
        print(f"  {label}: ERROR {r['error']} ({r['seconds']}s)")
        return
    if not r.get("t"):
        print(f"  {label}: nothing drawn ({r['seconds']}s) {r.get('summary') or ''}")
        return
    hs = f" HS(A)={r['a_hs']}" if r.get("a_hs") is not None else ""
    val = f" [{r['validation']}]" if r.get("validation") else ""
    print(f"  {label} ({r['seconds']}s{hs}{val})")
    print(f"     T : {r['t']}\n     A : {r['a']}")
    print(f"     A+: {r['a_plus']}   <-- the blindspot")
    print(f"     T-: {r['t_minus']}\n     A-: {r['a_minus']}\n     T+: {r['t_plus']}")
    if r.get("intent"):
        print(f"     {r['intent']}")


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_blindspot_paths():
    # Path A has no graph: all at once. Path B writes the graph: one at a time.
    # BLINDSPOT_PATHS=a or =b reruns one side; a skipped side reads as an error
    # row so the JSON keeps its shape.
    paths = os.environ.get("BLINDSPOT_PATHS", "ab").lower()
    skipped = {"seconds": 0.0, "error": "skipped"}
    a_results = (
        await asyncio.gather(*(_path_a(u) for u in UTTERANCES))
        if "a" in paths else [skipped] * len(UTTERANCES)
    )
    b_results = []
    for u in UTTERANCES:
        b_results.append(await _path_b(u) if "b" in paths else skipped)

    items = []
    for u, a, b in zip(UTTERANCES, a_results, b_results):
        print(f"\n### {u}")
        _show("A consultant", a)
        _show("B pipeline  ", b)
        items.append({"utterance": u, "a": a, "b": b})
    OUT.write_text(json.dumps(items, indent=1, ensure_ascii=False))

    def _stats(rs):
        ok = [r for r in rs if r.get("t")]
        secs = [r["seconds"] for r in rs]
        return (f"drawn {len(ok)}/{len(rs)}, errors {sum('error' in r for r in rs)}, "
                f"median {sorted(secs)[len(secs)//2]}s, max {max(secs)}s")
    print(f"\nA consultant: {_stats(a_results)}")
    print(f"B pipeline  : {_stats(b_results)}")
    print(f"written: {OUT}")
