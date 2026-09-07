"""Probe: during a LIVE ingest, what could the person see, and when?

WHY THIS RUN EXISTS AT ALL
==========================
`ingest`'s progress instrumentation has only ever run under mock brain
(`tests/test_ingest_progress.py`), and a mock brain cannot exercise the three
things that decide whether this instrumentation is honest on the real path:

1. **Conditional steps.** `SurfaceTheses` declares its dedup step only `if vocab
   and extracted_components`, and its extraction step once PER ATTEMPT inside a
   loop that exits as soon as it has enough candidates. Under a mock the branch
   taken is whatever the fixture makes it; live, the branch depends on what the
   model returns. A step declared on a branch that then does not run is a
   **phantom** — the closing event reports what COMPLETED, so a phantom is
   indistinguishable to a host from a step that FAILED (`utils/progress.py`).
2. **A denominator that grows for real.** `expect_progress` is additive and the
   window count, candidate count and perspective count are all discovered as the
   work proceeds. Only a live run produces the real trajectory, and the caveat that
   a host caching its first denominator renders a bar going backwards needs a
   number on this path, not just on `explore`'s.
3. **Retries.** A parse retry re-runs a call inside an already-declared step, and
   the zero-candidate re-sweep re-declares every window deliberately. Neither
   shape exists under a mock that always parses.

WHAT IT MEASURES
================
Both channels for the duration of ONE `ingest` call, timestamped against the tool's
start, exactly as `probe_explore_progress.py` does for `explore` — so the two are
directly comparable and the same three headline numbers mean the same thing:

- **time to first sign of life** (the "snappy" number),
- **largest silent gap**, graph-only against graph+progress (the number that decides
  the question: a stream that starts fast and then goes quiet for a minute is a
  progress bar that lies),
- **share of the wall spent in dead air.**

Plus three that are specific to this path:

- **Phantom steps** — `total - done` on the closing event, with the label sequence
  printed so a shortfall can be attributed to a stage rather than just noted.
- **The denominator trajectory** — every distinct `total`, in order, and the worst
  backwards jump in `done/total` a host would render.
- **A content-leak tripwire.** The material on this path is whole documents. Every
  label is supposed to carry indices and counts only ("Reading section 3 of 4"),
  which is a rule about code that nothing enforces at runtime. This run asserts no
  label contains any substantial run of the source and that no label is long enough
  to be quoting anything.

READING IT HONESTLY
===================
- **Availability, not product.** A good result means a host COULD render live
  progress. It says nothing about whether any host does, or whether the wording
  would read well to a person rather than to me.
- **A gap is not necessarily a defect.** `SourceDigest`'s reduce and
  `StatementDeduplication` are single calls; a scope can announce them but cannot
  subdivide them, so a gap the width of one call is the floor here — same
  conclusion `probe_explore_progress.py` reached for `SynthesisGeneration`.
- **The yield is stochastic and the wall clock is not a result.** The sibling cost
  probe measured 196 calls in one run and 95 in the next on the identical document,
  because `find_polarities` proposed 50 pairs and then 5. So event COUNTS here swing
  the same way; the gap and dead-air figures are the stable readings.
- **Both channels are connected explicitly.** `GraphEventBus.publish` is a no-op
  while disconnected and `progress._event_bus` is wired at DI setup, so a probe that
  forgot either would record nothing and read as "no progress exists" — the most
  alarming possible conclusion, from a one-line setup bug. Both are asserted before
  the work starts.
- The document is the SAME generator as `probe_ingest_cost.py`, imported rather than
  copied, so a silence here can be priced against that probe's stage table.

    poetry run pytest tests/e2e/probe_ingest_progress.py -s --real-llm

`DIALEXITY_PROBE_INGEST_KB` sets the source size (default 120 KB = 4 windows, as in
the cost probe). `-o log_cli=true --log-cli-level=WARNING` to see retry warnings,
which this probe PASSES through.

RESULT, 2026-09-07, haiku-4.5 — the sweep's denominator works, and three holes remain
=====================================================================================
**120 KB / 4 windows, 99.7s, 127 calls at 5.66x, 24 progress events:**

    time to first event        0.3s
    largest silent gap        52.3s graph-only  ->  14.4s with progress
    the 52.3s graph-silent stretch carries 11 progress events
    dead air over 3s          90.8s = 91% of the wall  (UNCHANGED by the channel)
    denominator               2 -> 7 -> 8 -> 12 -> ... -> 23
    phantom steps             none, closed 23/23
    leak check                clean across 24 labels

**The headline claim holds: on the swept path a person gets a real denominator, in
advance, twice.** "Reading part 3 of 4" (digest) at 0.3s and "Reading section 3 of 4
for tensions" at 30.1s are the two places ingestion knows its own size, and both
report it. The single worst stretch — 52.3s, over half the wall, in which a
graph-only host sees NOTHING between the Input node and the first Statement — now
carries 11 events. That is the change, and it is a 3.6x cut to the worst hole.

**Read the dead-air row as the honest limit.** Total dead air is 90.8s either way:
the channel shortens the worst gap but the stream is only ~1 event per 3-14s, so
almost every gap is still over the 3s threshold. Progressive disclosure here means
"never wonder if it froze", NOT "continuous motion".

**Three holes remain, all the same shape — one label before a gathered fan-out:**

1. **14.4s at 52.5-66.9s**, the widest that survives: `find_polarities` announces
   "Looking for what genuinely pushes back" and then runs 12 gathered
   `AntithesisEvaluationDto` calls (68.6s summed) with nothing to say.
2. **10.7s at 78.8-89.5s**: five `expand_polarities` steps all report at 78.8s
   because they are announced at the gather, then five ~11s `TetradDto` calls run
   silent. Reporting inside each task would not help — they all start together —
   so this one needs per-call subdivision like `TransformationGeneration` has.
3. **The single-window path bundles three phases under one label** (1 KB run:
   12.2s, and the widest progress gap of that run). `_extraction_loop` reports
   "Reading the material for tensions" once and then runs step 1, the step-2 gate
   and classification under it. The SWEEP path already splits the last of those out
   as "Placing N candidate tension(s)"; the loop path has no equivalent. This is the
   common chat case — a person pasting a paragraph — so it matters more than its
   size suggests.

**A 1 KB source ran 651s once and 45.5s the next time**, identical call structure and
identical 16-event progress stream both times (50 calls at 1.24x against 70 at
6.48x; mean call 16.1s against 4.1s, zero retries either way). Nothing in the
framework changed between them, so it is provider-side. Two lessons: **do not quote
a single wall clock from this probe**, and — the UX one — **a labelled step that
takes 605s is still 605s of one unchanging line.** Progress labels defend against
not knowing; they do not defend against slow.

**The digest is skipped entirely below `DIGEST_THRESHOLD`** (the 1 KB runs show no
`DigestDto` call), so "Building a working understanding of it" fires and completes
instantly on short material. Correct behaviour — compact content is its own digest —
but worth knowing before reading that label as evidence a digest was built.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model
# The document generator and its size knob, imported so the two ingest probes
# cannot drift apart. Private by name, shared on purpose: copying it would make a
# silence here unpriceable against that probe's per-stage token table.
from e2e.probe_ingest_cost import SOURCE_KB, _document

from dialectical_framework.agents.advisor.tools import ingest as ingest_mod
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.chunking import CHUNK_SIZE, chunk_text
from dialectical_framework.utils.retry_accounting import retry_account

INTENT = "Find the structural trade-offs this material keeps returning to"

#: Two events closer together than this are one burst for display. A rendering
#: threshold, not a perceptual one; no headline number depends on it.
_BURST_GAP_S = 1.0

#: A gap longer than this is dead air a person would notice. Not tuned — the rough
#: floor of "did it freeze?" — and the full gap list is printed anyway.
_NOTICEABLE_GAP_S = 3.0

#: Any run of source text this long appearing in a label is a leak. Long enough
#: that ordinary English overlap ("the material", "for tensions") cannot trip it,
#: short enough to catch a truncated quote.
_LEAK_WINDOW = 40

#: A label is a sentence, not a payload. The longest shipped label on this path is
#: ~50 chars; the cap is deliberately loose so it fails on quoting, not on wording.
_MAX_LABEL_CHARS = 160


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(7200)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_ingest_progress_stream(di_container):
    document = _document(SOURCE_KB)
    windows = chunk_text(document)

    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(
        f"source: {len(document):,} chars ({SOURCE_KB} KB)"
        f" -> {len(windows)} window(s) of at most {CHUNK_SIZE:,} chars"
    )
    if len(windows) == 1:
        print(
            "  NOTE: ONE window, so the sweep does not fire and the per-window"
            " progress steps — the ones with a denominator known in advance — are"
            " absent. Raise DIALEXITY_PROBE_INGEST_KB to exercise them."
        )
    if os.getenv("DIALEXITY_MAX_CONCURRENT_LLM_CALLS"):
        print(
            "  NOTE: the concurrency semaphore is SET, so silence below includes"
            " queueing. The sweep reports INSIDE its own semaphore, so its events"
            " still mean 'being read' rather than 'queued'."
        )

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    bus = di_container.event_bus()
    await bus.connect()
    assert ExecutionReport._event_bus is bus, (
        "the report class is not publishing to this bus, so an empty graph stream"
        " below would say nothing about the framework"
    )
    assert progress_module._event_bus is bus, (
        "progress is not wired to this bus — see `utils/progress.set_event_bus`;"
        " without this an empty progress stream would read as 'the emission points"
        " never fire', which is the wrong conclusion from a setup bug"
    )

    case = Case()
    case.commit()

    #: (seconds since tool start, Effect) — the channel a host already consumes.
    seen: list[tuple[float, object]] = []
    #: (seconds since tool start, ProgressEvent) — the channel under test. Kept
    #: separate because the claim is about what the two look like APART: an
    #: unchanged graph stream is the compatibility promise.
    progress: list[tuple[float, object]] = []

    try:
        with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
            started = time.monotonic()

            async def _collect() -> None:
                async with bus.subscribe(case.sid) as subscriber:
                    ready.set()
                    async for event in subscriber:
                        seen.append((time.monotonic() - started, event.message.effect))

            async def _collect_progress() -> None:
                async with bus.subscribe_progress(case.sid) as subscriber:
                    progress_ready.set()
                    async for event in subscriber:
                        progress.append((time.monotonic() - started, event.message))

            ready = asyncio.Event()
            progress_ready = asyncio.Event()
            collector = asyncio.create_task(_collect())
            progress_collector = asyncio.create_task(_collect_progress())
            # Subscribe BEFORE the work: `broadcaster` registers the queue inside
            # the context manager, so a task merely created is not yet listening and
            # the first events would be dropped — which is the one number this
            # probe cannot afford to get wrong.
            await ready.wait()
            await progress_ready.wait()

            with call_census() as census, retry_account() as account:
                await ingest_mod.ingest.fn(text=document, intent=INTENT)
            waited = time.monotonic() - started

            # Both publishes are `loop.create_task`, so events recorded in the final
            # instant have not necessarily been delivered yet.
            await asyncio.sleep(0.5)
            collector.cancel()
            progress_collector.cancel()
            for task in (collector, progress_collector):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    finally:
        await bus.disconnect()

    working = max(0.0, waited - account.wasted_s)
    print(
        f"\n  waited {waited:8.1f}s"
        f"   working {working:8.1f}s"
        f"   slept {account.sleep_s:6.1f}s"
        f"   retries {account.count} {dict(account.kinds) or ''}"
    )
    print(
        f"  calls {census.count:4d}"
        f"   in-flight {census.busy_s:8.1f}s"
        f"   parallelism {census.parallelism:5.2f}x"
        f"   depth ~{census.depth:5.1f} stages"
    )
    print(f"  effects {len(seen)}   progress events {len(progress)}")

    if not seen:
        print(
            "\n  ZERO effects reached the bus, from a tool that demonstrably writes"
            " an Input node. Fix the probe before concluding anything."
        )

    graph_widest = _report_channel("GRAPH", seen, waited, census, started)
    _report_call_timeline(census, started, waited)
    _report_bursts(seen)
    _report_progress_channel(progress, seen, waited, graph_widest)
    _report_phantoms(progress)
    _report_denominator(progress)
    _report_leaks(progress, document)

    # Coherence only, never a duration: this probe measures, it does not gate.
    assert seen, (
        "no effect reached the bus during a tool that records an Input node — the"
        " subscription or the connect is wrong, and the alarming reading would be"
        " an artefact of this file"
    )
    assert progress, (
        "the progress channel delivered nothing during a tool that opens a scope at"
        " its own entry point — either the scope was installed after the gathered"
        " tasks were created (they inherit a context without it) or"
        " `progress.set_event_bus` was never wired"
    )
    assert all(0.0 <= t <= waited + 1.0 for t, _ in progress), (
        "a progress event is timestamped outside the tool's own wall clock"
    )
    assert all(e.total >= e.done for _, e in progress), (
        "a progress event claims more done than expected — a denominator is being"
        " declared after the steps it covers, which is the one ordering rule"
        " `expect_progress` exists to make easy to follow"
    )
    keys = {e.key for _, e in progress}
    assert len(keys) == 1, (
        f"one ingest call published under {len(keys)} keys ({keys}) — the tool-level"
        " scope is being re-entered somewhere below it, which would let a host"
        " render two indicators for one wait"
    )
    finals = [e for _, e in progress if e.final]
    assert len(finals) == 1, (
        f"expected exactly one closing event, saw {len(finals)} — a second `final`"
        " tells a host to clear an indicator it has already cleared, and none"
        " leaves it spinning forever"
    )
    assert finals[0] is progress[-1][1], (
        "the closing event is not the LAST event: a step arrived after the scope"
        " closed, which `_closed` is supposed to swallow"
    )


def _report_channel(name, events, waited, census, started) -> tuple[float, float, str]:
    """Time-to-first, widest gap and dead air for one channel. Returns the gap."""
    if not events:
        return (0.0, 0.0, "no events")

    stamps = [t for t, _ in events]
    gaps: list[tuple[float, float, str]] = [(0.0, stamps[0], "before the first event")]
    for i in range(1, len(stamps)):
        node = getattr(events[i][1], "node", None)
        label = node.label if node else "?"
        gaps.append((stamps[i - 1], stamps[i], f"before {label}"))
    gaps.append((stamps[-1], waited, "after the last event"))

    widest = max(gaps, key=lambda g: g[1] - g[0])
    noticeable = [g for g in gaps if g[1] - g[0] >= _NOTICEABLE_GAP_S]
    dead_air = sum(g[1] - g[0] for g in noticeable)

    print(
        f"\n  {name} CHANNEL"
        f"\n    time to first event {stamps[0]:6.1f}s"
        f"  ({stamps[0] / waited:.0%} of the wall before any sign of life)"
        f"\n    LARGEST SILENT GAP  {widest[1] - widest[0]:6.1f}s"
        f"  at {widest[0]:.1f}s-{widest[1]:.1f}s, {widest[2]}"
        f"\n    dead air over {_NOTICEABLE_GAP_S:.0f}s  {dead_air:6.1f}s across"
        f" {len(noticeable)} gap(s) = {dead_air / waited:.0%} of the wall"
    )

    # Price the silence in calls. No clock correction: `CallRecord.started` and
    # these stamps both come from `time.monotonic()`, so subtracting the same
    # `started` puts them on one axis (an earlier probe "corrected" between them
    # and invented an offset).
    during = [c for c in census.calls if widest[0] <= (c.started - started) <= widest[1]]
    if during:
        by_dto: dict[str, int] = {}
        for call in during:
            dto = call.format_name or "no format"
            by_dto[dto] = by_dto.get(dto, 0) + 1
        named = ", ".join(
            f"{n}x {dto}" for dto, n in sorted(by_dto.items(), key=lambda kv: -kv[1])
        )
        print(
            f"    the widest gap covers {len(during)} of the {census.count} provider"
            f" calls: {named}"
        )
    return widest


def _report_call_timeline(census, started, waited) -> None:
    """Which call filled the silence, not just how many there were.

    Added after the first run of this probe, which priced a 615s graph-silent
    stretch at "13 of 50 provider calls" and left the time unattributable: a count
    cannot distinguish thirteen slow calls from twelve fast ones behind a single
    600s outlier, and those two readings point at completely different work. The
    per-DTO table is the same shape as `probe_ingest_cost.py`'s, restricted to
    seconds because this probe is about the wait rather than the bill.
    """
    if not census.calls:
        return

    by_dto: dict[str, tuple[int, float]] = {}
    for call in census.calls:
        dto = call.format_name or "no format"
        count, seconds = by_dto.get(dto, (0, 0.0))
        by_dto[dto] = (count + 1, seconds + (call.seconds or 0.0))

    print("\n  provider seconds by DTO (sum, so it exceeds the wall where gathered):")
    for dto, (count, seconds) in sorted(by_dto.items(), key=lambda kv: -kv[1][1]):
        print(
            f"    {seconds:8.1f}s  {count:3d} call(s)  mean {seconds / count:6.1f}s"
            f"   {dto}"
        )

    slowest = sorted(census.calls, key=lambda c: -(c.seconds or 0.0))[:8]
    print("\n  slowest calls, with the offset they STARTED at:")
    for call in slowest:
        offset = call.started - started
        print(
            f"    {offset:7.1f}s -> {offset + (call.seconds or 0.0):7.1f}s"
            f"  {call.seconds or 0.0:7.1f}s  {call.format_name or 'no format'}"
            f"  [{call.caller or '?'}]"
        )

    # The one-line verdict, because a single dominating call is a different defect
    # from a long chain and the distinction is easy to lose in the tables above.
    top = slowest[0]
    share = (top.seconds or 0.0) / waited if waited else 0.0
    if share >= 0.25:
        print(
            f"\n    ONE CALL IS {share:.0%} OF THE WALL"
            f" ({top.seconds or 0.0:.1f}s, {top.format_name or 'no format'})."
            " Read the depth figure with that in mind: this is not a long chain,"
            " it is one call nothing can overlap."
        )


def _report_bursts(events) -> None:
    if not events:
        return
    stamps = [t for t, _ in events]
    print("\n  what a graph-only host would see, burst by burst:")
    burst_start = stamps[0]
    burst: list[object] = [events[0][1]]
    for i in range(1, len(events)):
        if stamps[i] - stamps[i - 1] > _BURST_GAP_S:
            _print_burst(burst_start, stamps[i - 1], burst)
            burst_start, burst = stamps[i], [events[i][1]]
        else:
            burst.append(events[i][1])
    _print_burst(burst_start, stamps[-1], burst)
    kinds = {e.node.label for _, e in events if getattr(e, "node", None)}
    print(f"    node kinds on the stream: {', '.join(sorted(kinds))}")


def _print_burst(start: float, end: float, effects: list) -> None:
    kinds: dict[str, int] = {}
    for effect in effects:
        node = getattr(effect, "node", None)
        label = node.label if node else effect.effect_type
        kinds[label] = kinds.get(label, 0) + 1
    shape = ", ".join(f"{n}x {label}" for label, n in sorted(kinds.items()))
    span = f"{start:6.1f}s" if end - start < 0.1 else f"{start:6.1f}-{end:.1f}s"
    print(f"    {span:>16}  {len(effects):3d} effects  {shape}")


def _report_progress_channel(progress, seen, waited, graph_widest) -> None:
    """The headline: dead air as experienced by a host subscribed to BOTH."""
    if not progress:
        print("\n  PROGRESS CHANNEL — nothing delivered. See the assertion below.")
        return

    merged = sorted([t for t, _ in seen] + [t for t, _ in progress])
    merged_gaps = (
        [(0.0, merged[0])]
        + [(merged[i - 1], merged[i]) for i in range(1, len(merged))]
        + [(merged[-1], waited)]
    )
    widest = max(merged_gaps, key=lambda g: g[1] - g[0])
    dead = sum(g[1] - g[0] for g in merged_gaps if g[1] - g[0] >= _NOTICEABLE_GAP_S)
    graph_gap = graph_widest[1] - graph_widest[0]

    print(
        f"\n  WITH THE PROGRESS CHANNEL ({len(progress)} events)"
        f"\n    time to first event {merged[0]:6.1f}s"
        f"\n    largest silent gap  {widest[1] - widest[0]:6.1f}s"
        f"  at {widest[0]:.1f}s-{widest[1]:.1f}s"
        f"   (graph-only: {graph_gap:.1f}s)"
        f"\n    dead air over {_NOTICEABLE_GAP_S:.0f}s  {dead:6.1f}s"
        f" = {dead / waited:.0%} of the wall"
    )
    inside = [t for t, _ in progress if graph_widest[0] <= t <= graph_widest[1]]
    print(
        f"    the {graph_gap:.1f}s graph-silent stretch carries {len(inside)}"
        f" progress event(s)"
    )

    print("\n  the whole progress stream, as a person would read it:")
    for t, event in progress:
        final = "  FINAL" if event.final else ""
        print(f"    {t:6.1f}s  {event.done:3d}/{event.total:<3d} {event.detail}{final}")


def _report_phantoms(progress) -> None:
    """Declared steps that never ran, which read to a host exactly like failures."""
    if not progress:
        return
    closing = progress[-1][1]
    shortfall = closing.total - closing.done
    if shortfall == 0:
        print(
            f"\n  PHANTOM STEPS: none — closed at {closing.done}/{closing.total}."
            " Every step declared on this run's branches actually ran, which is the"
            " condition for a host to read a shortfall as a real failure."
        )
        return
    print(
        f"\n  PHANTOM STEPS: closed at {closing.done}/{closing.total}, so"
        f" {shortfall} declared step(s) never reported."
        "\n    This is NOT necessarily a defect — a step that failed looks the same"
        " — but on a run with no errors it means a denominator was declared on a"
        " branch that then did not run, and a host would render it as work lost."
        "\n    Attribute it by reading the stream above: the stage whose steps stop"
        " short is the site to move the `expect_progress` into."
    )


def _report_denominator(progress) -> None:
    """The trajectory, and the worst backwards jump a host would render."""
    if not progress:
        return
    totals: list[int] = []
    for _, event in progress:
        if not totals or totals[-1] != event.total:
            totals.append(event.total)
    worst = 0.0
    previous = 0.0
    for _, event in progress:
        if event.total:
            ratio = event.done / event.total
            worst = max(worst, previous - ratio)
            previous = ratio
    print(
        f"\n  DENOMINATOR: {' -> '.join(str(t) for t in totals)}"
        f"\n    worst backwards jump in done/total: {worst:.0%}."
        " A host that caches the first denominator it sees renders a bar that goes"
        " backwards by at least this much; the event carries `total` every time for"
        " exactly this reason."
    )


def _report_leaks(progress, document: str) -> None:
    """The tripwire that matters most on this path: labels must not quote source."""
    haystack = " ".join(document.split()).lower()
    leaks: list[tuple[str, str]] = []
    overlong: list[str] = []
    for _, event in progress:
        detail = event.detail or ""
        if len(detail) > _MAX_LABEL_CHARS:
            overlong.append(detail)
        normalised = " ".join(detail.split()).lower()
        for i in range(0, max(0, len(normalised) - _LEAK_WINDOW) + 1):
            fragment = normalised[i : i + _LEAK_WINDOW]
            if fragment and fragment in haystack:
                leaks.append((detail, fragment))
                break

    if not leaks and not overlong:
        print(
            f"\n  LEAK CHECK: clean. No label carries a {_LEAK_WINDOW}-char run of"
            f" the source and none exceeds {_MAX_LABEL_CHARS} chars, across"
            f" {len(progress)} label(s). The material on this path is whole"
            " documents, so this is the check that keeps a host rendering labels"
            " verbatim from putting the person's own text on a progress line."
        )
    for detail, fragment in leaks:
        print(f"\n  LEAK: label quotes the source — {fragment!r} in {detail!r}")
    for detail in overlong:
        print(f"\n  OVERLONG label ({len(detail)} chars): {detail!r}")

    assert not leaks, (
        "a progress label contains a run of the ingested document. Labels on this"
        " path are indices and counts by rule; something is interpolating content"
    )
    assert not overlong, (
        f"a progress label exceeds {_MAX_LABEL_CHARS} chars, which is long enough"
        " to be carrying a payload rather than describing a step"
    )
