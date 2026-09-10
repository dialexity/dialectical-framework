"""Probe: what does the Explorer door's uncapped `explore` actually ask for?

WHY
===
`ExplorationPipeline.max_deep_wheels` defaults to `None`, and `None` means **deepen
every wheel that was built**. The Advisor door sets it to 1 (`EXPLORE_DEEP_WHEELS`
in `advisor/tools/explore.py`, a module constant with its rationale in a comment),
but the Explorer agent's own `explore` tool passes nothing, and the pipeline's
docstring justifies that with "the Explorer agent's path, where the user selects
wheels, is already lazy and never sets this."

**That sentence is about a path the tool does not take.** `explore` builds ALL
Cycles and Wheels for the Nexus and then fans out one `ExploreTransformations` per
wheel, concurrently, before the person has selected anything. Wheel count is
`C(N,k) x max(1,(k-1)!) x W(k)` summed over layers, so it is 4 wheels at k=2 and
**96 at k=4** — one `@llm.tool` call whose provider spend is set by a combinatorial
count nobody at the keyboard chose.

This probe measures what that fan-out asks for, so the cap can be decided on a
number instead of on the arithmetic in this paragraph.

WHAT IT MEASURES, AND WHY IT IS FREE
====================================
Provider CALLS, not seconds. Mock brain returns instantly, so a wall clock here is
graph writes plus python and says nothing about the wait — but the call COUNT is the
cost lever, and it is structural: which wheels exist, which edges they share, and
which of those edges already carry a Transformation are all decided by the graph,
not by what a model said. That is why the sibling `probe_build_wheels_offprovider.py`
reproduces the paid run's 24 cycles / 96 wheels / 1,750 effects exactly.

Counting is done by wrapping `mock_brain.build_mock_response`, which is the single
funnel every FORMATTED call goes through once `install_mock_brain` has replaced
`use_brain` (the mocked `wrapper` looks the name up in the `mock_brain` module
namespace when it runs, so patching it here reaches a mock installed earlier by the
autouse fixture). **`utils/call_census.py` reads ZERO under mock brain** —
`record_call` lives inside the real `use_brain`, which is exactly what the mock
replaces — so do not reach for the census here and conclude the tool makes no calls.

The uncounted remainder is the no-`format` branch, which is the agent's own
tool-calling turn. The pipeline is all formatted concerns, so nothing it does escapes
the count; a probe pointed at the Explorer AGENT rather than the pipeline would need
to count that branch too.

    poetry run pytest tests/probe_explore_deep_wheels.py -s
    DIALEXITY_PROBE_EDW_K=4 poetry run pytest tests/probe_explore_deep_wheels.py -s

k defaults to 2 so a by-hand run is quick, and unlike the digest-threshold mistake
the branch under test is reached there: 4 wheels are built and 4 are deepened with
no cap, against 1 with the Advisor's. Only the SCALE differs. **Do not reach for k=4
casually** — the 96-wheel arm ran 41 minutes without finishing (see below), which is
the finding, and it holds the single test Memgraph the whole time.

**This file is not part of the default suite, and neither is any other `probe_*.py`.**
pytest's default `python_files` is `test_*.py`/`*_test.py` and this repo does not
override it, so probes only run when named on the command line.

WHAT IT CANNOT SAY
==================
- **No seconds worth quoting.** Nothing here prices latency. To price the calls, use
  the archived paid mean from `tests/e2e/probe_explore_cost.py` (1 PP, weak tier: 47
  calls, 367.8s provider time, 7.8s mean call, 4.15x parallelism) — and price COST
  with `provider_s`, never latency, because the fan-out already compresses.
- **The reuse it measures is real but its FLOOR is not tested.** Transformations are
  reused per graph EDGE (`transformation_repository.find_by_edge` in
  `_process_edge_pair`), and whether two wheels share an edge is structural. What is
  NOT structural is `_missing_categories`: it budgets against the insight categories
  already present, and mock brain returns one identical candidate shape every time, so
  a run where the model produced several DISTINCT categories per edge could ask for
  more than this shows. Read the counts as a LOWER bound on the uncapped ask.
- Setup (`ExpandPolarity` per tension, `CreateNexus`) is deliberately outside the
  counted window. Only the pipeline is measured.

WHAT IT FOUND, 2026-09-10
=========================
k=2, one box, mock brain:

                                       cycles wheels deep transf calls off-provider
    Explorer door (max_deep_wheels=None)    3      4    4     12   100        8.22s
    Advisor door (max_deep_wheels=1)        3      4    1      4    36        3.27s

The `off-provider` column is printed to show the shape of the work, not to be quoted:
a repeat run right after a `docker compose restart` gave 56.26s / 33.35s for the same
two arms, 7x the numbers above, while every count — 3/4/12/100 and 3/4/4/36 — came back
identical. **The counts are structural; the seconds are the box's cache.**

Deepening is where the money is: 36 of the uncapped door's 100 calls are
`ActionCandidateDto` and only 4 (3 `CausalCycleAssessmentDto` + 1 preset resolution)
belong to building the wheels at all. Reuse is real but weak — 4 wheels cost 100 calls
where 4 independent ones would cost ~144, so sharing edge pairs saves ~30%, not the
order of magnitude the dedup might suggest.

**k=4 did not finish.** 96 wheels, LLM mocked so every call returns instantly, one
box: killed after 41 minutes still working, Memgraph at 137% CPU and 2.3 GB of
traffic. That is the finding, not a box problem — there is no provider in this run to
wait for, so it is graph work alone, and it is already past any interactive budget
before a single token is paid for.

WHAT THIS DID *NOT* TURN OUT TO BE
==================================
The uncapped door **no agent can open.** `explorer.py`'s `@llm.tool explore` is in NO
toolset: `Explorer._tools()` returns `build_wheels` + `explore_transformations` (the
lazy pair), the Advisor has its own capped `advisor/tools/explore.py`, the Explorer
system prompt says "let the user choose which wheel(s)... call
`explore_transformations` for that specific wheel", and `docs/agents.md` documents only
the per-wheel path. Its one importer is `tests/test_tool_signatures.py`, which lists it
among the framework's tools — so it reads as live and is not.

What remains reachable is a HEADLESS caller constructing `ExplorationPipeline` without
`max_deep_wheels` (the pattern in `tests/test_agents_e2e.py`, which bounds k instead).
For that caller the numbers above are the price list.
"""

