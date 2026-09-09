"""The seven newly-scoped tools, watched on a real provider.

WHAT THIS ANSWERS THAT THE UNIT TESTS CANNOT
============================================
`tests/test_tool_progress_scopes.py` already proves, against mock brain, that each
of these seven tools opens exactly one keyed stream, closes it once, balances its
arithmetic, and leaks neither framework vocabulary nor the person's own text. None of
that needs a provider. What needs one:

- **Are the labels worth anything to a person?** A stream that closes 5/5 can still be
  five events in the first second followed by ninety seconds of silence. Only wall-clock
  gaps answer that, and only a real provider produces them.
- **Do phantoms appear under real branch conditions?** Mock brain returns identical DTOs
  every call, so its dedup collapses fixtures and whole branches never run.
  `FindPolarities`' Phase 0 is the recorded case: its consolidation step sits below a
  `len(unique_hashes) < 2` guard that mock brain reaches with one thesis, so the label
  never fires in the mocked suite and cannot be seen there at all.
- **Does the denominator behave?** `expect_progress` grows `total` additively, so a
  host caching the first denominator draws a bar that goes backwards. The size of that
  jump is a live property.

**These tools were never measured as ENTRY POINTS before.** Their internal reporting
sites were measured — on the `ingest`, `analyze` and `anchor` paths, where the same
`SurfaceTheses` / `FindPolarities` / `AntithesisExtraction` / `ExpandPolarity` /
`SourceDigest` code runs beneath a tool that owned the stream. What no run has ever
watched is one of these tools called DIRECTLY, which is exactly how a model reaches
them: `find_polarities` alone is the whole antithesis block with nothing else running.

WHAT IT CANNOT SAY
==================
One run per tool, one model, one source. Every number here is a single sample, and the
`ingest` probe's own history is the warning: **a 1 KB source ran 651s once and 45.5s the
next time**, identical call structure. So read the SHAPE (which phase is silent, whether
the labels land where the work is) and never a duration as a baseline. A retry is
invisible on this channel by design — `progress_key` is content-derived so a retry is
not new work — so any single gap may be a retry rather than a slow call; the retry
accounting per tool is printed for exactly that reason.

The tools run as a CHAIN on one Case, each feeding the next (`add_input` -> its Input ->
`surface_theses` -> its theses -> `find_polarities` -> its polarities ->
`expand_polarities`), because that is both the cheapest way to get real arguments and
the order a real session produces them. Cost follows the chain: `find_polarities` is
most of it, one antithesis chain per thesis.

Run: DIALEXITY_PROBE_TOOL_THESES=3 poetry run pytest --real-llm -s -q \
        tests/e2e/probe_tool_progress.py

RESULTS — first run, haiku-4.5, 10 KB source, 3 theses, 68 calls / 93.8s total
=============================================================================
    tool                  wall  calls  events  closed  widest hole
    add_input            11.6s      1       2     1/1  11.4s  (98% of the wall)
    digest_input         10.8s      1       2     1/1  10.7s  (100%)
    surface_theses       16.1s     13       4     3/3   6.1s  (38%)
    find_polarities      10.8s     37      42     8/8   3.0s  (28%)
    expand_polarities    18.0s      6       5     4/4   8.6s  (48%)
    anchor_theses         6.1s      4       2     1/1   6.1s  (100%)
    introduce_polarity   14.1s      6       3     2/2   7.1s  (50%)

**All seven speak, and every one closes balanced** — one stage, one key, no phantom
step, no leaked source, on the branches this run took. Before the scopes were installed
every row above would have been zero events for its whole wall. No retry fired on this
run, so none of the holes below is a retry in disguise.

What the run says that the mocked tests could not:

- **`digest_input` wrote NOTHING to the graph.** 0 effects across 10.8s, because it
  re-digested an Input that `add_input` had already digested. A graph-watching host sees
  a completely dark ten seconds; the progress channel is the only thing that speaks
  there. This is the sharpest single argument for the channel found so far.
- **`anchor_theses` is the thinnest stream: one label, then 100% of the wall silent.**
  Four provider calls (classification, taxonomy location) run inside that hole with
  nothing said about them. Not a defect — the stream is honest and closes 1/1 — but it
  is the clearest remaining place to add a step, and the cheapest.
- **`add_input` never names the capture.** Its first label is about building an
  understanding, published from inside `SourceDigest`; the Input node write that
  actually happens first is unlabelled. The `ingest` tool says "Taking in the material"
  because it declares that step itself. Whether `add_input` should too is a judgement
  call, recorded here rather than taken.
- **The two `ingest`-stage doors key DIFFERENT WIDTHS for the same node** —
  `add_input` keys `43764b716d` (10 chars, digest of the content) and `digest_input`
  keys `43764b7` (7 chars, the node's own hash shortened). Correct: they are different
  work reached by different arguments. But a host must not assume key width, and must
  not expect a re-digest to join the original capture's stream.
- **`expand_polarities` flashes.** Both "Working out how each side helps..." steps land
  in the SAME instant (0.09s), because the fan-out declares one per polarity and the
  labels are identical — the person sees one line where two were published. The 0.0s
  flash again, at a site the caller/callee analysis did not predict: not a caller
  duplicating an inner label, but a gather duplicating its own.
- **`find_polarities`' 30 `note` events arrive in a two-second burst, all reading
  "Another angle weighed".** Honest (each is one returning angle) and deliberately
  counter-neutral, but indistinguishable from one another, so a host rendering each
  shows a stutter rather than progress. The 10 KB `ingest` run reproduces this at
  110 notes. A count in the label would fix it and needs a total the site does not
  have; left alone.
- **`find_polarities` has the worst denominator jump: 17% backwards.** Its steps are
  declared per thesis as the fan-out resolves, which is the additive-`expect_progress`
  contract working as designed and the reason every event carries `total`.

The best-shaped stream is `introduce_polarity`: two labels, ~7s each, no hole longer
than half its work.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model
# The document generator, and the report helpers, imported rather than copied. Private
# by name, shared on purpose — the same precedent as `probe_ingest_progress` importing
# `_document` from `probe_ingest_cost`: a second copy of the gap arithmetic would make
# this probe's silences unpriceable against that one's.
from e2e.probe_ingest_cost import _document
from e2e.probe_ingest_progress import (_report_denominator, _report_leaks,
                                       _report_phantoms)

from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils import progress as progress_module
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.retry_accounting import retry_account

#: How many theses to extract, and therefore how many antithesis chains
#: `find_polarities` gathers. THE cost knob of this probe: each chain is ~11 provider
#: calls. Three is enough for Phase 0's consolidation guard to be passed (it needs two)
#: while leaving room for a merge to remove one.
THESES = max(2, int(os.getenv("DIALEXITY_PROBE_TOOL_THESES", "3")))

#: Fixed at 10 KB and NOT read from `DIALEXITY_PROBE_INGEST_KB`, because the branch
#: under test here is size-dependent and the two archived ingest sizes both miss it:
#: the single-pass digest label fires only for 1,500 < len(content) <= 40,000 chars
#: (`DIGEST_THRESHOLD` .. `CHUNK_SIZE`). 1 KB is below the threshold (no digest at all)
#: and 120 KB is four windows (the parts branch, which has its own labels). This is
#: also the ordinary case for a pasted document.
SOURCE_CHARS_KB = 10

INTENT = "Find the structural trade-offs this material keeps returning to"

#: A gap longer than this is dead air a person would notice. Same value as the ingest
#: probe's, and for the same reason: it is the rough floor of "did it freeze?", not a
#: tuned threshold. The full gap list prints anyway.
_NOTICEABLE_GAP_S = 3.0


async def _watch(bus, sid: str, make_coro, *, label: str):
    """Run one tool, collecting BOTH channels, timestamped from ITS OWN start.

    Subscribes per tool rather than once for the whole Case, because the claim under
    test is per tool: one stream, one key, one close. Slicing a shared subscription
    would fold a straggler from the previous tool into the next one's accounting, which
    is the exact defect this probe exists to catch.
    """
    progress: list[tuple[float, object]] = []
    effects: list[tuple[float, object]] = []
    ready = asyncio.Event()
    progress_ready = asyncio.Event()
    started = 0.0

    async def _collect_effects() -> None:
        async with bus.subscribe(sid) as subscriber:
            ready.set()
            async for event in subscriber:
                effects.append((time.monotonic() - started, event.message.effect))

    async def _collect_progress() -> None:
        async with bus.subscribe_progress(sid) as subscriber:
            progress_ready.set()
            async for event in subscriber:
                progress.append((time.monotonic() - started, event.message))

    collector = asyncio.create_task(_collect_effects())
    progress_collector = asyncio.create_task(_collect_progress())
    # Subscribe BEFORE the work: `broadcaster` registers the queue inside the context
    # manager, so a task merely created is not yet listening and the first events —
    # the ones that decide time-to-first-event — would be dropped.
    await ready.wait()
    await progress_ready.wait()

    started = time.monotonic()
    result = None
    error: BaseException | None = None
    try:
        with call_census() as census, retry_account() as account:
            result = await make_coro()
    except BaseException as exc:  # noqa: BLE001 - a probe reports, it does not gate
        error = exc
    waited = time.monotonic() - started

    # Both publishes are `loop.create_task`, so an event recorded in the final instant
    # has not necessarily been delivered yet.
    await asyncio.sleep(0.5)
    collector.cancel()
    progress_collector.cancel()
    for task in (collector, progress_collector):
        try:
            await task
        except asyncio.CancelledError:
            pass

    return {
        "label": label,
        "result": result,
        "error": error,
        "waited": waited,
        "progress": progress,
        "effects": effects,
        "census": census,
        "account": account,
    }


def _print_stream(run: dict) -> None:
    """The whole stream, verbatim. The point of a probe is what actually came out."""
    label, progress, waited = run["label"], run["progress"], run["waited"]
    census, account = run["census"], run["account"]

    print(f"\n{'=' * 78}\n{label}")
    print(
        f"  waited {waited:7.1f}s   calls {census.count:3d}"
        f"   provider {census.provider_s:7.1f}s   in-flight {census.busy_s:7.1f}s"
        f"   parallelism {census.parallelism:5.2f}x"
    )
    if account.count:
        print(
            f"  retries {account.count} {dict(account.kinds)}"
            f" — slept {account.sleep_s:.1f}s of that wall, so any gap below may be a"
            f" retry rather than a slow call"
        )
    if run["error"] is not None:
        print(f"  RAISED {type(run['error']).__name__}: {run['error']}")
    print(f"  effects {len(run['effects'])}   progress events {len(progress)}")

    if not progress:
        print(
            "  ZERO progress events. Either the scope was installed after the gathered"
            " tasks were created (they inherit a context that does not point at it) or"
            " nothing beneath this tool reports at all."
        )
        return

    print(f"  {'at':>8}  {'gap':>7}  {'done/total':>10}  kind  detail")
    previous = 0.0
    for t, event in progress:
        gap = t - previous
        kind = "final" if event.final else ("note " if event.note else "step ")
        flag = "  <-- dead air" if gap >= _NOTICEABLE_GAP_S else ""
        print(
            f"  {t:8.2f}  {gap:7.2f}  {event.done:4d}/{event.total:<5d}"
            f"  {kind} {event.detail or '(empty)'}{flag}"
        )
        previous = t
    tail = waited - progress[-1][0]
    print(f"  {'':8}  {tail:7.2f}   after the last event{'  <-- dead air' if tail >= _NOTICEABLE_GAP_S else ''}")

    stages = {e.stage for _, e in progress}
    keys = {e.key for _, e in progress}
    print(f"  stage(s) {sorted(stages)}   key(s) {sorted(keys)}")

    gaps = [(progress[0][0], "before the first event")]
    for i in range(1, len(progress)):
        gaps.append((progress[i][0] - progress[i - 1][0], progress[i][1].detail))
    gaps.append((tail, "after the last event"))
    widest, what = max(gaps, key=lambda g: g[0])
    share = widest / waited * 100 if waited else 0.0
    print(f"  WIDEST HOLE {widest:.1f}s ({share:.0f}% of the wall) — {what!r}")


def _check(run: dict) -> list[str]:
    """Coherence only, collected rather than asserted — one tool must not stop the rest.

    Returned so the summary can name them; the test asserts on the collection at the
    very end, after every tool has had its say.
    """
    label, progress = run["label"], run["progress"]
    problems: list[str] = []

    if not progress:
        return [f"{label}: no progress event reached the bus"]

    keys = {e.key for _, e in progress}
    if len(keys) != 1:
        problems.append(f"{label}: {len(keys)} keys on one call ({sorted(keys)})")

    stages = {e.stage for _, e in progress}
    if len(stages) != 1:
        problems.append(
            f"{label}: {len(stages)} stages ({sorted(stages)}) — a nested scope"
            f" installed instead of deferring"
        )

    finals = [e for _, e in progress if e.final]
    if len(finals) != 1:
        problems.append(f"{label}: {len(finals)} closing events, expected 1")
    elif finals[0] is not progress[-1][1]:
        problems.append(f"{label}: a step arrived AFTER the closing event")
    elif finals[0].detail != "":
        problems.append(f"{label}: closing event carries a label {finals[0].detail!r}")

    if any(e.total < e.done for _, e in progress):
        problems.append(f"{label}: done exceeded total — a denominator declared late")

    if run["error"] is not None:
        problems.append(f"{label}: raised {type(run['error']).__name__}")

    return problems


def _artifacts(result) -> dict:
    """Tool output is JSON for the model; the probe needs the hashes back out of it."""
    if not isinstance(result, str):
        return {}
    try:
        return json.loads(result).get("artifacts") or {}
    except (json.JSONDecodeError, AttributeError):
        return {}


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(7200)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_tool_progress_streams(di_container):
    from dialectical_framework.agents.analyst.skills.anchor_theses import \
        anchor_theses
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        expand_polarities
    from dialectical_framework.agents.analyst.skills.find_polarities import \
        find_polarities
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        introduce_polarity
    from dialectical_framework.agents.analyst.skills.surface_theses import \
        surface_theses
    from dialectical_framework.agents.orchestrator.tools.add_input import \
        add_input
    from dialectical_framework.agents.orchestrator.tools.digest_input import \
        digest_input

    document = _document(SOURCE_CHARS_KB)
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(
        f"source: {len(document):,} chars — one window, above DIGEST_THRESHOLD, so the"
        f" SINGLE-PASS digest branch runs (the branch neither archived ingest size"
        f" reaches)"
    )
    print(f"theses requested: {THESES} (so {THESES} antithesis chains at ~11 calls each)")
    if os.getenv("DIALEXITY_MAX_CONCURRENT_LLM_CALLS"):
        print(
            "  NOTE: the concurrency semaphore is SET, so silence below includes"
            " queueing, not just provider time."
        )

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    bus = di_container.event_bus()
    await bus.connect()
    assert ExecutionReport._event_bus is bus, (
        "the report class is not publishing to this bus, so an empty graph stream"
        " would say nothing about the framework"
    )
    assert progress_module._event_bus is bus, (
        "progress is not wired to this bus — see `utils/progress.set_event_bus`;"
        " without this an empty progress stream would read as 'the emission points"
        " never fire', which is the wrong conclusion from a setup bug"
    )

    runs: list[dict] = []
    try:
        case = Case()
        case.commit()
        with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
            # 1. add_input — the capture AND the digest behind it, one stream. The
            #    label under test lives inside `SourceDigest._generate_digest`.
            run = await _watch(
                bus, case.sid,
                lambda: add_input.fn(content=document),
                label="add_input (stage `ingest`, key = digest of the content)",
            )
            runs.append(run)
            input_hash = _artifacts(run["result"]).get("input_hash")
            print(f"  -> input_hash {input_hash}")

            # 2. digest_input — the same concern reached by hash, keyed by the NODE.
            #    Already digested by (1), so this exercises the refresh path.
            if input_hash:
                runs.append(await _watch(
                    bus, case.sid,
                    lambda: digest_input.fn(input_hash=input_hash),
                    label="digest_input (stage `ingest`, key = the Input's short hash)",
                ))

            # 3. surface_theses — the one site in the tree whose denominator is known
            #    in advance, though only when the source SWEEPS; at 10 KB it does not.
            run = await _watch(
                bus, case.sid,
                lambda: surface_theses.fn(intent=f"{INTENT}. Extract {THESES}."),
                label="surface_theses (stage `extraction`, key = digest of the intent)",
            )
            runs.append(run)
            thesis_hashes = list(_artifacts(run["result"]).get("thesis_hashes") or [])
            print(f"  -> {len(thesis_hashes)} thesis hash(es)")

            # 4. find_polarities — the longest silence on the Analyst's path: Phase 0
            #    consolidation, then one antithesis chain per surviving thesis,
            #    including the `note_progress` site that reports each returning angle.
            if len(thesis_hashes) >= 2:
                run = await _watch(
                    bus, case.sid,
                    # count is antitheses PER thesis, so 1 keeps this linear in the
                    # thesis count. The shape under test is the fan-out across theses,
                    # not the depth within one.
                    lambda: find_polarities.fn(thesis_hashes=thesis_hashes, count=1),
                    label="find_polarities (stage `opposition`, key = digest of the theses)",
                )
                runs.append(run)
                polarity_hashes = [
                    row["polarity_hash"]
                    for row in _artifacts(run["result"]).get("polarity_data") or []
                    if row.get("polarity_hash")
                ]
                print(f"  -> {len(polarity_hashes)} polarity hash(es)")
            else:
                polarity_hashes = []
                print(
                    f"  SKIPPED find_polarities: only {len(thesis_hashes)} thesis"
                    f" hash(es), and its consolidation guard needs two"
                )

            # 5. expand_polarities — every step inside a `gather` the TOOL creates,
            #    which is the ordering guarantee no other tool here tests. Two is
            #    enough to exercise the fan-out; more is linear cost for one shape.
            if polarity_hashes:
                runs.append(await _watch(
                    bus, case.sid,
                    lambda: expand_polarities.fn(polarity_hashes=polarity_hashes[:2]),
                    label="expand_polarities (stage `expansion`, key = digest of the polarities)",
                ))

            # 6. anchor_theses — the person's own named concepts, no extraction.
            runs.append(await _watch(
                bus, case.sid,
                lambda: anchor_theses.fn(statements=["Delivery speed", "Oversight"]),
                label="anchor_theses (stage `anchor`, key = digest of the statements)",
            ))

            # 7. introduce_polarity — the same stage AND the same key construction as
            #    the Advisor's `anchor` tool, so both doors key one stream.
            runs.append(await _watch(
                bus, case.sid,
                lambda: introduce_polarity.fn(
                    thesis="Ship on the promised date",
                    antithesis="Hold the release until the audit clears",
                ),
                label="introduce_polarity (stage `anchor`, key = advisor.anchor's own)",
            ))
    finally:
        await bus.disconnect()

    problems: list[str] = []
    for run in runs:
        _print_stream(run)
        if run["progress"]:
            _report_phantoms(run["progress"])
            _report_denominator(run["progress"])
            try:
                # This helper asserts on a leak. Collect it instead of letting it
                # abort the loop: the remaining tools' streams are the run's value
                # and a leak in the first one must not cost us the other six.
                _report_leaks(run["progress"], document)
            except AssertionError as exc:
                problems.append(f"{run['label']}: {exc}")
        problems.extend(_check(run))

    print(f"\n{'=' * 78}\nSUMMARY")
    print(f"  {'tool':<22} {'wall':>8} {'calls':>6} {'events':>7} {'closed':>9}  widest hole")
    for run in runs:
        progress = run["progress"]
        finals = [e for _, e in progress if e.final]
        closed = f"{finals[0].done}/{finals[0].total}" if finals else "NEVER"
        if progress:
            gaps = [progress[0][0]] + [
                progress[i][0] - progress[i - 1][0] for i in range(1, len(progress))
            ] + [run["waited"] - progress[-1][0]]
            widest = f"{max(gaps):.1f}s"
        else:
            widest = "n/a"
        print(
            f"  {run['label'].split(' ')[0]:<22} {run['waited']:7.1f}s"
            f" {run['census'].count:6d} {len(progress):7d} {closed:>9}  {widest}"
        )

    if problems:
        print("\nPROBLEMS")
        for problem in problems:
            print(f"  - {problem}")

    assert runs, "no tool ran — the chain broke before the first one"
    # The stream-shape guarantees are cheap to state and the whole reason for the run;
    # durations are reported, never gated.
    assert not problems, "\n".join(problems)
