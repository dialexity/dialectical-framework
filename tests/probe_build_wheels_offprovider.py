"""Probe: where does `build_wheels`' off-provider wall go, and can EITHER channel narrate it?

WHY THIS IS FREE
================
`tests/e2e/probe_build_wheels_progress.py` measured `BuildWheels` on a real provider
at k=4 perspectives and found something it was not looking for: **in-flight provider
time was 26.4s of a 163.2s wall, so 137s — 84% — belonged to nobody's API call.** It
also found the largest silent stretch measured anywhere in this tree, 110.9s with an
empty progress channel, after which 2,427 graph effects arrived in a flood.

Off-provider wall is python and graph traffic. Mock brain reproduces all of it at
zero provider cost, which makes this the cheapest measurement available and the one
that has to happen BEFORE instrumenting anything: if the wait is graph writes rather
than reasoning, a `note_progress` per estimation call narrates the wrong 26 seconds.

WHAT IT MEASURES
================
Three things, on one `BuildWheels.resolve()` run:

1. **A phase breakdown** — inclusive wall per method, by wrapping them for timing
   only. Nesting is real (`_build_layer` contains the cycle and wheel builders), so
   the rows are marked with indentation and a residual is printed rather than
   pretending the columns add up.
2. **Graph traffic** — every `execute`/`execute_and_fetch` through the client,
   counted and timed. `execute_and_fetch` hands back the connection's own generator
   and the query runs on ITERATION, so timing the call alone would report ~0; the
   wrapper times the consumption too, which is why its seconds are trustworthy and
   why they include the caller's own loop body between `next()` calls.
3. **Whether either channel can speak during the phase** — effects are collected
   with arrival timestamps and compared against the instant
   `PerspectiveCombination.resolve` RETURNED.

That third one is the point, and the mechanism is already documented at the seam
without anyone having joined it to this path. `ExecutionReport._emit` and
`progress._publish` both end in `loop.create_task(...)`. A task does not run until
the loop is next given control. **`PerspectiveCombination.resolve` is `def`, not
`async def`, and so is every method under it** — it builds all 24 cycles and 96
wheels and commits them without a single `await`. So every effect it emits is
QUEUED, and the flood at the end of the paid run is not a host rendering slowly:
it is the first moment the loop was free to deliver anything.

(That was true when this was written and the phase has since been changed — see THE
PHASE NOW YIELDS at the end. The paragraphs below are kept as the measurement that
identified the fix.)

The consequence for instrumentation is the finding, not a caveat: **`report_progress`
inside that phase would be scheduled and not delivered, then arrive all at once when
the phase ends.** `_publish`'s own comment already warns that "the task below does
not run until the next suspension point" — it is there because reading `scope.done`
inside `_send` reported delivery-time counters. The same sentence means a fully
synchronous phase cannot be narrated at all, whatever labels are added to it.
`test_the_progress_channel_cannot_speak_from_a_synchronous_phase` demonstrates that
in isolation, so the claim does not rest on reading the k=4 timings correctly.

SIZE, AND WHY A SMALL DEFAULT IS HONEST HERE
===========================================
`K` defaults to 2 so a by-hand run is quick. That is NOT the mistake the digest
threshold made: there, the archived size never reached the branch that costs, and here
the branch is reached at k=2 — `CausalityEstimation` is gated at layer 2 and k=2 clears
it. Only the SCALE differs, and scale is what `DIALEXITY_PROBE_BW_K=4` is for. Run it
at 4 to reproduce the numbers below; expect a couple of minutes.

**This file is not part of the default suite, and neither is any other `probe_*.py`.**
pytest's default `python_files` is `test_*.py`/`*_test.py` and this repo does not
override it, so probes only run when named on the command line. Do not read a green
suite as evidence that any measurement below still holds.

WHAT IT CANNOT SAY
==================
Mock brain returns instantly, so the estimation row here is graph writes plus python
with the provider removed — never read it as the real estimation cost (that is
1,102.8s of provider time across 112 calls, from the paid probe). And one run on one
machine: read the SHAPE, not the seconds.

    poetry run pytest tests/probe_build_wheels_offprovider.py -s
    DIALEXITY_PROBE_BW_K=4 poetry run pytest tests/probe_build_wheels_offprovider.py -s

RESULTS
=======
The numbers below are the BASELINE, before the signature cache in
`WheelRepository`. They are kept because they are what identified the cache; for
what it changed, see AFTER THE FIX at the end.

2026-09-09, mock brain. k=2 in 1.18s; k=4 twice, 180.7s and 149.8s (same machine,
so read the seconds as ±20%; the counts below were IDENTICAL across both runs).

    k=4 phase breakdown (inclusive; indented rows nest)
      116.59s  77.8%    1x  COMBINATION (sync)
      116.59s  77.8%    4x    build_layer
        0.19s   0.1%   24x      find_or_create_cycle
      111.76s  74.6%   24x      build_wheels_for_cycle     <-- 4.7s per cycle
        4.57s   3.1%    4x      connect_opposite_pairs
       27.88s  18.6%    2x  ESTIMATION (mocked, so writes + python only)

**1. 94% of the wall is graph client traffic, and it is 300,517 `execute_and_fetch`
calls to build 96 wheels.** k=2 already shows the shape: 2,260 fetches for 4 wheels.
This is not reasoning time and no provider is involved in any of it.

**2. Two query shapes are 106s of the 116s combination phase**, both of them lazy
relationship traversals off `Statement`:

      63.42s  134,496x  0.47ms  MATCH (source)<-[r:IS_SOURCE_OF]-(target:Statement)
      42.89s   92,037x  0.47ms  MATCH (source)-[r:IS_TARGET_OF]->(target:Statement)

226,533 round-trips at sub-millisecond each. Nothing is slow; there are simply
hundreds of thousands of them, which is what a GQLAlchemy `RelationshipManager`
access costs when it is read inside a loop. The remainder is small by comparison:
22,776 `BELONGS_TO_CYCLE` traversals (5.2s), 9,540 aspect-position reads (4.3s),
4,099 hash-prefix lookups (4.2s).
Subtract 2.65s of the k=4 wall as harness-only: 2,144x `SET n:___DIALEXITY_TEST___`
comes from the test client wrapper and has no production counterpart.

**2b. `DIALEXITY_PROBE_BW_SITES=1` names the code, and it is one call path.** Of
303,101 charges at k=4, 196,568 (65%) are opened beneath a single line —
`find_by_component_sequence`, called once per candidate arrangement:

     105,396x  wheel.py:statements < find_by_component_sequence < _build_wheels_for_cycle
      75,504x  order_transitions < wheel.py:edges < wheel.py:statements
      15,668x  wheel.py:edges < wheel.py:statements < find_by_component_sequence

The repository runs ONE query for every wheel in the sid with a matching transition
count, then reads `wheel.statements` on each to compare canonical signatures. So each
new arrangement re-reads every wheel already built at that size: quadratic, and the
per-read cost is not 1 query but 1 + 4N, because `Wheel.statements` reads
`self.edges`, and `edges` runs `order_transitions`, which walks the chain with its
OWN `source.get()` per transition plus a `target.get()` per step — before the
`statements` loop then reads source and target again for each transition.

Two things had made this look 13x bigger than a hand-derivation predicted: the
`order_transitions` pass (a factor of ~2 that reading `statements` alone does not
show), and charges being `next()` calls rather than queries — a single-row query is
charged three times (open, row, StopIteration), so the 226,533 figure in (2) is
~75,500 actual round-trips. The hand estimate was the right order after all; the
comparison was against the wrong unit.

That also makes `Wheel.edges` a hot spot in its own right, independent of this path:
every access costs 2N+1 traversals, and `_perspectives`, `polarity_count`,
`edge_pairs` and rendering all go through it. The writes are NOT the problem —
`transition.commit` is 12,640 charges for 1,896 real Transition creates.

**3. The paid run's 137s off-provider is exactly this.** 116s combination + ~28s of
estimation writes, with its 26.4s of provider time overlapping rather than adding.
So the k=4 `explore` wall is a query-volume problem wearing a latency problem's
clothes, and it is the largest single lever measured in this tree — larger than
every provider-side saving found so far put together.

**4. Neither channel can narrate that phase, and this is the instrumentation
verdict.** 0 of 1,750 effects were delivered before `PerspectiveCombination.resolve`
returned, at BOTH sizes; all 1,750 arrived after. The isolated demonstration is the
same: three `report_progress` calls from inside a synchronous block, and all three
plus the closing event land at 0.46s — the instant the block hands control back.

**A `def` phase cannot report progress.** Adding labels to `PerspectiveCombination`
would publish nothing during the 116s and then flood a host with the lot, which is
worse than silence: a bar that sits at zero and then completes tells a person their
wait was instant. Narrating it requires the phase to YIELD — an `await` at each
layer or cycle boundary — which is a change to a synchronous reasoning path and has
to be decided as one, not slipped in as instrumentation. Fixing (2) first may make
the question moot, which is the argument for doing it in that order.

(Both happened, in that order: (2) shrank the phase from 116s to ~10s mocked, and the
yield was then taken as its own decision. See THE PHASE NOW YIELDS at the end. The
sentence above is still right about LABELS — none were added.)

AFTER THE FIXES
===============
Three landed, in this order, each measured at k=4 on the same machine:

  **(1) `WheelRepository._signature_of`** caches the canonical signature per wheel,
  so `find_by_component_sequence` reads each wheel's components at most once
  instead of once per candidate arrangement — the quadratic call path from 2b.

  **(2) `immutable=True` on `Transition.source`/`.target`** memoises a non-empty
  endpoint read on the source node INSTANCE, killing the `order_transitions` /
  `statements` double read of the same two endpoints off the same objects.

  **(3) `RelationshipManager.prefetch`, called from `Wheel.edges`** reads both
  endpoint sets for ALL of a wheel's transitions in two batched queries. This is
  the lever (2) could not reach: `edges` builds a FRESH transition list every
  call, so the per-instance memo starts cold each time and (2) only made the
  SECOND pass free. Ordering a wheel now costs 3 round-trips, not 2N+1.

  **(4) `hash_match` in `node_repository`** compares a full-length hash with `=`
  instead of `STARTS WITH`. Same nodes — all hashes are sha256 hexdigests, so
  equal length, so no string is a strict prefix of another — but only equality is
  a point lookup on the `Node(hash)` index. `STARTS WITH` against a parameter made
  the planner fall back to `ScanAllByLabelProperties (n :Node {sid})`: every node
  in the case, then filtered.

  **(5) `BaseNode.commit()` stops asking `find_by_hash` before calling `save()`**,
  which asks the identical question under identical conditions. See below — the
  charge arithmetic for this one closes to the unit.

  **(6) `PerspectiveRepository.find_by_statements`, called from `Wheel._perspectives`**
  batches what was one lookup per edge endpoint (2N per wheel) into one query. This
  was named as "the obvious next lever" in the (3)/(4) notes below, and it was.

                            baseline        (1)         (2)         (3)         (4)     (5)+(6)
      wall                   145.11s     44.83s      48.84s      30.27s      23.67s      19.29s
      COMBINATION (sync)     115.27s     22.57s      18.44s      11.46s      11.05s       9.88s
      build_wheels_for_cycle 110.70s     18.63s      18.99s      10.63s      10.34s       9.20s
      execute_and_fetch      300,517    120,309      94,650      74,920      74,920      67,556
      IS_SOURCE_OF           134,496     34,332      18,282       7,904       7,904       7,904
      IS_TARGET_OF            92,037     26,865      17,256       7,904       7,904       7,904
      BELONGS_TO_CYCLE        22,776      7,904       7,904       7,904       7,904       7,904

**(5) and (6) share one column because they were measured in one run, not A/B'd.** The
wall is a single sample either way; what each bought individually is legible in the two
shapes they touch, and both fell by the amount predicted before the change:

      shape                                     charges before   after   predicted
      MATCH (n:Node) WHERE n.hash = $hash               4,099     2,723     2,723
      // Aspect positions ... (c:Statement)             9,540     3,552         -

**The hash figure is the one worth trusting, because it was predicted to the unit.** The
write probe found that 688 commits asked the same question twice; a miss costs 2 charges
(open, then StopIteration), so removing them had to remove exactly 1,376 charges. It did:
4,099 - 1,376 = 2,723. That is not a fitted number, it was written down first.

For (6) no charge prediction was possible — batching does not remove calls one-for-one,
it trades many small results for one larger one, so charges per call go UP while calls
collapse. Time is the readable measure there: that shape was the most expensive in the
run at 2.96s clean and is now 0.84s, sixth.

**Read the counts, not the wall, between (1) and (2)** — charges fell 21% while the
wall rose, because per-query latency moved 0.32 -> 0.43ms on the same box and the
mocked estimation phase swings 16-25s run to run. Cumulatively the wall is a real
4.8x and the traffic a real -75%, but no single column pair is a clean A/B.

**The (3) -> (4) wall difference is NOT what (4) bought.** Re-running (3) immediately
before making the change, on the box as it was that day, gave 24.28s — not the 30.27s
in the column. So the honest same-session A/B is 24.28s -> 23.67s, and the only
figure that moved for a reason attributable to (4) is the shape's own cost:

      MATCH (n:Node) WHERE ... RETURN n     4,099x    before        after
        per query                                    0.617ms      0.374ms
        total                                          2.53s        1.53s

Charge count is unchanged, as it must be — (4) makes each lookup cheaper, it does not
remove any. And a 1s saving on a 24s run is the SMALL part of this fix: the old
predicate was O(nodes in the case) and the new one is flat, which a 2,100-node probe
database can barely show. `tests/probe_hash_lookup_scaling.py` measures the two curves
side by side at several case sizes and is the place that claim is actually supported.

**The reasoning is untouched, and these counts are the evidence.** 24 cycles and 96
wheels every run, 2,144 `save_node` and 2,821 `save_relationship` every run, 1,750
effects every run. Identical structure, identical writes, identical stream — only
the reads the code did to decide are gone. Full suite green after each.

What did NOT change: the phase was still `def`, so it still delivered 0 of 1,750
effects before returning. ~10s of silence is a smaller lie than 116s but it is the
same lie, so the question survived — just with much less riding on it. It is answered
in the next section.

**The phase that dominated no longer does.** COMBINATION and ESTIMATION are now
9.88s and 8.77s of a 19.29s wall — an even split, where the baseline was 116s
against 28s. Anything further on the combination side is worth at most the smaller
half, and the estimation half is mocked here: on a real provider that phase carries
1,102.8s of API time, so its ~9s of graph work is noise. **Off-provider wall is no
longer the thing to optimise on this path.** It was 84% of the paid k=4 run; the same
arithmetic now puts it at roughly a quarter.

**Where the remaining traffic is, from `DIALEXITY_PROBE_BW_SITES=1` after (3).** No
single line dominates any more; the largest items are:

     12,640x  transition.py:commit < _build_wheels_for_cycle       (1,896 real creates)
      7,536x  find_by_statement < wheel.py:_perspectives < polarity_count
      4,896x  wheel.py:edges < wheel.py:_perspectives < polarity_count
      4,656x  estimation.py:commit < _get_or_create_estimation < upsert_estimation
      3,312x  base_node.py:save < base_node.py:commit < estimation.py:commit
      3,620x  node_repository.py:find_by_hash, across three commit paths

Two observations worth carrying forward. First, **`Wheel.polarity_count` is now the
biggest read on the combination side** — 12,432 charges between its two lines, and
`find_by_statement` is the most expensive query shape in the whole run (9,540 charges,
2.96s). `_perspectives` walks every edge, reads both endpoints, and runs ONE repository
query per component, then throws away every result not in `cycle.perspective_hashes`
— which it already has in hand before the loop starts. Batching those 2N lookups into
one query is the obvious next lever and preserves the filter and the first-seen
ordering exactly. **This became lever (6) above** and did preserve both, though the
ordering claim needed more care than "obvious" suggests: `_perspectives` order becomes
the wheel's `polar_segments`, so it is pinned differentially in
`tests/test_perspectives_batched_lookup.py` against a copy of the per-component loop.

Second, **the top site is now a write path, not a read**, and writes are not
compressible the same way: 1,896 Transitions genuinely have to be created. Of the
2,144 `save_node` calls, note that 2,144 `SET n:___DIALEXITY_TEST___` (1.70s) is
harness-only and has no production counterpart, so ~36% of the measured `save_node`
time is not real.

**What is still unsafe:** a plain memo on `Wheel.edges`, which several callers
re-traverse per wheel (`statements`, `_perspectives`, `polarity_count`,
`_collect_structure_hash_parts`, `_get_commit_dependents`, rendering). Transitions
attach via `transition.cycle.connect(wheel)` — a write through a different manager on
a different node, exactly the case `all()`'s docstring says the memo does not guard —
and `_build_wheels_for_cycle` reads wheels mid-build.

THE PHASE NOW YIELDS, 2026-09-10
================================
`resolve` and `_build_layer` are `async def`, with `await asyncio.sleep(0)` after each
cycle's wheels and after each layer's opposite-direction pass. No label was added and
none is wanted: the phase writes 1,750 effects, so what it lacked was a turn, not a
voice. Three k=4 runs on one box, back to back:

                          with yields   WITHOUT (A/B)   with yields
    effects BEFORE return       1,459               9         1,459
    wall                       59.41s          49.82s        55.13s
    COMBINATION                29.07s          23.83s        25.56s
    build_wheels_for_cycle     27.35s          22.09s        23.59s
    execute_and_fetch          67,556          67,556        67,556
    cycles / wheels             24/96           24/96         24/96
    harness-only query        2.169ms         1.879ms       1.984ms   <- box drift

**1. The finding is 9 -> 1,459 of 1,750 effects delivered while the phase runs**, and
the reading it kills is the one this file made twice: silence during the combination was
never a reporting cost, it was a scheduling artifact. The 291 that still arrive after
the boundary are the estimation phase's, which is where they belong.

**2. The yields cost a few percent, and the raw walls overstate it.** Normalise each run
by the harness-only `SET n:___DIALEXITY_TEST___` query — 2,144 identical statements that
no framework change can touch, so it reads as this box's per-query drift — and the
combination phase costs +2% and +6% against the A/B, the wall +3% and +5%. Some of that
is real: the same 1,750 publish tasks now run INSIDE the phase's window instead of after
it, so the phase is charged for delivery it used to defer. Nothing else moved —
identical charges, identical structures, identical effect count.

**3. Do NOT compare these walls to the 19.29s column above.** That box ran the
harness-only query at 1.24ms and this one at 1.88-2.17ms, so it is ~1.5x slower today
for reasons no code in this repo controls. Same-session A/B or nothing, which is why
three runs were taken rather than one.

**4. `test_the_progress_channel_cannot_speak_from_a_synchronous_phase` still passes and
still matters.** It demonstrates the seam property in isolation — three labels from a
`def` block all land at 0.46s — and that property is why the fix had to be a yield. It
no longer describes `PerspectiveCombination`, and its docstring says so.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time

import pytest

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.explorer.skills.build_wheels import BuildWheels
from dialectical_framework.concerns.causality_estimation import CausalityEstimation
from dialectical_framework.concerns.create_nexus import CreateNexus
from dialectical_framework.concerns.perspective_combination import \
    PerspectiveCombination
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.progress import progress_scope, report_progress

_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

#: Six tensions so `DIALEXITY_PROBE_BW_K` can reach 4 without reusing content —
#: structural dedup is per-content, so a repeat would skip the work being measured.
TENSIONS = [
    ("Buy out the cofounder and take full control",
     "Keep him to retain his customer relationships"),
    ("Move the anchor accounts into my own name",
     "Leave the client relationships where they already sit"),
    ("Raise a round now while the terms are good",
     "Stay unfunded and keep every decision ours"),
    ("Publish the roadmap so customers can plan",
     "Hold it back so competitors cannot"),
    ("Promote from inside to reward the people who stayed",
     "Hire outside to get skills the team does not have"),
    ("Standardise the process so any engineer can run it",
     "Leave room for judgement where the work is unusual"),
]

INTENT = "Whether to buy out the cofounder before the next raise"

K = max(2, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_BW_K", "2"))))


class _Clock:
    """Inclusive wall and call count per label. Timing only — no behaviour change."""

    def __init__(self) -> None:
        self.totals: dict[str, list] = {}
        self.marks: dict[str, float] = {}
        self.origin = 0.0

    def add(self, label: str, seconds: float) -> None:
        row = self.totals.setdefault(label, [0, 0.0])
        row[0] += 1
        row[1] += seconds

    def mark(self, label: str) -> None:
        """Stamp the moment something finished, relative to the run's start."""
        self.marks[label] = time.monotonic() - self.origin

    def seconds(self, label: str) -> float:
        return self.totals.get(label, [0, 0.0])[1]

    def count(self, label: str) -> int:
        return self.totals.get(label, [0, 0.0])[0]