from __future__ import annotations

import os
import time

import pytest

import mock_brain as mock_brain_module
from dialectical_framework.agents.explorer.explorer import ExplorationPipeline
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from probe_build_wheels_offprovider import INTENT, TENSIONS, _perspectives

#: 2 keeps a by-hand run quick; 4 is the run that makes the point. Bounded by the
#: sibling's tension list, since structural dedup is per-content and a repeated
#: tension would skip the work being counted.
K = max(1, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_EDW_K", "2"))))

#: The two doors, by the only thing that differs between them.
ARMS: list[tuple[str, int | None]] = [
    ("Explorer door (max_deep_wheels=None)", None),
    ("Advisor door (max_deep_wheels=1)", 1),
]

#: `tests/e2e/probe_explore_cost.py`, 2026-08-27, weak tier, 1 PP. Used only to turn
#: a call count into provider-seconds; it is one archived tier and one wheel size, so
#: it prices an order of magnitude and not a wall clock.
PAID_MEAN_CALL_S = 7.8


class _Counter:
    """Every formatted provider call, grouped by the DTO it was asked for."""

    def __init__(self) -> None:
        self.by_format: dict[str, int] = {}

    @property
    def total(self) -> int:
        return sum(self.by_format.values())

    def add(self, name: str) -> None:
        self.by_format[name] = self.by_format.get(name, 0) + 1


def _count_calls(patch, counter: _Counter) -> None:
    """Wrap the one funnel every mocked formatted call goes through.

    `build_mock_response` is looked up in the `mock_brain` module namespace when the
    patched `use_brain` wrapper runs, not captured in its closure, so setting it here
    is picked up by a mock installed earlier by the autouse fixture.
    """
    original = mock_brain_module.build_mock_response

    def wrapper(format_model, *args, **kwargs):
        counter.add(getattr(format_model, "__name__", str(format_model)))
        return original(format_model, *args, **kwargs)

    patch.setattr(mock_brain_module, "build_mock_response", wrapper)


async def _run_arm(cap: int | None, monkeypatch) -> dict:
    """One door, on its own Case so nothing is reused from the other."""
    case = Case()
    case.commit()
    with scope(case.sid):
        hashes = await _perspectives(K)
        created = await CreateNexus().resolve(
            intent=INTENT, perspective_hashes=hashes
        )

        counter = _Counter()
        with monkeypatch.context() as patch:
            _count_calls(patch, counter)
            started = time.monotonic()
            pipeline = ExplorationPipeline(
                nexus_hash=created.nexus.hash, max_deep_wheels=cap
            )
            result = await pipeline.resolve()
            wall = time.monotonic() - started

    return {
        "wheels": len(result.wheel_hashes),
        "cycles": len(result.cycle_hashes),
        "deepened": len(result.deepened_wheel_hashes),
        "transformations": result.transformation_count,
        "errors": [e.model_dump() for e in result.errors],
        "calls": counter.total,
        "by_format": counter.by_format,
        "wall": wall,
    }


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_what_the_uncapped_explore_asks_for(di_container, monkeypatch):
    print(
        f"\n### ExplorationPipeline at k = {K} perspectives, LLM mocked"
        f" (DIALEXITY_PROBE_EDW_K to change)"
    )

    rows: list[tuple[str, dict]] = []
    for label, cap in ARMS:
        rows.append((label, await _run_arm(cap, monkeypatch)))

    print(
        f"\n  {'':<38}{'cycles':>7}{'wheels':>7}{'deep':>6}"
        f"{'transf':>8}{'calls':>7}{'off-provider':>14}"
    )
    for label, row in rows:
        print(
            f"  {label:<38}{row['cycles']:>7}{row['wheels']:>7}{row['deepened']:>6}"
            f"{row['transformations']:>8}{row['calls']:>7}{row['wall']:>13.2f}s"
        )

    print("\n  CALLS BY DTO (the uncapped door)")
    uncapped = rows[0][1]
    for name, count in sorted(
        uncapped["by_format"].items(), key=lambda kv: -kv[1]
    ):
        print(f"       {count:>6}x  {name}")

    capped = rows[1][1]
    if capped["calls"]:
        ratio = uncapped["calls"] / capped["calls"]
        print(
            f"\n  The uncapped door asks for {ratio:.1f}x the capped one"
            f" ({uncapped['calls']} calls against {capped['calls']})."
        )
    print(
        f"  At the archived paid mean of {PAID_MEAN_CALL_S}s per call"
        f" (`probe_explore_cost.py`, weak tier), {uncapped['calls']} calls is"
        f" ~{uncapped['calls'] * PAID_MEAN_CALL_S / 60:.0f} minutes of PROVIDER time"
        f" for one tool call — compressed by the fan-out, but paid in full."
    )
    for label, row in rows:
        if row["errors"]:
            print(f"  {label}: {len(row['errors'])} wheel(s) failed to deepen")

    # The finding, not a health check: the two doors differ only in the cap, and the
    # uncapped one deepens everything the combinatorics produced.
    assert uncapped["deepened"] == uncapped["wheels"], (
        "the uncapped door did not deepen every wheel, so `max_deep_wheels=None`"
        " no longer means what this probe was written to size"
    )
    assert capped["deepened"] == 1, (
        f"the capped door deepened {capped['deepened']} wheels, not 1"
    )
    assert uncapped["calls"] > capped["calls"], (
        "capping changed nothing about the call count, which would mean the cost is"
        " not in the per-wheel fan-out at all"
    )
