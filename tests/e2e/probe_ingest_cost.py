"""Probe: what does ingesting a LARGE source actually cost, now that it is swept?

WHY
===
The ingestion figure in circulation is **DERIVED, not measured**: three undigested
~400 KB files render 1.22 MB / ~300k tokens (`tests/probe_input_text_cost.py`,
which measured only the rendering), and multiplying that by the send counts in the
code gave "~2.5M-6M tokens per ingest". Every step of that arithmetic was checked
against the source and two of the multipliers were still wrong on the first two
attempts (`max_attempts` is 4 and not 3; step 2 is up to six sends and not one,
because `ConversationFacilitator.isolate()` COPIES the history holding step 1's
prompt). A number nobody has observed, whose derivation has already been wrong
twice, is not a measurement — so this probe makes it one.

Three fixes have landed since that projection, and this is the first run that can
say what they bought:

- `input_context` is bounded (`INPUT_CONTEXT_BUDGET`), so grounding no longer
  renders documents.
- `SourceDigest` reads a long source in PARTS (n+1 calls, capped at 8 wide).
- `SurfaceTheses` SWEEPS a long source window by window instead of sending the
  whole concatenation up to four times, and `StatementDeduplication` bounds its
  own source context.

WHAT IT MEASURES
================
`utils/call_census.py` and `utils/retry_accounting.py` around ONE `ingest` call on
a synthetic document of a known size. The census gives the two levers the sibling
probes established — `provider_s` is COST, `busy_s`/`depth` is LATENCY,
`parallelism` is neither, it reports compression already achieved — plus the thing
this probe actually exists for: **prefill tokens, split by stage**.

The stage split is by response-model name, and the three that matter are the ones
that can carry a WINDOW of the document:

- `DigestDto` — one per part plus the reduce (`SourceDigest`).
- `ExtractedContentDto` — step 1 of `ThesisExtraction`, one per window, the
  window in the prompt.
- `CandidateCheckDto` — step 2, up to `count + 2` per window, each one carrying
  the window AGAIN because `isolate()` copies step 1's history.

Everything else (intent parsing, classification, deduplication, polarity finding
and expansion) sees bounded context by construction and is grouped as REST. The
DTOs are IMPORTED rather than named as strings, so a rename breaks this file
instead of silently re-staging a third of the tokens into the wrong bucket.

READING IT HONESTLY
===================
- **The default document is 120 KB, which is 4 windows — a tenth of the 1.2 MB
  scenario the projection was about.** Scaling the result up is LINEAR IN WINDOWS
  by construction (each window is read independently; nothing about window 30
  costs more than window 3), so the extrapolation is defensible — but it IS an
  extrapolation and must be labelled one. `DIALEXITY_PROBE_INGEST_KB=1200`
  measures the real thing at ten times the price.
- **A bound on each CALL is not a bound on the TOTAL.** The sweep's whole claim is
  that no single prompt carries the document; the number of prompts still grows
  with the document. So a large total here would NOT refute the sweep — it would
  say the remaining cost is the fan-out width, which is a different lever
  (`isolate()`, see below).
- **Output tokens are not measured.** `CallRecord` records prefill only, so every
  token figure here is input-side. On ingestion that is where the mass is (a
  digest reading is a few hundred output tokens against ten thousand in), but the
  bill is larger than what this prints.
- **Read `calls_with_usage` before any token total.** A call that reported no
  usage is recorded as UNMEASURED, not as zero.
- **`cache_read` of 0 alongside a large `cache_write` is a FINDING, not a
  non-event.** The first run of this probe printed a note saying a zero read was
  expected because no ingestion prompt clears the 4,096-token minimum. That note
  was wrong, and the same run's own `cache_write` column proved it: 184,625 tokens
  were written. A cache WRITE bills at 1.25x, so every written token that nothing
  ever reads is a 25% surcharge paid for nothing. The probe now prices that
  explicitly instead of explaining it away — see `_cache_verdict`.
- Synthetic material, deliberately: cost is driven by SIZE, which this controls
  exactly, and the paragraphs are varied enough (twelve distinct tensions, cycled
  with a running index) that extraction has real work to do rather than finding
  the same claim in every window and deduplicating it away.

    poetry run pytest tests/e2e/probe_ingest_cost.py -s --real-llm

`-o log_cli=true --log-cli-level=WARNING` for the same reason as the sibling
probes: this PASSES while retrying, so the warnings naming a failing DTO are
otherwise collected and discarded.

WHAT TO DO WITH THE ANSWER
==========================
One lever is already identified and deliberately NOT taken: switching
`ThesisExtraction._step2_identify_candidates` off `isolate()` to a fresh
facilitator would cut the `CandidateCheckDto` row to nothing, since those calls
carry the window only because they inherit step 1's history. If that row dominates,
this probe is the evidence that the A/B is worth running — which is the whole point
of measuring rather than projecting.

RESULT (2026-09-04, haiku-4.5, 120 KB / 4 windows, two runs)
============================================================
**The projection was right about the order of magnitude and wrong about where the
money goes.** Extrapolated to the 1.2 MB scenario (33 windows by the real chunker):
**~2.5M prefill tokens**, against the derived "~2.5M-6M". So the number survives
contact with measurement, at the bottom of its own band.

**The size-driven measurement is solid; the rest of the pipeline is not stable
enough to extrapolate.** Two back-to-back runs on the identical document:

| | run 1 | run 2 |
|---|---|---|
| calls | 196 | 95 |
| size-driven prefill (READ + both SWEEP stages) | 276,044 | 276,396 |
| per window | 69,011 | 69,099 |
| everything else ("fixed") | 537,482 | 191,949 |
| polarities found | 50 | 5 |
| wall clock | 98.5s | 85.1s |

The size-driven part reproduced to **0.1%**, which is what a real rate looks like.
The remainder swung **2.8x** — because `find_polarities` proposed 50 pairs in one
run and 5 in the other, and each pair costs a downstream evaluation (`ModePointResultDto`
x110 alone was 661.7s of run 1's 1,024.6s of provider time). So the label "fixed"
in the RATE line means "not driven by SOURCE SIZE", not "constant": it is driven by
extraction YIELD, which is stochastic. Anyone quoting a single total from this probe
is quoting a coin flip. Quote the per-window figure.

**Step 2 is the lever, confirmed: 207,047 tokens, 75% of everything the document's
size costs**, across 24 calls that carry a window each — solely because
`isolate()` copies step 1's history. Dropping that would cut ingestion's
size-driven cost roughly 4x. Still not taken: it is a reasoning change and needs an
A/B, not a measurement.

**Cache traffic on this path is pure loss, and this is the run that found it:
184,438 tokens written, 0 read, ~46,110 token-equivalents of 1.25x surcharge for
entries nothing came back for.** All of it is step 2 (see the cache-written column).
It is not fixable by adding breakpoints — the sharing is between CONCURRENT
siblings, which is the one shape prompt caching cannot serve. It IS fixed for free
by the step-2 change above, which is a third argument for that A/B.

**Latency is not the problem here.** 85-98s to ingest 120 KB at 5-11x parallelism,
with 1.3-3.9s of the wall clock spent outside any provider call. There is no
orchestration gap to close on this path.
"""