def _wrap_sync(patch, owner, name: str, label: str, clock: _Clock, *, mark=False):
    original = getattr(owner, name)

    def wrapper(*args, **kwargs):
        started = time.monotonic()
        try:
            return original(*args, **kwargs)
        finally:
            clock.add(label, time.monotonic() - started)
            if mark:
                clock.mark(label)

    patch.setattr(owner, name, wrapper)


def _wrap_async(patch, owner, name: str, label: str, clock: _Clock, *, mark=False):
    original = getattr(owner, name)

    async def wrapper(*args, **kwargs):
        started = time.monotonic()
        try:
            return await original(*args, **kwargs)
        finally:
            clock.add(label, time.monotonic() - started)
            if mark:
                clock.mark(label)

    patch.setattr(owner, name, wrapper)


#: Attributing every query to its call site walks the stack 300k times, which
#: inflates the seconds. Opt in when you want the WHO and read the timings from a
#: run with it off.
SITES = os.getenv("DIALEXITY_PROBE_BW_SITES") == "1"

#: Layers that only pass a query through; the interesting frame is above them.
_PLUMBING = ("relationship_manager.py", "database_client.py", "memgraph.py")


def _shape(query: str) -> str:
    """Collapse a query to something groupable — whitespace out, head kept."""
    flat = " ".join(str(query).split())
    return flat[:110]


