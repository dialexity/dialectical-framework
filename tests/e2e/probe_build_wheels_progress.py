"""Probe: what does `build_wheels` cost, and what can a person see while it runs?

WHY THIS EXISTS SEPARATELY FROM `probe_explore_progress.py`
==========================================================
That probe measured `explore` end to end and closed its big hole: the transformation
phase went from 34s of total silence to ~10-12s of labelled waiting. But **every run
it ever recorded used ONE perspective**, and one perspective is exactly the input for
which `build_wheels` does almost no work:

    causal_cycles = [c for c in new_cycles if c.perspective_count >= 2]
    causal_wheels = [w for w in new_wheels if self._safe_polarity_count(w) >= 2]
    if causal_cycles or causal_wheels:
        await self._run_estimation(causal_cycles, causal_wheels)

With one perspective nothing reaches layer 2, so `CausalityEstimation` — the only
provider work in the whole skill — **never ran in any measurement taken so far.**
That is why `build_wheels` reads as a harmless 1.5s in that probe's archive. The same
mistake as the digest threshold: the archived probe size does not reach the branch
that costs. So the number everyone has been quoting for stage 1 of `explore` is the
cost of the branch that does nothing.

And the cost is combinatorial rather than linear. The structure count was already
written down correctly in CLAUDE.md — `C(k, L)` * `max(1, (L-1)!)` cycles per layer,
`W(L)` wheels per cycle with `W(1..4) = 1, 2, 4, 8` — and what this file adds is the
CALL count, which is one `CausalCycleAssessmentDto` per estimated structure and not
one per cycle: `_run_estimation` takes both lists, gated at layer 2, so

    calls(k) = sum over L in 2..min(k, max_wheel_layer) of
                   C(k, L) * (L-1)! * (1 + W(L))

    k=2 ->  1*3                                    =    3
    k=3 ->  3*3 + 2*5                              =   19
    k=4 ->  6*3 + 8*5 + 6*9                        =  112
    k=5 -> 10*3 + 20*5 + 30*9                      =  400   (layer cap binding)

(the left factor of each term is the CYCLE count at that layer, `C(k,L)*(L-1)!`)

`_estimation_calls` below is that formula, and the k=2/k=4 rows of the last run match
it exactly, so it can be trusted for the sizes nobody has paid for. **An earlier
version of this docstring predicted 1 and 20 sequences** by summing only the cycle
permutations and forgetting both the layer-1 cycles and the wheels-per-cycle factor.
It was wrong by 3x and 5.6x. Prefer the formula above, and prefer CLAUDE.md's
structure arithmetic over any re-derivation of it.

WHAT IT MEASURES
================
`BuildWheels.resolve()` ALONE — no transformations, no synthesis — at two nexus
sizes, each on its own nexus built from its own perspectives:

- **k=2** is the Advisor's hard ceiling. `advisor_max_perspectives_per_exploration`
  defaults to 2 and `run_exploration_detailed` slices the excess off as deferred, so
  no Advisor `explore` call can ever hand `build_wheels` more than this.
- **k=4** is a plausible Explorer nexus, where nothing caps the perspective count and
  `max_deep_wheels=None` means every wheel built here is also deepened.

Two questions, and the second matters as much as the first:

1. **What does estimation cost** in calls and seconds, and does it grow the way the
   arithmetic says?
2. **How many wheels does a nexus of size k produce?** That count IS the fan-out on
   the Explorer door — `ExplorationPipeline` gathers one `ExploreTransformations` per
   deepened wheel and each opens its own progress stream keyed on its own wheel hash.
   So this number decides whether folding those into one stream per `explore` call is
   obviously right (a handful) or lossy (dozens).

Measuring `BuildWheels` alone is what makes this affordable: counting the wheels does
not require paying for a transformation chain on each of them.

WHY THE PERSPECTIVE SETS ARE DISJOINT
====================================
Structural dedup is per-content, not per-nexus: a layer-2 cycle over (p1, p2) that
already exists is not returned in `new_cycles`, and estimation only ever runs on what
is new. So a sweep that grew ONE nexus (k=2, then add two more) would estimate the
full set at k=2 and only the additions at k=4, and the growth curve would be an
artefact of the sweep order rather than a property of nexus size. Each size therefore
gets its own perspectives. The cost is one `ExpandPolarity` per perspective in setup,
outside every measured window.

WHAT IT CANNOT SAY
==================
Two sizes, one model, one run each. The wheel and cycle COUNTS are structural and
should reproduce exactly; the seconds are a single sample and the explore probe's own
history is the warning there (a 1 KB source ran 651s once and 45.5s the next time).
Read the counts as facts and the durations as an order of magnitude.

The progress stream was EMPTY on the first run, and that was the point of it:
`build_wheels`, `perspective_combination`, `causality_estimation` and the estimator
contained zero progress calls between them — verified by grep, not assumed — so the
results below are the BEFORE side of the pair.

**That has since changed, and this probe is now the before-and-after** — see the
2026-09-10 run at the bottom, which answers both questions this paragraph posed.
`BuildWheels` opens a scope of its own (it is a tool a model can call directly) and
reports three steps: the combination phase, then one per estimation pass. The two
claims worth checking here are ones a green unit test cannot make: that the
combination label ARRIVES BEFORE the phase it announces (that phase never suspends,
so the label is delivered by an explicit `flush_progress` and nothing else), and how
wide the remaining gaps are once it does. Both now measured.

    poetry run pytest tests/e2e/probe_build_wheels_progress.py -s --real-llm

RESULTS
=======
One run, haiku-4.5, 2026-09-09, 117 calls / 287s total:

    k  cycles  wheels  calls   wall  in-flight  off-provider  widest graph gap
    2       3       4      4   15.6s      14.5s          1.1s   7.5s  (48%)
    4      24      96    113  163.2s      26.4s        136.8s  110.9s (68%)

Both structure counts reproduce CLAUDE.md's formula exactly (k=4 -> 24C/96W, the
figure already written there) and both call counts reproduce `_estimation_calls`
exactly, so the arithmetic above is now confirmed rather than asserted.

**1. `CausalityEstimation` does run, and it is one provider call per structure.**
k=2 spent 21.0s of provider time on 3 calls; k=4 spent **1,102.8s on 112 calls** at
41.75x parallelism. So the 1.5s that `probe_explore_progress.py`'s archive records
for stage 1 is the PP=1 branch, exactly as suspected, and it understates a
4-perspective nexus by two orders of magnitude in provider spend.

**2. The k=4 wall is NOT provider time, and that is the finding this probe did not
set out to make.** In-flight was 26.4s of a 163.2s wall: **137s — 84% — is
off-provider**, i.e. `PerspectiveCombination` plus the sequential graph writes for
2,437 effects. Every latency lever applied to this tree so far (gathering, cache
splitting, reply reuse, retry curves) aims at provider time and has nothing to bite
on here. Where that 137s actually goes is UNMEASURED: the widest gap is 110.9s
between effects 9 and 10, after which 2,427 effects arrive in a flood, and this run
did not print the bursts (the burst dump in `_report` was added afterwards, for the
next run to answer it). **Locating it costs nothing** — it is graph and Python time,
so mock brain reproduces it, and that is the cheapest next measurement in the tree.

**3. Nothing reports, and it is the largest single silent stretch measured anywhere
in this codebase.** 110.9s at k=4 with an empty progress channel, against the 52.3s
graph-only ingest gap and the 34s transformation gap that motivated the whole seam.
Even the Advisor's own ceiling (k=2) sits silent for 7.5s, 48% of its wall.

**4. The Explorer door deepens ALL 96 wheels.** `ExplorationPipeline` defaults
`max_deep_wheels=None` and `_select_deep_wheels` ends `ranked[: self.max_deep_wheels]`,
so `explorer.explore` on a 4-perspective nexus would gather 96 `ExploreTransformations`
plus 96 `GenerateSynthesis`, each installing its own keyed scope — 192 concurrent
streams a host would have to draw. At 6 Transformations per wheel and 4 sequential
`TransformationGeneration` calls each, that is on the order of 2,300 provider calls
for one tool call. **Read this as a budget question and not an instrumentation one:**
the Advisor door caps at `EXPLORE_DEEP_WHEELS = 1` on purpose and the Explorer door
caps at nothing, and no measurement of the Explorer door at k>1 exists. (The 192
streams are now ONE — both skills defer into `ExplorationPipeline`'s scope — so the
instrumentation half of this is closed and the SPEND half is untouched.)

SECOND RUN, 2026-09-10 — three labels land, and the k=4 wall fell 3.2x
=====================================================================
Same probe, same tier, after two unrelated changes landed: the six DB levers (see
CLAUDE.md's `_signature_of` note) and the three-door progress scopes. 117 calls again,
179.5s total against 287s::

    k  cycles  wheels  calls  wall   in-flight  off-provider  graph gap  BOTH channels
    2       3       4      4  17.1s      15.2s          1.9s   9.0s(52%)   8.9s (52%)
    4      24      96    113  51.0s      25.5s         25.5s  14.9s(29%)  12.8s (25%)

    (was: k=2 15.6s / 7.5s(48%) graph-only; k=4 163.2s / 136.8s off-provider /
     110.9s(68%) graph gap, with an EMPTY progress channel)

**1. The combination label arrives BEFORE the phase, and only `flush_progress` makes
that true.** At k=4 the label publishes at **2.05s** and the phase's own 1,629 effects
land at **14.87s** — 12.8s of labelled quiet where finding 3 measured 110.9s of blank
quiet. The phase never suspends, so without the four `asyncio.sleep(0)`s the label
would have been stamped and delivered at 14.87s alongside the flood it was meant to
announce: a 0.0s flash. This is the claim `tests/test_explore_progress_scope.py`
asserts against a real bus, confirmed here on the real path.

**2. Both sizes close 3/3 with one stage, one key, no phantom step.** k=2 at
1.08s / 2.22s / 8.19s / final 17.08s; k=4 at 2.05s / 14.87s / 25.24s / final 51.05s.
Every label covers work that ran, and `pred` matches `calls` exactly at both sizes
(4 and 113), so the estimator is still one call per structure.

**3. The k=4 wall is 51.0s, down from 163.2s, and this is the first PAID confirmation
of the DB work** — off-provider fell 136.8s -> 25.5s, i.e. the 84%-of-wall finding
above is now 50%, and the structure counts are unchanged (24C/96W, 113 calls,
2,437 effects). Provider time barely moved (1,052.9s at 41.22x against 1,102.8s at
41.75x), which is the point: nothing here touched a provider call. **Finding 2's
"where that 137s goes is UNMEASURED" is therefore obsolete** — it went where the
off-provider probe said it did, and most of it is gone.

**4. The widest remaining k=4 gap IS the combination phase, now labelled** (12.8s
between the label and its own flood), which is exactly the part of the seam work still
open: `flush_progress` puts a label in FRONT of a synchronous phase and cannot narrate
its inside. **Closed the same day, and not by the seam** — that flood was the phase
holding the event loop, not the reporting being slow, so `PerspectiveCombination` now
awaits between complete find-or-create units and delivers 1,459 of 1,750 effects while
it runs (measured in `tests/probe_build_wheels_offprovider.py`, which is free and is the
right instrument for it: delivery timing has nothing to do with provider time). Read the
12.8s below as the last measurement of the OLD behaviour; a paid re-run would re-time the
same graph writes and is not what proves this one. **And the share inverted between the sizes** — k=2's 8.9s is 52% of its
wall against k=4's 25% — so on the door people actually hit (the Advisor caps at 2)
the last estimation pass is half the wait under one correct label. That pass gathers
its calls per (type, size) group and writes Rationale effects as each group persists,
so it is `note_progress`'s recorded counter-case, not a site for it.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.explorer.skills.build_wheels import BuildWheels
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.retry_accounting import retry_account

#: Same taxonomy URIs as the explore probes, so a structure built here is comparable
#: to one built there.
_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

#: Six distinct tensions, because the two sizes take DISJOINT sets (2 + 4) for the
#: dedup reason in the docstring. The first two are the explore probes' own pair, so
#: the k=2 row is directly comparable to their setup.
TENSIONS = [
    (
        "Buy out the cofounder and take full control",
        "Keep him to retain his customer relationships",
    ),
    (
        "Move the anchor accounts into my own name",
        "Leave the client relationships where they already sit",
    ),
    (
        "Raise a round now while the terms are good",
        "Stay unfunded and keep every decision ours",
    ),
    (
        "Publish the roadmap so customers can plan",
        "Hold it back so competitors cannot",
    ),
    (
        "Promote from inside to reward the people who stayed",
        "Hire outside to get skills the team does not have",
    ),
    (
        "Standardise the process so any engineer can run it",
        "Leave room for judgement where the work is unusual",
    ),
]

INTENT = "Whether to buy out the cofounder before the next raise"

#: The sizes measured, and why each one. Not env-driven: the whole point is that the
#: BRANCH is size-dependent, and a default that silently misses it is the defect this
#: probe was written to correct.
SIZES = (2, 4)

_NOTICEABLE_GAP_S = 3.0

#: Wheels per cycle by layer, from CLAUDE.md's combinatorial-growth note.
_WHEELS_PER_CYCLE = {1: 1, 2: 2, 3: 4, 4: 8}


def _estimation_calls(k: int, max_layer: int = 4) -> int:
    """Predicted `CausalCycleAssessmentDto` calls for a nexus of `k` perspectives.

    One call per structure that clears the layer-2 gate — cycles AND wheels — which
    is what the k=2/k=4 measurements below confirm. See the docstring's arithmetic.
    """
    total = 0
    for layer in range(2, min(k, max_layer) + 1):
        cycles = math.comb(k, layer) * math.factorial(layer - 1)
        total += cycles * (1 + _WHEELS_PER_CYCLE[layer])
    return total


async def _measure(bus, sid: str, nexus_hash: str) -> dict:
    """Run `BuildWheels` alone, collecting both channels and the call census."""
    seen: list[tuple[float, object]] = []
    progress: list[tuple[float, object]] = []
    ready = asyncio.Event()
    progress_ready = asyncio.Event()
    started = 0.0

    async def _collect() -> None:
        async with bus.subscribe(sid) as subscriber:
            ready.set()
            async for event in subscriber:
                seen.append((time.monotonic() - started, event.message.effect))

    async def _collect_progress() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            progress_ready.set()
            async for event in subscriber:
                progress.append((time.monotonic() - started, event.message))

    collector = asyncio.create_task(_collect())
    progress_collector = asyncio.create_task(_collect_progress())
    # Subscribe BEFORE the work, or the first events — the ones that decide time to
    # first sign of life — are dropped.
    await ready.wait()
    await progress_ready.wait()

    started = time.monotonic()
    with call_census() as census, retry_account() as account:
        build = BuildWheels(nexus_hash=nexus_hash)
        result = await build.resolve()
    waited = time.monotonic() - started

    await asyncio.sleep(0.5)
    collector.cancel()
    progress_collector.cancel()
    for task in (collector, progress_collector):
        try:
            await task
        except asyncio.CancelledError:
            pass

    return {
        "result": result,
        "report": build.report,
        "waited": waited,
        "seen": seen,
        "progress": progress,
        "census": census,
        "account": account,
    }


def _gaps(stamps: list[float], waited: float) -> list[tuple[float, str]]:
    if not stamps:
        return [(waited, "the whole run")]
    out = [(stamps[0], "before the first event")]
    for i in range(1, len(stamps)):
        out.append((stamps[i] - stamps[i - 1], f"between events {i} and {i + 1}"))
    out.append((waited - stamps[-1], "after the last event"))
    return out


def _report(k: int, run: dict) -> None:
    result, census, account = run["result"], run["census"], run["account"]
    waited, seen, progress = run["waited"], run["seen"], run["progress"]

    cycles = [c for c in result.new_cycles if c.hash]
    wheels = [w for w in result.new_wheels if w.hash]

    print(f"\n{'=' * 78}\nk = {k} perspectives")
    print(f"  waited {waited:7.1f}s   calls {census.count:3d}"
          f"   provider {census.provider_s:7.1f}s   in-flight {census.busy_s:7.1f}s"
          f"   parallelism {census.parallelism:5.2f}x")
    if account.count:
        print(f"  retries {account.count} {dict(account.kinds)}, slept {account.sleep_s:.1f}s")
    print(f"  built {len(cycles)} cycle(s), {len(wheels)} wheel(s)")
    print(f"  cycle_intent {run['report'].artifacts.get('cycle_intent')!r}")

    if census.count:
        by_dto: dict[str, tuple[int, float]] = {}
        for call in census.calls:
            dto = call.format_name or "no format"
            n, total = by_dto.get(dto, (0, 0.0))
            by_dto[dto] = (n + 1, total + (call.seconds or 0.0))
        print("  provider seconds by DTO:")
        for dto, (n, total) in sorted(by_dto.items(), key=lambda kv: -kv[1][1]):
            print(f"    {total:8.1f}s  {n:3d} call(s)  mean {total / n:5.1f}s  {dto}")
    else:
        print("  NO provider calls — estimation did not run at this size")

    # The fan-out this size implies on the Explorer door. No longer a stream count —
    # `ExplorationPipeline` owns one stream now and both skills defer into it — but the
    # PROVIDER fan-out is untouched, and that door still deepens every wheel.
    print(f"  => on the Explorer door this nexus deepens {len(wheels)} wheel(s),"
          f" so ExplorationPipeline would run {len(wheels)} concurrent"
          f" transformation chain(s) plus {len(wheels)} synthesis call(s) —"
          f" one stream, unbounded spend")

    print(f"  graph effects {len(seen)}   progress events {len(progress)}")
    if progress:
        print("  PROGRESS STREAM:")
        for t, event in progress:
            kind = "final" if event.final else ("note " if event.note else "step ")
            print(f"    {t:7.2f}  {event.done:3d}/{event.total:<4d} {kind}"
                  f" {event.detail or '(empty)'}")
    else:
        print("  PROGRESS STREAM EMPTY — this is now a DEFECT, not the finding:"
              " `BuildWheels` opens its own scope and reports three steps")

    # Burst-by-burst, because at k=4 the wall is mostly NOT provider time and the
    # only way to see where it went is when the writes actually land.
    if seen:
        print("  what a graph-only host would see, burst by burst (1s buckets):")
        bursts: list[list[tuple[float, object]]] = [[seen[0]]]
        for stamp, effect in seen[1:]:
            if stamp - bursts[-1][-1][0] <= 1.0:
                bursts[-1].append((stamp, effect))
            else:
                bursts.append([(stamp, effect)])
        for burst in bursts:
            kinds: dict[str, int] = {}
            for _, effect in burst:
                node = getattr(effect, "node", None)
                label = node.label if node else effect.effect_type
                kinds[label] = kinds.get(label, 0) + 1
            span = (f"{burst[0][0]:.1f}s" if len(burst) == 1
                    else f"{burst[0][0]:.1f}-{burst[-1][0]:.1f}s")
            top = ", ".join(
                f"{n}x {k}" for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])
            )
            print(f"    {span:>16}  {len(burst):5d} effects  {top}")

    stamps = [t for t, _ in seen]
    worst, where = max(_gaps(stamps, waited), key=lambda g: g[0])
    share = worst / waited * 100 if waited else 0.0
    print(f"  WIDEST GRAPH-SILENT GAP {worst:.1f}s ({share:.0f}% of the wall) — {where}")

    # The number that says whether the instrumentation earned anything: a host
    # subscribed to BOTH channels sees the union, so the graph gap above is only dead
    # air where no progress event falls inside it. Reported separately rather than
    # replacing the graph figure, because the two answer different questions — the
    # graph stream is what a host had BEFORE any of this, and the comparison is the
    # finding.
    both = sorted(stamps + [t for t, _ in progress])
    worst_both, where_both = max(_gaps(both, waited), key=lambda g: g[0])
    share_both = worst_both / waited * 100 if waited else 0.0
    print(f"  WIDEST GAP ON BOTH CHANNELS {worst_both:.1f}s ({share_both:.0f}%)"
          f" — {where_both}")
    if worst_both >= _NOTICEABLE_GAP_S:
        print(f"    still over the {_NOTICEABLE_GAP_S}s legibility floor: dead air a"
              f" person cannot distinguish from a hang even with progress subscribed")


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(3600)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_build_wheels_progress(di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(f"sizes: {SIZES} perspectives, on disjoint perspective sets")

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    bus = di_container.event_bus()
    await bus.connect()
    assert ExecutionReport._event_bus is bus, (
        "the report class is not publishing to this bus, so an empty graph stream"
        " would say nothing about the framework"
    )
    assert progress_module._event_bus is bus, (
        "progress is not wired to this bus — see `utils/progress.set_event_bus`;"
        " without this a silent progress stream below would be a setup bug rather"
        " than a finding"
    )

    runs: dict[int, dict] = {}
    try:
        case = Case()
        case.commit()
        with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
            offset = 0
            for k in SIZES:
                # Disjoint perspectives per size, so structural dedup cannot make a
                # later size look cheaper than it is.
                assert offset + k <= len(TENSIONS), (
                    f"need {offset + k} tensions for sizes {SIZES}, have"
                    f" {len(TENSIONS)}"
                )
                tensions = TENSIONS[offset : offset + k]
                offset += k

                hashes: list[str] = []
                for thesis, antithesis in tensions:
                    t = Statement(text=thesis, meaning=_T_MEANING)
                    t.commit()
                    a = Statement(text=antithesis, meaning=_A_MEANING)
                    a.commit()
                    polarity = Polarity()
                    polarity.set_t(t, heuristic_similarity=1.0)
                    polarity.set_a(a, heuristic_similarity=0.8)
                    polarity.commit()
                    perspectives = await ExpandPolarity(
                        polarity_hash=polarity.hash
                    ).resolve()
                    assert perspectives, "ExpandPolarity produced no Perspective"
                    hashes.append(perspectives[0].hash)

                create = CreateNexus()
                created = await create.resolve(
                    intent=INTENT, perspective_hashes=hashes
                )
                runs[k] = await _measure(bus, case.sid, created.nexus.short_hash)
    finally:
        await bus.disconnect()

    for k in SIZES:
        _report(k, runs[k])

    print(f"\n{'=' * 78}\nSUMMARY — how stage 1 of `explore` grows with nexus size")
    print(f"  {'k':>3} {'cycles':>7} {'wheels':>7} {'calls':>6} {'pred':>6}"
          f" {'wall':>8} {'in-flight':>10} {'off-provider':>13}")
    for k in SIZES:
        run = runs[k]
        census = run["census"]
        off = run["waited"] - census.busy_s
        print(f"  {k:>3} {len(run['result'].new_cycles):>7}"
              f" {len(run['result'].new_wheels):>7} {census.count:>6}"
              f" {_estimation_calls(k) + 1:>6}"
              f" {run['waited']:7.1f}s {census.busy_s:9.1f}s {off:12.1f}s")
    print("  'pred' is `_estimation_calls(k)` plus the one auto-preset call, so it is a"
          " FORMULA and not a measurement — a mismatch means the estimator stopped"
          " calling once per structure.")
    print("  'off-provider' is wall minus the union of all call intervals: the part of"
          " the wait that no provider is responsible for, i.e. combination plus the"
          " sequential graph writes. Watch it, not `provider`, when it dominates.")

    assert runs, "no size ran"
    # The only assertion: the sweep must actually have reached the branch that costs.
    # A run where neither size made a provider call has measured nothing, and would
    # otherwise be archived as though it had.
    assert any(runs[k]["census"].count for k in SIZES), (
        "no size made a single provider call, so CausalityEstimation never ran and"
        " this run says nothing about the branch it exists to price"
    )