from __future__ import annotations

import logging
import os
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.tools import ingest as ingest_mod
from dialectical_framework.concerns.source_digest import DigestDto
from dialectical_framework.concerns.thesis_extraction import (
    CandidateCheckDto, ExtractedContentDto)
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.chunking import CHUNK_SIZE, chunk_text
from dialectical_framework.utils.retry_accounting import retry_account

#: Twelve unrelated tensions, so a window has something of its own to say.
#: Repetition across windows would let deduplication hide the extraction cost.
_TENSIONS = [
    "Concentrating release authority in one team makes the schedule predictable "
    "and makes every delay theirs alone; distributing it removes the bottleneck "
    "and removes the person who can say the date is wrong.",
    "Documenting a process so it survives turnover freezes the version of it that "
    "was true when somebody wrote it down; leaving it in people's heads keeps it "
    "current and unshareable.",
    "Hiring for the gap you have now fills it faster than hiring for the gap you "
    "expect, and leaves you with a team shaped like a problem you already solved.",
    "Pricing per seat rewards you for accounts that grow and punishes you for "
    "products that make each seat more capable, since the better they work the "
    "fewer are needed.",
    "A long deprecation window keeps trust with the customers who cannot move and "
    "keeps the code that cannot be simplified, so the cost of the promise lands on "
    "everyone who kept up.",
    "Reviewing every change catches the mistakes a reviewer can see and teaches "
    "the author to write for the reviewer rather than for the reader.",
    "Measuring a team on throughput surfaces the work nobody was tracking and "
    "buries the work that does not decompose into countable units.",
    "Owning your infrastructure keeps the failure modes yours to fix and the "
    "attention yours to spend, on a problem that is nobody's differentiator.",
    "Onboarding a customer with a bespoke integration wins the account and adds a "
    "constraint to every future decision about the interface.",
    "Splitting a monolith makes each part deployable and makes every interesting "
    "question a question about two parts at once.",
    "Paying above market removes compensation as a reason to leave and removes it "
    "as a reason to stay somewhere the work has gone stale.",
    "Giving a team full autonomy makes them accountable for outcomes and makes the "
    "organisation's shared problems nobody's job in particular.",
]


