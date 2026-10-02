"""Where the one-shot `anchor`'s ~43 s go, call by call.

Runs the wired thesis-only `anchor` on a few utterances under `call_census`
and prints each provider call as a timeline bar (who, which DTO, when it
started, how long), then the three census numbers: provider seconds bought,
busy seconds (union of intervals), parallelism. The gaps between bars are
graph writes and orchestration. This is the measurement step 2 (latency)
starts from — the chain's shape decides whether the fix is "gather what is
independent" or "ask for less".

    poetry run pytest tests/e2e/probe_oneshot_census.py --real-llm -q -s
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from dialectical_framework.agents.advisor.tools.anchor import _anchor
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census

UTTERANCES = (
    "I should quit my job and start my own company.",
    "My co-founder never listens to me.",
    "We're going to cut the marketing budget in half.",
    "I don't trust my new manager.",
)
_OUT = Path(__file__).resolve().parent / "results" / "tetrad_quality"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_oneshot_census(di_container) -> None:
    runs = []
    for text in UTTERANCES:
        case = Case()
        case.commit()
        with scope(case.sid), call_census() as census:
            t0 = time.monotonic()
            await _anchor(thesis=text, antithesis=None, context="", utterance=text)
            wall = time.monotonic() - t0
        calls = sorted(census.calls, key=lambda c: c.started)
        start = calls[0].started if calls else t0
        print(f"\n=== «{text}»  wall {wall:.1f}s  provider {census.provider_s:.1f}s  "
              f"busy {census.busy_s:.1f}s  parallelism {census.parallelism:.2f}  "
              f"calls {census.count}  non-LLM {wall - census.busy_s:.1f}s")
        for c in calls:
            off = c.started - start
            bar = " " * int(off) + "#" * max(1, int(round(c.seconds)))
            print(f"  {off:5.1f}s +{c.seconds:4.1f}s  {c.label:48s} |{bar}")
        runs.append({
            "utterance": text, "wall": round(wall, 1), "provider_s": round(census.provider_s, 1),
            "busy_s": round(census.busy_s, 1), "parallelism": round(census.parallelism, 2),
            "calls": [{"label": c.label, "offset": round(c.started - start, 2), "seconds": round(c.seconds, 2)} for c in calls],
        })
    out = _OUT / f"oneshot_census-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(runs, indent=2, ensure_ascii=False))
    print(f"\n→ {out}")