def _site() -> str:
    """The nearest framework frames above the client, innermost first.

    Hand-walked rather than `traceback.extract_stack` because this runs on every
    single query and the stack is deep.
    """
    frames: list[str] = []
    frame = sys._getframe(1)
    walked = 0
    while frame is not None and walked < 30 and len(frames) < 3:
        walked += 1
        name = frame.f_code.co_filename
        if "dialectical_framework" in name:
            base = name.rsplit("/", 1)[-1]
            if base not in _PLUMBING:
                frames.append(f"{base}:{frame.f_code.co_name}")
        frame = frame.f_back
    return " < ".join(frames) or "?"


def _wrap_db(
    patch,
    db,
    clock: _Clock,
    shapes: dict[str, list],
    sites: dict[str, list] | None = None,
) -> None:
    """Time ALL client traffic, including the lazy generator's consumption.

    `execute_and_fetch` returns the connection's generator: the query runs when the
    caller iterates. Timing the call would report ~0s for every read in the tree.

    `sites` groups the same traffic by the framework frames that opened it. The site
    is taken where the query is OPENED, not where a row is pulled: by the time
    `consume()` runs, the opener's frames are gone and the generator's own frame is
    all that is left.
    """

    def charge(query, seconds: float, site: str | None = None) -> None:
        row = shapes.setdefault(_shape(query), [0, 0.0])
        row[0] += 1
        row[1] += seconds
        if sites is not None and site is not None:
            row = sites.setdefault(site, [0, 0.0])
            row[0] += 1
            row[1] += seconds

    execute = db.execute

    def execute_wrapper(*args, **kwargs):
        site = _site() if sites is not None else None
        started = time.monotonic()
        try:
            return execute(*args, **kwargs)
        finally:
            elapsed = time.monotonic() - started
            clock.add("db execute", elapsed)
            if args:
                charge(args[0], elapsed, site)

    fetch = db.execute_and_fetch

    def fetch_wrapper(*args, **kwargs):
        query = args[0] if args else kwargs.get("query", "?")
        site = _site() if sites is not None else None
        started = time.monotonic()
        inner = fetch(*args, **kwargs)
        opened = time.monotonic() - started
        clock.add("db execute_and_fetch", opened)
        charge(query, opened, site)

        def consume():
            while True:
                tick = time.monotonic()
                try:
                    item = next(inner)
                except StopIteration:
                    elapsed = time.monotonic() - tick
                    clock.add("db execute_and_fetch", elapsed)
                    charge(query, elapsed, site)
                    return
                elapsed = time.monotonic() - tick
                clock.add("db execute_and_fetch", elapsed)
                charge(query, elapsed, site)
                yield item

        return consume()

    patch.setattr(db, "execute", execute_wrapper)
    patch.setattr(db, "execute_and_fetch", fetch_wrapper)
    for name in ("save_node", "save_relationship"):
        _wrap_sync(patch, db, name, f"db {name}", clock)