def _document(kilobytes: int) -> str:
    """A document of ~`kilobytes`, varied, deterministic, and paragraph-broken."""
    target = kilobytes * 1024
    parts: list[str] = []
    size = 0
    index = 0
    while size < target:
        tension = _TENSIONS[index % len(_TENSIONS)]
        block = (
            f"## Section {index + 1}\n\n"
            f"{tension}\n\n"
            f"The team argued about section {index + 1} for two weeks and settled "
            f"nothing. Both readings survived the argument, which is the tell that "
            f"the trade-off is real rather than a matter of getting the facts "
            f"straight.\n\n"
        )
        parts.append(block)
        size += len(block)
        index += 1
    return "".join(parts)[:target]


#: Source size in KB. 120 is 4 windows — enough to exercise both sweeps at a
#: tenth of the 1.2 MB scenario the projection was about.
SOURCE_KB = max(1, int(os.getenv("DIALEXITY_PROBE_INGEST_KB", "120")))

INTENT = "Find the structural trade-offs this material keeps returning to"

#: Stages, keyed by response model. Imported classes, not strings: a rename must
#: break this file rather than quietly move a third of the tokens into REST.
_READ = {DigestDto.__name__}
_SWEEP_STEP1 = {ExtractedContentDto.__name__}
_SWEEP_STEP2 = {CandidateCheckDto.__name__}


_READ_LABEL = "READ (digest, in parts)"
_STEP1_LABEL = "SWEEP step 1 (window in the prompt)"
_STEP2_LABEL = "SWEEP step 2 (window via isolate())"
_REST_LABEL = "REST (bounded context)"

#: The stages whose cost is driven by the SIZE of the source. Everything else has
#: bounded context by construction, so it is a fixed cost per ingest and must not
#: be scaled when extrapolating to a bigger document. Scaling the grand total
#: instead was the first version's mistake, and at 66% REST it overstated the
#: 1.2 MB figure by roughly 3x.
_SIZE_DRIVEN = (_READ_LABEL, _STEP1_LABEL, _STEP2_LABEL)


def _stage(format_name: str | None) -> str:
    if format_name in _READ:
        return _READ_LABEL
    if format_name in _SWEEP_STEP1:
        return _STEP1_LABEL
    if format_name in _SWEEP_STEP2:
        return _STEP2_LABEL
    return _REST_LABEL


#: Cache surcharge on Anthropic models: a write bills at 1.25x base input, a read
#: at 0.1x. So a written token that is later read pays 1.35x instead of 2.0x and
#: wins; a written token that is NEVER read pays 1.25x instead of 1.0x and simply
#: loses. Only the second case is priced below, because it is the one this path is
#: in and the one nobody chose.
_CACHE_WRITE_SURCHARGE = 0.25


