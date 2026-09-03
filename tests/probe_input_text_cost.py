"""Measure what one `_get_input_text()` costs, and what P of them cost gathered.

Item 8 on the ingestion list assumed `ExpandPolarity._get_input_text()` was
worth hoisting out of `AnalysisPipeline`'s gather. Before changing a skill's
constructor for it, size the thing: `get_all()` plus a per-input digest
fallback, all of it SYNC GQLAlchemy work that blocks the event loop.

Measured 2026-09-03, local Memgraph, 9 reps:

    inputs  digest  rendered      one call    3x gathered
    1       yes     104 chars     7.6 ms      21.9 ms
    5       yes     528 chars     4.4 ms       9.4 ms
    5       no      12 KB         2.8 ms       7.5 ms
    3       no      1.22 MB      61.0 ms      81.6 ms

Two readings, and only the second one matters.

The hoist is DEAD as a latency lever. Three gathered calls cost about three
serial ones — no overlap, exactly as expected, since `execute_and_fetch` is
sync and blocks the loop — so hoisting saves the P-1 copies: ~5-15 ms on a
digested scope, against a chain measured in tens of seconds. Not worth
changing `ExpandPolarity`'s constructor and ~40 call sites' contract for.

What the last row says is the real finding, and it is about SIZE, not time.
`input_context()` is unbounded and falls back to full content per Input, so
three undigested ~400 KB files render 1.22 MB (~300k tokens) of `input_text`
— and five of its seven consumers do not truncate at all
(`aspect_generation`, `perspective_validation`, `control_statements_check`,
`antithesis_classification`, `tetrad_grounding`; only `statement_headline`
and `statement_classification` cut, at 1500/2000). That is a context-limit
failure or a ruinous bill, per polarity, not a slowdown. It is reachable
exactly when a digest is missing — including when `SourceDigest` failed, a
path that only got MORE survivable, so bounding this is item 13's job and it
is load-bearing.

Run: poetry run pytest tests/probe_input_text_cost.py -q -s -p no:randomly
(not collected by the default suite — `probe_*.py`, no assertions)
"""

from __future__ import annotations

import asyncio
import statistics
import time

import pytest

from dialectical_framework.agents.analyst.skills.expand_polarities import (
    ExpandPolarity,
)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.scope_context import scope


def _seed(n_inputs: int, digested: bool, body_reps: int = 200) -> str:
    case = Case()
    case.commit()
    with scope(case.sid):
        for i in range(n_inputs):
            inp = Input(content=f"Input {i}: " + ("lorem ipsum " * body_reps))
            if digested:
                inp.digest = f"Digest of input {i}"
            inp.commit()
            case.inputs.connect(inp)
    return case.sid


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "n_inputs,digested,body_reps",
    [
        (1, True, 200),
        (5, True, 200),
        (5, False, 200),
        # The case the question was actually about: pasted files, no digest yet.
        # 3 x ~200 KB is what `ingest` leaves behind before SourceDigest lands.
        (3, False, 34_000),
    ],
)
async def test_measure(n_inputs, digested, body_reps, reps=9):
    sid = _seed(n_inputs, digested, body_reps)
    with scope(sid):
        concern = ExpandPolarity(polarity_hash="unused")

        singles = []
        for _ in range(reps):
            t = time.perf_counter()
            text = await concern._get_input_text()
            singles.append(time.perf_counter() - t)

        gathered = []
        for _ in range(reps):
            t = time.perf_counter()
            await asyncio.gather(*[concern._get_input_text() for _ in range(3)])
            gathered.append(time.perf_counter() - t)

    print(
        f"\nn_inputs={n_inputs} digested={digested} rendered_chars={len(text)}"
        f"\n  one call      median {statistics.median(singles) * 1000:7.2f} ms"
        f"  (min {min(singles) * 1000:.2f} max {max(singles) * 1000:.2f})"
        f"\n  3x gathered   median {statistics.median(gathered) * 1000:7.2f} ms"
        f"  (min {min(gathered) * 1000:.2f} max {max(gathered) * 1000:.2f})"
    )
