"""Probe: during explore's wall clock, what could the person SEE, and when?

WHY
===
`probe_explore_cost.py` settled that `explore`'s ~104s (1 PP) is real work: 85% of
the wall clock has a call in flight, about 11 sequential stages deep, already
compressed 4.15x by the existing fan-out. So there is no missing `gather`, and the
best available cost win — batching the audit, 40% of provider time — would land
`explore` around 70s. **The floor is structural, so optimisation cannot make this
snappy.** What can is not making the person WAIT on it: if the wheel visibly forms
while it is being built, 70s of construction and 104s of construction feel far more
alike than either feels like 104s of nothing.

The framework already has the machinery. `ExecutionReport.node_created` /
`node_committed` / `relationship_created` publish an `Effect` to `GraphEventBus`
through `_emit`, fire-and-forget on the running loop, at the moment the mutation is
recorded — no batching anywhere, and `merge()` deliberately does NOT re-emit, so
every effect reaches the bus exactly once at its own moment. A host subscribes per
`sid` and gets a live stream.

So the question is not "is there a stream?" but **"is the stream any use during the
wait?"** — and that is not answerable by reading the code, because it depends on
where the emissions fall relative to the gathers. CLAUDE.md's own concurrency rule
("gather the LLM work, collect results, THEN write graph nodes sequentially") means
emissions cluster at graph-write time, after each stage's LLM work. Whether that
yields ~11 usable progress bursts or one burst at the end is an empirical question.

WHAT IT MEASURES, AND WHICH NUMBER IS THE UX ONE
================================================
It subscribes to the bus for the duration of the tool and timestamps every effect
relative to the tool's start. From that:

- **Time to first event** — how long the person stares at nothing before ANY sign
  of life. This is the "snappy" number.
- **Largest silent gap** — the longest stretch with no event at all, wherever it
  falls. **This is the number that decides the question**, and it is not the same as
  the first one: a stream that starts in 2s and then goes quiet for 60s is a
  progress bar that lies, which is worse than no progress bar.
- **Share of the wall clock spent in silence** (gaps over a legibility threshold),
  because a person's sense of "hung" tracks total dead air, not the count of events.
- **What the events say.** An `Effect` carries `NodeRef.label` (the node class) plus
  `patch["text"]` and `meta`, so a host can render "Ac+ transition: <text>" rather
  than "something happened". A stream of legible nouns is progressive disclosure; a
  stream of `Rationale` hashes is a spinner with extra steps.

The call census runs alongside so a silence can be priced in calls, not just in
seconds: "38s of dead air spanning 12 audit calls" names the stage to instrument,
which a bare duration does not.

READING IT HONESTLY
===================
- **This measures AVAILABILITY, not the product.** A perfect result here means a
  host COULD show live progress; it does not mean any host does, and it says nothing
  about whether the rendering would be legible to a person rather than to me. The
  framework-side question is the only one this probe can settle.
- **A burst is not a stage.** Effects cluster at graph-write time, so burst count is
  a lower bound on pipeline stages — `depth` from the census is the better estimate,
  and the two should be read together rather than reconciled.
- 1 PP is the FLOOR, as in the cost probe. Widening N adds parallel branches, which
  makes the stream denser without lengthening the per-Transformation chain — so a
  gap measured here is a WORST case for dead air only in the sense that more work
  fills it in; the longest single gap should be read as roughly N-invariant.
- The bus is connected explicitly here. `GraphEventBus.publish` is a no-op while
  disconnected, so a probe that forgot `connect()` would record zero events and read
  as "no progress available at all" — the most alarming possible conclusion, from a
  one-line setup bug. The run asserts it saw something for exactly that reason.

    poetry run pytest tests/e2e/probe_explore_progress.py -s --real-llm

`DIALEXITY_PROBE_EXPLORE_PP=2` widens to two perspectives.

RESULT, 2026-08-27 — the stream is instant, then there is ONE 45.6s hole
=======================================================================
Weak tier, 1 PP, 6 Transformations, 97.5s wall, 150 effects, 50 calls::

    TIME TO FIRST EFFECT  0.0s   (nothing is waited for before the first sign of life)
    LARGEST SILENT GAP   45.6s   at 1.5s-47.1s, before Transformation
    dead air over 3s     92.7s   across 8 gaps = 95% of the wall

      0.0s    6 effects   Nexus, Perspective, Rationale, CC/DV estimations
      1.5s    8 effects   Cycle, 2x Transition, 2x Wheel
     47.1s  120 effects   12x Transformation, 36x Transition, 36x Rationale   <- all at once
     54-91s  ~11 effects  Rationale, trickling (the audits)
     97.5s    4 effects   2x Statement, 2x Synthesis

**Progressive disclosure is available, and the emission POINTS are in the wrong
place.** The bus works, the subscription works, and the nouns on the stream are
exactly what a person would want to watch appear — `Nexus`, `Cycle`, `Wheel`,
`Transformation`, `Transition`, `Synthesis`. Structure lands in the first 1.5s, so
"here is the shape of your situation" is free. Then **the entire Transformation
phase is silent: 45.6s covering 33 of the 50 provider calls** (6 each of
`ActionCandidateDto`, `AcMinusCompletionDto`, `ReSideCompletionDto`, `HsScoringDto`,
`CategoryReframingDto`), after which 120 effects fire in a single burst.

The cause is structural and it is CLAUDE.md's own concurrency rule working as
designed: gather the LLM work, then write graph nodes sequentially after the gather.
Effects are emitted at graph-write time, so **the emissions cannot happen while the
work is happening** — by the time a `Transformation` node exists to report, its four
generation calls and two audits are already paid for. Note the audit phase (54-91s)
DOES trickle, because each audit writes its Rationale as it finishes; that stretch is
the shape the Transformation phase should have.

So the gap is not a missing subscription and not a missing `gather`. It is that the
bus carries only graph MUTATIONS, and during those 45.6s there is nothing to mutate
yet — the honest signal there is "4 of 6 transformations generated", which is
progress and not a mutation. Closing it means a progress signal that a gathered
child may emit safely (publishing to the bus is not a graph write, so the
GQLAlchemy constraint does not apply), which is a change to the contract host apps
consume and therefore not a change to make silently.

SECOND RUN, same day — the barrier was NOT the cause, and this probe proved it
============================================================================
The write loop was changed from `asyncio.gather` + a post-barrier loop to a
completion-order drain (`utils/async_drain.py`), on the reasoning that each
Transformation would then land as its own work finished and the burst would spread
across the 43s. Re-measured::

    waited 80.9s   effects 150   calls 48
    TIME TO FIRST EFFECT  0.0s
    LARGEST SILENT GAP   42.9s   (was 45.6s)
    burst at 44.4-46.4s, 120 effects   (was one instant)

**The prediction was wrong.** The gap moved 45.6s → 42.9s and the burst spread over
2.0s instead of 0 — nothing a person would notice. The reason is visible in the cost
probe's own per-caller table and I should have read it first: the six tetrad tasks are
six *identical* 4-call chains started at the same moment, so they complete at the same
moment. **Completion-order draining only pays on heterogeneous work**, and this work
is uniform by construction. The barrier was real and was not what the person was
waiting for.

(The 97.5s → 80.9s wall is run-to-run variance — 48 calls against 50 — not an effect
of the change. Do not read it as one.)

This is what the probe is for. The drain was kept for the case it does serve (a
retrying tetrad no longer holds back its five siblings' writes — tail, not median),
and the conclusion above stands unchanged: the 43s belongs to work that produces no
node until it is finished, so only a progress signal emitted between
`_generate_tetrad`'s four sequential calls can fill it.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.tools.explore import \
    run_exploration_detailed
from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census

#: Same scenario as `probe_explore_cost.py`, so the two runs are comparable and a
#: gap here can be priced against that run's stage structure.
_T_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion"
_A_MEANING = "dx://taxonomy/System(General.v1)/Viability/Integrity/Separation"

TENSIONS = [
    (
        "Buy out the cofounder and take full control",
        "Keep him to retain his customer relationships",
    ),
    (
        "Move the anchor accounts into my own name",
        "Leave the client relationships where they already sit",
    ),
]

INTENT = "Whether to buy out the cofounder before the next raise"

PP_COUNT = max(1, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_EXPLORE_PP", "1"))))

#: Two events closer together than this are one burst for display purposes. Chosen
#: as a rendering threshold, not a perceptual one: it keeps a 40-node graph write
#: from printing 40 lines, and no headline number depends on it.
_BURST_GAP_S = 1.0

#: A gap longer than this is dead air a person would notice. Not a tuned constant —
#: it is the rough floor of "did it freeze?" in UI literature, and the report prints
#: the full gap list anyway so a different threshold can be applied by eye.
_NOTICEABLE_GAP_S = 3.0


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(3600)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_explore_progress_stream(di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(f"perspectives woven: {PP_COUNT}")

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    bus = di_container.event_bus()
    # Without this every `publish` is a silent no-op — see the docstring's last
    # bullet. The container wires the bus into `ExecutionReport` at setup; it does
    # not connect it, because connecting is the host's lifecycle call.
    await bus.connect()
    assert ExecutionReport._event_bus is bus, (
        "the report class is not publishing to this bus, so an empty stream below"
        " would say nothing about the framework"
    )

    case = Case()
    case.commit()

    #: (seconds since tool start, effect) — appended by the collector task.
    seen: list[tuple[float, object]] = []

    try:
        with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
            # Setup outside the measurement, as in the cost probe.
            perspective_hashes = []
            for thesis, antithesis in TENSIONS[:PP_COUNT]:
                t = Statement(text=thesis, meaning=_T_MEANING)
                t.commit()
                a = Statement(text=antithesis, meaning=_A_MEANING)
                a.commit()
                polarity = Polarity()
                polarity.set_t(t, heuristic_similarity=1.0)
                polarity.set_a(a, heuristic_similarity=0.8)
                polarity.commit()
                pps = await ExpandPolarity(polarity_hash=polarity.hash).resolve()
                assert pps, "ExpandPolarity produced no Perspective — nothing to explore"
                perspective_hashes.append(pps[0].hash)

            started = time.monotonic()

            async def _collect() -> None:
                async with bus.subscribe(case.sid) as subscriber:
                    ready.set()
                    async for event in subscriber:
                        seen.append((time.monotonic() - started, event.message.effect))

            ready = asyncio.Event()
            collector = asyncio.create_task(_collect())
            # Subscribe BEFORE the work: `broadcaster` registers the queue inside
            # the context manager, so a task merely created is not yet listening
            # and the first events would be dropped — which would corrupt the one
            # number this probe exists to measure.
            await ready.wait()

            with call_census() as census:
                report, transformation_hashes = await run_exploration_detailed(
                    perspective_hashes=perspective_hashes,
                    intent=INTENT,
                    nexus_hash=None,
                )
            waited = time.monotonic() - started

            # `_emit` schedules publishes with `loop.create_task`, so effects
            # recorded in the final instant have not necessarily been delivered.
            await asyncio.sleep(0.5)
            collector.cancel()
            try:
                await collector
            except asyncio.CancelledError:
                pass
    finally:
        await bus.disconnect()

    print(
        f"\n  waited {waited:8.1f}s"
        f"   effects {len(seen):4d}"
        f"   calls {census.count:4d}"
        f"   depth ~{census.depth:4.1f} stages"
    )
    print(f"  transformations built: {len(set(transformation_hashes))}")

    if not seen:
        print(
            "\n  ZERO effects reached the bus. Either the tool records no mutations"
            " (it does — `_create_transformation` calls `node_created`) or this probe"
            " failed to subscribe. Fix the probe before concluding anything."
        )
    else:
        # Gaps, including the leading one (start -> first event) and the trailing
        # one (last event -> return). Both are dead air the person sits through,
        # and the leading one is the "snappy" number.
        stamps = [t for t, _ in seen]
        gaps: list[tuple[float, float, str]] = [(0.0, stamps[0], "before the first effect")]
        for i in range(1, len(stamps)):
            label = seen[i][1].node.label if seen[i][1].node else "?"
            gaps.append((stamps[i - 1], stamps[i], f"before {label}"))
        gaps.append((stamps[-1], waited, "after the last effect"))

        first = stamps[0]
        widest = max(gaps, key=lambda g: g[1] - g[0])
        noticeable = [g for g in gaps if g[1] - g[0] >= _NOTICEABLE_GAP_S]
        dead_air = sum(g[1] - g[0] for g in noticeable)

        print(
            f"\n  TIME TO FIRST EFFECT {first:.1f}s"
            f"  ({first / waited:.0%} of the wall spent before any sign of life)"
        )
        print(
            f"  LARGEST SILENT GAP  {widest[1] - widest[0]:.1f}s"
            f"  at {widest[0]:.1f}s–{widest[1]:.1f}s, {widest[2]}"
        )
        print(
            f"  dead air over {_NOTICEABLE_GAP_S:.0f}s: {dead_air:.1f}s across"
            f" {len(noticeable)} gap(s) = {dead_air / waited:.0%} of the wall"
        )

        # Priced in calls, because "38s of silence" and "38s of silence spanning 12
        # audit calls" point at different work. No clock correction is needed or
        # wanted: `CallRecord.started` and these stamps both come from
        # `time.monotonic()`, so subtracting the same `started` puts them on one
        # axis. An earlier draft "corrected" between them and invented an offset.
        during = [
            c
            for c in census.calls
            if widest[0] <= (c.started - started) <= widest[1]
        ]
        if during:
            by_dto: dict[str, int] = {}
            for call in during:
                by_dto[call.label.split(" via ")[0]] = by_dto.get(call.label.split(" via ")[0], 0) + 1
            named = ", ".join(f"{n}x {dto}" for dto, n in sorted(by_dto.items(), key=lambda kv: -kv[1]))
            print(
                f"  the widest gap covers {len(during)} of the {census.count} provider"
                f" calls: {named}"
            )

        print("\n  what the person would see, burst by burst:")
        burst_start = stamps[0]
        burst: list[object] = [seen[0][1]]
        for i in range(1, len(seen)):
            if stamps[i] - stamps[i - 1] > _BURST_GAP_S:
                _print_burst(burst_start, stamps[i - 1], burst)
                burst_start, burst = stamps[i], [seen[i][1]]
            else:
                burst.append(seen[i][1])
        _print_burst(burst_start, stamps[-1], burst)

        legible = {e.node.label for _, e in seen if e.node}
        print(f"\n  node kinds on the stream: {', '.join(sorted(legible))}")

    # Coherence only, never a duration: this probe measures, it does not gate.
    assert seen, (
        "no effect reached the bus during a tool that demonstrably records node"
        " creations — the subscription or the connect is wrong, and the alarming"
        " reading ('no live progress exists') would be an artefact of this file"
    )
    assert all(0.0 <= t <= waited + 1.0 for t, _ in seen), (
        "an effect is timestamped outside the tool's own wall clock"
    )


def _print_burst(start: float, end: float, effects: list) -> None:
    kinds: dict[str, int] = {}
    for effect in effects:
        label = effect.node.label if getattr(effect, "node", None) else effect.effect_type
        kinds[label] = kinds.get(label, 0) + 1
    shape = ", ".join(f"{n}x {label}" for label, n in sorted(kinds.items()))
    span = f"{start:6.1f}s" if end - start < 0.1 else f"{start:6.1f}-{end:.1f}s"
    print(f"    {span:>16}  {len(effects):3d} effects  {shape}")