async def _perspectives(count: int) -> list[str]:
    """Setup, outside the measured window."""
    hashes: list[str] = []
    for thesis, antithesis in TENSIONS[:count]:
        t = Statement(text=thesis, meaning=_T_MEANING)
        t.commit()
        a = Statement(text=antithesis, meaning=_A_MEANING)
        a.commit()
        polarity = Polarity()
        polarity.set_t(t, heuristic_similarity=1.0)
        polarity.set_a(a, heuristic_similarity=0.8)
        polarity.commit()
        expanded = await ExpandPolarity(polarity_hash=polarity.hash).resolve()
        assert expanded, "ExpandPolarity produced no Perspective"
        hashes.append(expanded[0].hash)
    return hashes


@pytest.mark.llm
@pytest.mark.asyncio
async def test_probe_where_the_off_provider_wall_goes(di_container, monkeypatch):
    print(f"\n### build_wheels at k = {K} perspectives, LLM mocked"
          f" (DIALEXITY_PROBE_BW_K to change)")

    bus = di_container.event_bus()
    await bus.connect()
    clock = _Clock()
    arrivals: list[float] = []
    ready = asyncio.Event()
    sid_holder: dict[str, str] = {}
    shapes: dict[str, list] = {}
    sites: dict[str, list] | None = {} if SITES else None

    async def collect() -> None:
        async with bus.subscribe(sid_holder["sid"]) as subscriber:
            ready.set()
            async for _ in subscriber:
                arrivals.append(time.monotonic() - clock.origin)

    try:
        case = Case()
        case.commit()
        sid_holder["sid"] = case.sid
        with scope(case.sid):
            hashes = await _perspectives(K)
            created = await CreateNexus().resolve(
                intent=INTENT, perspective_hashes=hashes
            )

            collector = asyncio.create_task(collect())
            await ready.wait()

            with monkeypatch.context() as patch:
                _wrap_db(patch, di_container.graph_db(), clock, shapes, sites)
                _wrap_sync(patch, BuildWheels, "_resolve_nexus",
                           "resolve nexus", clock)
                _wrap_sync(patch, BuildWheels, "_resolve_perspectives",
                           "resolve perspectives", clock)
                _wrap_async(patch, BuildWheels, "_resolve_auto_preset",
                            "auto preset (1 call)", clock)
                # Both are coroutines since the phase started yielding — wrapped
                # SYNC they would time the coroutine's construction (0.00s) and mark
                # the boundary before any work had run, which is how this probe first
                # reported the change.
                _wrap_async(patch, PerspectiveCombination, "resolve",
                            "COMBINATION", clock, mark=True)
                _wrap_async(patch, PerspectiveCombination, "_build_layer",
                            "  build_layer", clock)
                _wrap_sync(patch, PerspectiveCombination, "_find_or_create_cycle",
                           "    find_or_create_cycle", clock)
                _wrap_sync(patch, PerspectiveCombination, "_build_wheels_for_cycle",
                           "    build_wheels_for_cycle", clock)
                _wrap_sync(patch, PerspectiveCombination,
                           "_connect_opposite_direction_pairs",
                           "    connect_opposite_pairs", clock)
                _wrap_async(patch, CausalityEstimation, "resolve",
                            "ESTIMATION (mocked LLM)", clock, mark=True)

                clock.origin = time.monotonic()
                result = await BuildWheels(
                    nexus_hash=created.nexus.short_hash
                ).resolve()
                wall = time.monotonic() - clock.origin

            await asyncio.sleep(0.5)
            collector.cancel()
            try:
                await collector
            except asyncio.CancelledError:
                pass
    finally:
        await bus.disconnect()

    cycles, wheels = len(result.new_cycles), len(result.new_wheels)
    print(f"  built {cycles} cycle(s), {wheels} wheel(s) in {wall:.2f}s"
          f"   effects delivered {len(arrivals)}")

    print("\n  PHASE BREAKDOWN (inclusive wall; indentation shows nesting, so the"
          " rows do NOT add up)")
    order = [
        "resolve nexus", "resolve perspectives", "auto preset (1 call)",
        "COMBINATION", "  build_layer", "    find_or_create_cycle",
        "    build_wheels_for_cycle", "    connect_opposite_pairs",
        "ESTIMATION (mocked LLM)",
    ]
    for label in order:
        count, seconds = clock.totals.get(label, [0, 0.0])
        share = seconds / wall * 100 if wall else 0.0
        print(f"    {seconds:7.2f}s  {share:5.1f}%  {count:5d}x  {label}")
    accounted = clock.seconds("COMBINATION") + clock.seconds(
        "ESTIMATION (mocked LLM)"
    )
    print(f"    {wall - accounted:7.2f}s  {(wall - accounted) / wall * 100:5.1f}%"
          f"         residual outside those two phases")
    unlabelled = clock.seconds("COMBINATION") - clock.seconds("  build_layer")
    print(f"    within COMBINATION: {unlabelled:.2f}s sits outside build_layer"
          f" (which is where the two indented rows below it live)")

    print("\n  GRAPH TRAFFIC")
    for label in ("db execute", "db execute_and_fetch", "db save_node",
                  "db save_relationship"):
        count, seconds = clock.totals.get(label, [0, 0.0])
        print(f"    {seconds:7.2f}s  {count:6d}x  {label}")
    db_seconds = clock.seconds("db execute") + clock.seconds("db execute_and_fetch")
    print(f"    => {db_seconds:.2f}s of {wall:.2f}s"
          f" ({db_seconds / wall * 100:.0f}%) is client traffic."
          f" `save_node`/`save_relationship` are NESTED inside it — counts only.")

    # Which query, not just how much. A count in the hundreds of thousands is only
    # actionable once it has a call shape attached to it.
    print("\n  QUERY SHAPES, by time (first 110 chars, whitespace collapsed)")
    for shape, (count, seconds) in sorted(
        shapes.items(), key=lambda kv: -kv[1][1]
    )[:8]:
        per = seconds / count * 1000 if count else 0.0
        print(f"    {seconds:7.2f}s  {count:7d}x  {per:6.3f}ms each  {shape}")
    print(f"    ({len(shapes)} distinct shapes,"
          f" {sum(c for c, _ in shapes.values())} charges total — a charge is one"
          f" `next()`, so a query returning many rows is charged many times)")

    if sites:
        # A shape names the query; only the stack names the code to change. Reading
        # the tree by hand got the order of magnitude wrong, which is why this exists.
        print("\n  WHO OPENS THE QUERIES (innermost framework frames first)")
        for site, (count, seconds) in sorted(
            sites.items(), key=lambda kv: -kv[1][1]
        )[:12]:
            print(f"    {seconds:7.2f}s  {count:7d}x  {site}")
        print(f"    ({len(sites)} distinct sites. Timings here are INFLATED — the"
              f" stack walk runs on every query; take seconds from a run with"
              f" DIALEXITY_PROBE_BW_SITES unset.)")

    print("\n  CAN THE GRAPH CHANNEL SPEAK WHILE THE COMBINATION PHASE RUNS?")
    boundary = clock.marks.get("COMBINATION")
    if boundary is None:
        print("    combination never ran — nothing to say")
    else:
        before = [a for a in arrivals if a <= boundary]
        after = len(arrivals) - len(before)
        print(f"    PerspectiveCombination.resolve returned at {boundary:.2f}s")
        print(f"    effects delivered BEFORE it returned: {len(before)}")
        print(f"    effects delivered AFTER  it returned: {after}")
        print("    Both channels end in `loop.create_task`. While that phase was `def`"
              " all the way down this read 0 before / everything after: its events"
              " were QUEUED, not slow. It now awaits between complete find-or-create"
              " units, so BEFORE should carry most of them.")