def _cache_verdict(census) -> None:
    """Price the cache traffic, including the case where it is pure loss.

    Written because the first version of this probe printed "cache read of 0 is
    EXPECTED, no ingestion prompt clears the 4,096-token minimum" — and the same
    run reported 184,625 tokens WRITTEN, which is only possible if prompts cleared
    it. An explanation that contradicts a number printed three lines above it is
    worse than no explanation, so the note is now derived from the numbers.

    The mechanism, from the code rather than from the totals: mirascope stamps
    `cache_control` on the LAST content block of the LAST message, and only when
    the history contains an assistant turn (`anthropic/_utils/encode.py:356-377`).
    `ThesisExtraction._step2_identify_candidates` fans out `count + 2` isolated
    conversations whose copied history holds step 1's window — multi-turn, ~10k
    tokens, comfortably over the minimum — so each one writes a cache entry. They
    run under one `asyncio.gather`, so they are all in flight at once and none can
    read what another wrote: a provider cache entry is readable only after the
    call that wrote it has returned. Concurrent siblings sharing a long prefix is
    the one shape prompt caching cannot help, and it is exactly this shape.
    """
    written = census.cache_write_tokens
    read = census.cache_read_tokens
    if not written and not read:
        print(
            "\n  CACHE — no traffic either way. Every prefix in this run was under"
            " the 4,096-token minimum, which is the correct outcome for small"
            " prompts and not a defect."
        )
        return
    if read:
        print(
            f"\n  CACHE — {written:,} written, {read:,} read. A read pays back a"
            f" write, so this is working; the ratio is the thing to watch."
        )
        return
    print(
        f"\n  CACHE — {written:,} tokens WRITTEN and {read:,} read, which is pure"
        f" loss: a write bills at 1.25x, so this run paid"
        f" ~{written * _CACHE_WRITE_SURCHARGE:,.0f} token-equivalents of surcharge"
        f" for entries nothing came back for."
        f"\n    Not a misconfiguration and not fixable by 'more caching': the"
        f" prefixes that clear the minimum are shared by CONCURRENT siblings"
        f" (`_step2_identify_candidates` fans out under one gather), and a cache"
        f" entry is readable only after the call that wrote it returns. The"
        f" available fixes are to stop writing here, or to serialize one call"
        f" first so the rest can read it — the second buys the discount at the"
        f" price of a round trip on the critical path, which is the wrong"
        f" direction for a latency complaint."
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(7200)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_ingest_cost(di_container):
    document = _document(SOURCE_KB)
    windows = chunk_text(document)

    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print(
        f"source: {len(document):,} chars ({SOURCE_KB} KB)"
        f" -> {len(windows)} window(s) of at most {CHUNK_SIZE:,} chars"
    )
    if len(windows) == 1:
        print(
            "  NOTE: ONE window, so neither sweep fires and this run measures the"
            " single-pass path. Raise DIALEXITY_PROBE_INGEST_KB to exercise the"
            " thing the probe is about."
        )
    if os.getenv("DIALEXITY_MAX_CONCURRENT_LLM_CALLS"):
        print(
            "  NOTE: the concurrency semaphore is SET, so `not in a call` below"
            " includes queueing and must not be read as orchestration."
        )

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    case = Case()
    case.commit()

    with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
        with call_census() as census, retry_account() as account:
            started = time.monotonic()
            report = await ingest_mod.ingest.fn(text=document, intent=INTENT)
            waited = time.monotonic() - started

    working = max(0.0, waited - account.wasted_s)
    print(
        f"\n  waited {waited:8.1f}s"
        f"   working {working:8.1f}s"
        f"   slept {account.sleep_s:6.1f}s"
        f"   retries {account.count} {dict(account.kinds) or ''}"
    )
    print(
        f"  calls {census.count:4d}"
        f"   provider {census.provider_s:8.1f}s"
        f"   in-flight {census.busy_s:8.1f}s"
        f"   not in a call {max(0.0, waited - census.busy_s):7.1f}s"
    )
    print(
        f"  PARALLELISM {census.parallelism:5.2f}x"
        f"   depth ~{census.depth:5.1f} stages"
        f"   mean call {census.mean_call_s:5.1f}s"
    )

    if census.count == 0:
        print(
            "  NO calls recorded — the census is not wired."
            " Fix that before reading anything else."
        )
        pytest.fail("ingest made no LLM calls at all — setup is wrong")

    # Tokens, and the gate on them first: a total is only as complete as the
    # number of calls that reported usage at all.
    print(
        f"\n  token usage reported by {census.calls_with_usage} of"
        f" {census.count} calls"
    )
    if census.calls_with_usage < census.count:
        print(
            f"    {census.count - census.calls_with_usage} call(s) reported NO"
            " usage — recorded as unmeasured, not as zero, so every figure below"
            " is a FLOOR."
        )
    print(
        f"  prefill: {census.uncached_input_tokens:,} uncached"
        f"   {census.cache_read_tokens:,} cache read"
        f"   {census.cache_write_tokens:,} cache write"
    )
    print("    (output tokens are NOT recorded, so the bill is larger than this)")

    measured_prefill = sum(c.prefill_tokens or 0 for c in census.calls)

    # The stage split — the actionable output, because the three window-bearing
    # stages are the ones any further fix would touch. `cw` is carried per stage
    # so an unread cache write can be attributed rather than just totalled.
    print("\n  prefill tokens by stage:")
    by_stage: dict[str, tuple[int, int, float, int]] = {}
    for call in census.calls:
        stage = _stage(call.format_name)
        count, tokens, seconds, written = by_stage.get(stage, (0, 0, 0.0, 0))
        by_stage[stage] = (
            count + 1,
            tokens + (call.prefill_tokens or 0),
            seconds + call.seconds,
            written + (call.cache_write_tokens or 0),
        )
    for stage, (count, tokens, seconds, written) in sorted(
        by_stage.items(), key=lambda row: row[1][1], reverse=True
    ):
        share = tokens / measured_prefill if measured_prefill else 0.0
        print(
            f"    {tokens:>10,} tok  {share:>5.0%}  x{count:<4d}"
            f" {seconds:7.1f}s  {written:>9,} cache-written  {stage}"
        )

    print("\n  provider time by caller (most expensive first):")
    for caller, count, seconds in census.by_caller():
        print(f"    {seconds:8.1f}s  x{count:<4d} {caller}")

    # The extrapolation, built from the SIZE-DRIVEN stages only and a fixed
    # remainder. Scaling the grand total is wrong: at two thirds REST, a linear
    # scale-up of the whole thing charges the 1.2 MB document ten times for a
    # polarity pass it only runs once.
    size_driven = sum(by_stage.get(s, (0, 0, 0.0, 0))[1] for s in _SIZE_DRIVEN)
    fixed = measured_prefill - size_driven
    per_window = size_driven / len(windows) if windows else 0.0
    print(
        f"\n  RATE — {measured_prefill:,} prefill tokens for {SOURCE_KB} KB"
        f" in {len(windows)} window(s):"
        f" {size_driven:,} size-driven ({per_window:,.0f}/window)"
        f" + {fixed:,} fixed"
    )
    if len(windows) > 1:
        target_windows = len(chunk_text(_document(1200)))
        projected = per_window * target_windows + fixed
        print(
            f"  EXTRAPOLATION (not a measurement) — 1.2 MB is"
            f" {target_windows} windows by the real chunker, so"
            f" ~{projected:,.0f} prefill tokens: {per_window * target_windows:,.0f}"
            f" size-driven + {fixed:,} fixed. Linear in windows by construction"
            f" (each window is read independently, so nothing about window 30"
            f" costs more than window 3) and the fixed part is held constant"
            f" because its context is bounded."
            f"\n    'Fixed' means NOT DRIVEN BY SOURCE SIZE — it does not mean"
            f" constant. It is driven by extraction YIELD, which is stochastic:"
            f" two runs of this probe on the identical document found 50 and 5"
            f" polarities and their non-size-driven prefill differed by 2.8x,"
            f" while the size-driven part reproduced to 0.1%. Quote the"
            f" per-window figure; a single grand total from here is a coin flip."
        )

    step2 = by_stage.get(_STEP2_LABEL, (0, 0, 0.0, 0))
    if step2[1] and measured_prefill:
        print(
            f"\n  THE LEVER — step 2 is {step2[1]:,} tokens"
            f" ({step2[1] / measured_prefill:.0%} of measured prefill,"
            f" {step2[1] / size_driven:.0%} of the size-driven part) across"
            f" {step2[0]} calls that carry the window ONLY because `isolate()`"
            f" copies step 1's history. A fresh facilitator there would cut this"
            f" row to near nothing. It is a REASONING change (step 2 would no"
            f" longer see the source), so it needs an A/B — this is the evidence"
            f" that the A/B is worth running, not a licence to take it."
        )

    _cache_verdict(census)

    print(f"\n  report: {str(report)[:600]}")

    # Assertions on coherence only, never on a duration or a token count: this
    # probe measures, it does not gate. A threshold here would fail on a slow
    # afternoon and teach the next reader to ignore the file.
    assert census.busy_s <= waited + 1.0, (
        "calls were in flight for longer than ingest ran — the intervals or the"
        " clocks disagree, so nothing derived from them can be trusted"
    )
    assert census.parallelism >= 1.0 - 1e-6, (
        "parallelism below 1.0 is arithmetically impossible — `busy_s` is"
        " over-merging"
    )
    assert account.wasted_s <= waited + 1.0, (
        "recorded retry waste exceeds the tool's own wall clock"
    )
    if len(windows) > 1:
        # The guarantee the sweep exists for, checked at the token level rather
        # than at the prompt level (that is `tests/test_surface_theses_sweep.py`):
        # no single call may carry the whole document.
        whole_document_tokens = len(document) / 4
        biggest = max((c.prefill_tokens or 0) for c in census.calls)
        assert biggest < whole_document_tokens * 0.75, (
            f"one call prefilled {biggest:,} tokens against ~{whole_document_tokens:,.0f}"
            " for the whole document — something is sending the source unsplit"
        )