@pytest.mark.asyncio
async def test_the_progress_channel_cannot_speak_from_a_synchronous_phase(
    di_container,
):
    """The instrumentation consequence, in isolation from any reasoning path.

    Three `report_progress` calls from inside a synchronous block. Every one is
    published with `loop.create_task`, so none can be delivered until the block
    returns control — which is why a `def` phase cannot be narrated at all, however
    many labels it declares.
    """
    bus = di_container.event_bus()
    await bus.connect()
    assert progress_module._event_bus is bus, "progress is not wired to this bus"

    case = Case()
    case.commit()
    delivered: list[tuple[float, str]] = []
    ready = asyncio.Event()
    origin = time.monotonic()

    async def collect() -> None:
        async with bus.subscribe_progress(case.sid) as subscriber:
            ready.set()
            async for event in subscriber:
                detail = event.message.detail or "FINAL"
                delivered.append((time.monotonic() - origin, detail))

    try:
        with scope(case.sid):
            collector = asyncio.create_task(collect())
            await ready.wait()

            def synchronous_phase() -> float:
                """The shape `PerspectiveCombination.resolve` had before it yielded."""
                for i in range(3):
                    report_progress(f"step {i + 1}")
                    time.sleep(0.15)
                return time.monotonic() - origin

            origin = time.monotonic()
            with progress_scope("probe", total=3):
                returned_at = synchronous_phase()
                mid_phase = list(delivered)

            await asyncio.sleep(0.3)
            collector.cancel()
            try:
                await collector
            except asyncio.CancelledError:
                pass
    finally:
        await bus.disconnect()

    print("\n### Can a synchronous phase narrate itself?")
    print(f"    the block ran {returned_at:.2f}s and published 3 steps")
    print(f"    delivered while it was still running: {len(mid_phase)}")
    for stamp, detail in delivered:
        print(f"      {stamp:6.2f}s  {detail}")

    assert not mid_phase, (
        "a synchronous phase delivered progress mid-flight, which would mean"
        " `_publish` no longer schedules with `loop.create_task` — re-read the"
        " conclusion this probe draws for `build_wheels` before trusting it"
    )
    assert len(delivered) >= 3, "the steps were never delivered at all"
    assert all(stamp >= returned_at for stamp, _ in delivered), (
        "every event must arrive after the block returned control to the loop"
    )
