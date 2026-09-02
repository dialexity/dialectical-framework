"""Probe: how much overlap did gathering the two pole resolutions actually buy?

WHY
===
`probe_anchor_retry_cost.py` predicted that gathering `IntroducePolarity`'s two pole
resolutions would save ~5.8s, and measured ~3.3s. That probe recorded the ~2.5s gap
as UNEXPLAINED with two candidates it could not separate: overhead growth (freed
provider time reappearing as graph writes / framework time), or the two now-concurrent
poles CONTENDING so the pair costs more than `max(pole)`.

There is a third candidate, and it is arithmetic rather than empirical. Gathering two
coroutines does not save one pole's cost — it saves the part of the two poles' work
that ends up running SIDE BY SIDE. The ~5.8s prediction was
`mean(ClassificationDto) + mean(TaxonomyLocationDto)` pooled over 8 calls each, i.e.
an estimate of E[one pole], which is the saving only when the two poles overlap
perfectly. They cannot: each pole is a CHAIN — `ClassificationDto`, then
`TaxonomyLocationDto` only if the first came back `is_simple=False`
(`statement_classification.py:701-717`) — so if the two chains' first links differ in
length the second links start at different times and the tails hang off each end.

THE HEADLINE IS MEASURED, NOT INFERRED FROM SPANS
=================================================
The saving a gather buys is the provider time that ran concurrently, and with a
per-pole census that is directly measurable by inclusion-exclusion over the
`CallRecord` intervals:

    overlap_provider_s = busy_A + busy_B - busy_union

where each `busy` is a UNION of call intervals (`call_census.py:204-206`). That is
`|A ∩ B|` — the seconds during which both poles had a call in flight — and it is the
quantity the serial-to-gathered saving is made of. It is not an identity on the other
columns, it is not inflated by framework overhead or retry sleep (neither is a call
interval), and it does not care how long the enclosing spans were.

An earlier draft made `realized = serial - overlap_wall` the headline. That was
worthless twice over. It is identically `min(A,B) - skew`, and `skew ≈ 0` by
construction because `asyncio.gather` schedules both coroutines in the same
event-loop tick and `timed`'s first statement is the clock read — so the conclusion
was fixed before any provider call. (Same trap the sibling documents about itself:
"`depth` is an identity on the other two columns" — `probe_anchor_retry_cost.py:184-185`.)
And it was SELF-CONFIRMING in the other direction: two fully serialized 5.8s poles
read as spans 5.8 and 11.6, a spread of 5.8s, which the span arithmetic reports as a
2.9s min-vs-mean bias "explaining the whole gap" when the true cause is interference.
Queueing shows up as duration, not as skew, so any instrument built on spans books
interference as its own thesis. `overlap_provider_s` cannot: a serialized pair has an
empty intersection and reads 0.

WHAT THE SPAN STATISTICS ARE STILL FOR, AND THEIR ONE HONEST LIMIT
=================================================================
`bias = mean_pole - mean(min(A,B))` is still printed, because the ~5.8s prediction
was an E[pole] estimate and the bias is what that estimator was wrong by. But note
it is a SAMPLE IDENTITY: per row `(A+B)/2 - min(A,B) ≡ |A-B|/2` exactly, so
`bias ≡ mean_spread / 2` and the two printed lines are ONE reading, not two agreeing
ones. It is also measured on SPANS while the prediction was built from PROVIDER
means, a strictly larger quantity — so it is computed a second time from
`provider_s` and both are printed; a divergence localises the contamination. And it
is measured POST-gather to estimate what the PRE-gather prediction's bias was, which
is valid only under the null that gathering did not change the spread — the very
thing the interference hypothesis denies. Read `overlap_provider_s` first.

PRE-REGISTERED, BECAUSE "E[min] < E[pole] WHENEVER POLES VARY" IS UNFALSIFIABLE
==============================================================================
Any positive spread confirms that sentence, so on its own it would let a 0.8s bias be
written up as the explanation for a 2.5s gap. The numbers are therefore fixed here,
before the run:

    to close the gap by this mechanism alone,  E|A-B| ~= 5.0s  is required
    on poles averaging ~5.8s. Verified by simulation: iid normal at CV 0.76 gives
    bias 2.50s; at an ordinary CV of 0.25 it gives 0.82s, under a third of the gap;
    iid exponential gives E[min] = mu/2 = 2.90s, which would fit. (Normal at CV 0.76
    puts ~9.5% of its mass below zero and is not a sensible model for a duration, so
    the exponential case is the one carrying the claim.)

Two things that must NOT be read as corroboration:

1. `bias = 2.5s` and `E[min] = 3.3s` are the SAME statement rearranged, since
   `bias = mean_pole - E[min]` and the gap is `predicted(=mean_pole) - measured`. If
   the residual lands near zero, that is one finding, not two.
2. **A single parse retry satisfies the 5.0s threshold on its own.** The sibling
   records a retry costing 2.0s of sleep plus a ~3.4s discarded attempt — ~5.4s of
   span — on 2 of 3 both-poles calls, same tier, same tensions
   (`probe_anchor_retry_cost.py:312-316`). One such row in five adds ~1.1s to
   `mean_spread`; two on opposite poles reach the threshold with ZERO provider
   variance. So the bias block is computed twice and **only the retry-free subgroup
   may be quoted**, with its `n` printed beside it.

Third pre-registration: the ~3.3s being explained is a difference of MEDIANS at n=3,
two of whose calls retried, with no error bar. A residual near 1s is not
distinguishable from noise in either direction.

STRUCTURAL SPREAD IS NOT LATENCY SPREAD
=======================================
Two ways the two poles can differ in cost for reasons that have nothing to do with
provider variance, both of which would masquerade as the thesis:

- `is_simple` — no `TaxonomyLocationDto` call at all, so ~2.8s instead of ~5.8s. Read
  off the returned draft rather than inferred. On the 2026-09-01 reference run
  `TaxonomyLocationDto` count equalled `ClassificationDto` count (8 and 8), so NO
  pole classified simple and this will most likely report 0/5 — read a zero as "the
  guard did not need to fire", not as "checked and clean".
- `HeadlineDto` — `StatementHeadline` short-circuits at `component_length = 7` words
  (`statement_headline.py:90-96`, `settings.py:18`), so a pole whose text is 8 words
  makes the call and a 6-word partner does not: a ~1.0s structural spread. This is
  LIVE on tension 3 below ("Raise with the cap table as it stands" is 8 words against
  6), which is one of the three inherited from the sibling.

So the subgroup flag is `mixed_dtos` — the two poles made different DTO sets — which
subsumes both.

THE OTHER TWO CANDIDATES
========================
- **Contention.** Per-pole provider seconds against the pre-change per-DTO means for
  the DTOs that pole actually made — like-for-like. Comparing a pole's WALL span
  against a sum of provider means is not a contention test: the span also holds
  facilitator overhead, prompt assembly, retry sleeps and scheduling, so it exceeds
  the reference mechanically at zero contention.
- **Interference / serialization.** `overlap_wall` against `max(busy)` and
  `sum(busy)`. Near `max` means the poles really overlapped; near `sum` means they
  queued. This is the check that separates overlap from interference on the SPAN
  columns, and it also catches a semaphore queue, since a call is timed inside its
  slot and the queue wait therefore lands in the span but not in `busy_s`.

It measures the POLE STAGE, not the whole tool, so it cannot rule the overhead-growth
candidate in or out. If `overlap_provider_s` agrees with the ~3.3s measured at the
tool, that candidate is squeezed out by agreement rather than tested — say it that
way and do not upgrade it.

    poetry run pytest tests/e2e/probe_pole_overlap.py -s --real-llm \
        -o log_cli=true --log-cli-level=WARNING

The log flags matter for the same reason the sibling gives: this probe PASSES while
retrying, so without them the ParseError lines that name the retrying DTO are
captured and discarded, and a retry cannot be attributed — which the retry-free
subgroup above now depends on.

`DIALEXITY_PROBE_OVERLAP_N` sets how many tensions to run (default 5). n matters more
here than in most probes: the span statistics are expectations over a SPREAD, and a
spread cannot be estimated from one pair. Cost is roughly n x 40s plus retries.

RESULT (2026-09-02, haiku-4.5, n=5, 2m41s, no cap, 0 retries in 5 calls)
=======================================================================
**The min-vs-mean hypothesis is REFUTED, and the gather is bigger than predicted.**

    MEASURED OVERLAP (provider seconds that ran side by side)
        median 6.25s        (retry-free + same-DTO-mix subgroup, n=4: 5.96s)
        against 5.8s PREDICTED and 3.3s measured at the tool

    per row, spans:  serial -> gathered      min(A,B)   |A-B|    skew
        15.7 -> 8.9   6.8    2.2   +0.00
        10.8 -> 5.4   5.4    0.0   +0.00
        12.8 -> 6.5   6.3    0.1   +0.00
        12.5 -> 6.3   6.3    0.0   +0.00
        11.8 -> 6.1   5.7    0.4   +0.00

    Those are the printed figures, to the ONE decimal the report emits. An earlier
    draft of this table carried a second decimal (0.10 / 0.03 / 0.43) that the report
    never printed, and it was not merely over-precise: its median came to 0.10 against
    the summary line's 0.15s, i.e. a hand-transcribed table disagreeing with the
    computed statistic beside it. Read per-row values off the run, medians off the
    summary block; do not re-derive one from the other at this precision.

    WHICH GAP, because the base moved when the stage was measured. The 2.5s this
    probe pre-registered against is `5.8s predicted - 3.3s at the tool`, and that
    framing (and therefore the 5.0s spread threshold, which is 2 x 2.5) was fixed
    before the run. Now that the stage is measured at 6.2s freed, the stage-vs-tool
    discrepancy is `6.2 - 3.3 = 2.9s`. The mechanism's 0.33s is 13% of the first and
    11% of the second; the refutation holds either way, but quote the base you mean.

The two poles cost very nearly the SAME: mean `E|A-B|` **0.56s**, median **0.15s**,
max 2.17s, against the **5.0s** this mechanism needed. So the min-vs-mean bias is
**0.33s** of the 2.5s gap (retry-free subgroup), residual **+2.17s** — or +2.57s
against the 2.9s stage-vs-tool framing above. The
pre-registration is what makes this a refutation rather than a shrug: had the
threshold not been fixed in advance, 0.33s could have been written up as "poles do
vary, so the prediction was biased high", which is true and explains nearly none of
it.

**The gather is close to perfect and there is no interference.** Median gathered wall
6.3s against median `max(busy)` 6.3s and `sum(busy)` 12.5s — the union of the two
poles' provider intervals equals the larger pole almost exactly, on all five rows,
with a start skew of 0.000s. So the pole stage takes **12.5s serial down to 6.3s**,
i.e. it frees ~6.2s of wall clock, MORE than the ~5.8s arithmetic predicted, not less.

**Therefore the ~2.5s gap is not in the pole stage at all**, and the three candidates
this probe could test are all excluded: imperfect overlap (no — it is near-perfect),
pole spread (no — 0.33s), contention (small: retry-free poles spent 64.3s against
59.0s expected, **+9%**, which on concurrent poles costs roughly the growth in the
LARGER pole, ~0.5s of wall per call, and is itself measured against a reference pooled
from a sequential run in a different Case regime, so treat it as weak).

What is left, and neither is testable from inside the pole stage:

1. **Overhead growth downstream** — freed provider time reappearing as graph writes
   or framework time later in the tool.
2. **The 3.3s itself.** It is a difference of medians at n=3, two of whose calls
   retried, with no error bar, against a directly measured 6.2s of freed wall here.
   The instrument with the error bar is this one; the 3.3s is the loose figure in the
   comparison, and "the tool-level saving was underestimated" is as live an
   explanation as anything about the framework.

Two structural checks fired as pre-registered, which is the reason to trust the
spread: **1 of 5 rows had a mixed DTO set** — exactly tension 3, where "Raise with
the cap table as it stands" (8 words) made a `HeadlineDto` call its 6-word partner did
not, the ~1.0s asymmetry predicted above. Both word counts come from `TENSIONS` in this
file, NOT from the report, which truncates pole text to 24 chars
(`'Fix the equity split bef'`) and cannot be asked the question. And **0 poles classified `is_simple`**, as
the reference run's equal Classification/Taxonomy counts implied. Read the zero as
"the guard did not need to fire".

Do not quote `min(A,B)` or the span bias from this run as anything but a refutation:
the spread is so small that every span statistic here is near its floor.
"""

from __future__ import annotations

import logging
import os
import statistics
import time
from typing import Optional

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.tools.anchor import anchor
from dialectical_framework.agents.analyst.skills.introduce_polarity import \
    IntroducePolarity
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import (CallCensus, _union_seconds,
                                                     call_census)
from dialectical_framework.utils.retry_accounting import (RetryAccount,
                                                          retry_account)

#: Same scenario as `probe_anchor_retry_cost.py`, so pole costs are comparable with
#: the per-DTO means quoted there.
CONTEXT = (
    "My cofounder holds 45% of the equity. Two anchor accounts are 60% of our "
    "revenue and both CEOs call him, not me. I gave him direct feedback in March "
    "and nothing has changed since. I have to decide before the next raise."
)

#: The first three are `probe_anchor_retry_cost.py`'s. The last two are extra pairs
#: from the same scenario, present only to estimate the SPREAD between poles — the
#: quantity the span statistics need, which n=3 cannot pin.
#:
#: Tension 3 is the one with the live `HeadlineDto` asymmetry (8 words against 6).
TENSIONS = [
    ("Buy out the cofounder now", "Keep the partnership intact"),
    ("Move the anchor accounts to my name", "Leave the relationships where they are"),
    ("Raise with the cap table as it stands", "Fix the equity split before raising"),
    ("Tell the two CEOs myself", "Keep him as the relationship owner"),
    ("Decide before the raise", "Let the raise settle it"),
]

PROBE_N = max(1, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_OVERLAP_N", "5"))))

#: Pre-change per-DTO means, from `probe_anchor_retry_cost.py`'s 2026-09-01 pooled
#: table (`total / calls`, so a mean over few calls and not a distribution):
#: ClassificationDto 22.3s/8, TaxonomyLocationDto 24.1s/8, HeadlineDto 1.0s/1.
#:
#: Used to build each pole's EXPECTED serial provider time from the DTOs it actually
#: made, which is the only like-for-like contention test available here.
#:
#: Two limits to state when quoting it: 2 of those 8 classifications came from the
#: THESIS-ONLY branch (`AnchorTheses`), not from a pole, so a quarter of the
#: reference is work this probe never runs; and `HeadlineDto`'s "mean" is one call.
SERIAL_DTO_REFERENCE_S = {
    "ClassificationDto": 22.3 / 8,
    "TaxonomyLocationDto": 24.1 / 8,
    "HeadlineDto": 1.0,
}

#: The gap this probe exists to explain, from the sibling's 2026-09-02 run. A
#: difference of MEDIANS at n=3 — see the third pre-registration.
GAP_TO_EXPLAIN_S = 2.5

#: What the sibling measured at the tool, for the squeeze-out argument only.
MEASURED_AT_TOOL_S = 3.3

#: What the per-DTO arithmetic predicted, i.e. the E[pole] estimate that overshot.
PREDICTED_S = 5.8


class _Pole:
    """One `_classify_statement` invocation, timed and censused in isolation."""

    def __init__(
        self,
        text: str,
        start: float,
        end: float,
        census: CallCensus,
        account: RetryAccount,
        is_simple: Optional[bool],
    ) -> None:
        self.text = text
        self.start = start
        self.end = end
        self.span = end - start
        self.provider_s = census.provider_s
        self.busy_s = census.busy_s
        #: Raw call intervals, for the cross-pole intersection that is the headline.
        self.intervals = [(c.started, c.ended) for c in census.calls]
        self.retry_s = account.wasted_s
        self.retries = account.count
        #: Read off the returned draft, not inferred from the absence of a call.
        #: `None` only when the pole raised, in which case the row is discarded.
        self.is_simple = is_simple
        # DTO name only: `CallRecord.label` renders as "<Dto> via <caller>" when the
        # call had a response model, and as the bare caller when it did not
        # (`call_census.py:154-164`). So an unstructured call lands here under a
        # function name, silently contributes 0 to `expected_provider_s`, and
        # inflates the contention figure. `unknown_dtos` exists to make that visible
        # rather than let it read as contention.
        self.dtos = {
            label.split(" via ")[0]: (count, seconds)
            for label, count, seconds in census.by_caller()
        }
        self.unknown_dtos = sorted(set(self.dtos) - set(SERIAL_DTO_REFERENCE_S))

    @property
    def expected_provider_s(self) -> float:
        """Serial provider seconds this pole's OWN DTO mix would have cost before.

        Counts RECORDS, and a discarded retry attempt is a record (`record_call`
        fires before `response.parse()`), so a retrying pole's expectation grows by a
        whole extra mean and pulls the contention ratio back toward 1.0. The
        contention block therefore reports retry-free poles separately.
        """
        return sum(
            SERIAL_DTO_REFERENCE_S.get(dto, 0.0) * count
            for dto, (count, _) in self.dtos.items()
        )

    def label(self) -> str:
        mix = ",".join(
            f"{dto.replace('Dto', '')}x{count}"
            for dto, (count, _) in sorted(self.dtos.items())
        )
        simple = "simple " if self.is_simple else "complex"
        return f"{simple} [{mix or 'no calls'}]"


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_pole_overlap(di_container, monkeypatch):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")

    # A semaphore cap serialises the poles outright and the whole probe would measure
    # a queue. The wait lands in the span but NOT in `busy_s` (a call is timed inside
    # its slot), so the interference check would catch it — but only after the money
    # is spent. Each pole makes up to 2 concurrent calls, so the pair needs 4.
    cap = os.getenv("DIALEXITY_MAX_CONCURRENT_LLM_CALLS")
    print(f"DIALEXITY_MAX_CONCURRENT_LLM_CALLS={cap or 'unset (no cap)'}")
    if cap and cap.isdigit() and 0 < int(cap) < 4:
        pytest.skip(
            f"concurrency capped at {cap}; the two poles need 4 slots to overlap, so"
            " this run would measure the semaphore rather than the gather"
        )

    print(
        f"pre-registered: this mechanism needs E|A-B| ~= 5.0s to explain the"
        f" {GAP_TO_EXPLAIN_S}s gap alone, and ONLY the retry-free subgroup may be"
        " quoted against it"
    )
    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    # A per-call bucket bound at coroutine ENTRY rather than a shared list cleared
    # between calls. `IntroducePolarity` uses no `return_exceptions`, so a failing
    # pole leaves its sibling running in the background; with a shared list that
    # orphan could append after a later clear and contaminate a subsequent row.
    # Binding `sink` before the first await makes that structurally impossible.
    bucket: list[list[_Pole]] = [[]]
    original = IntroducePolarity._classify_statement

    async def timed(self, text: str, context: str):
        sink = bucket[0]
        started = time.monotonic()
        # Nested `call_census`/`retry_account`: both are STACKS whose `record_*`
        # writes to every installed level, so a scope here yields this pole's own
        # provider seconds, intervals, DTO mix and retry waste while leaving the
        # tool-level totals untouched. Verified: a sibling gather task cannot leak in,
        # because each task copies the context at creation.
        with call_census() as pole_census, retry_account() as pole_account:
            draft = None
            try:
                draft = await original(self, text, context)
                return draft
            finally:
                sink.append(
                    _Pole(
                        text,
                        started,
                        time.monotonic(),
                        pole_census,
                        pole_account,
                        draft.classification.is_simple if draft is not None else None,
                    )
                )

    monkeypatch.setattr(IntroducePolarity, "_classify_statement", timed)

    rows = []
    with using_model(di_container, DEFAULT_TIER_WEAK):
        for thesis, antithesis in TENSIONS[:PROBE_N]:
            # A Case per call. NOTE this makes `waited` NOT comparable with the
            # sibling probe's rows, which share a Case within a branch. It is also
            # NOT an accretion control: the pole stage does no graph lookup at all,
            # so a shared Case would not have made a later pole cheaper. What it
            # removes is `StatementDeduplication`'s growing vocabulary, downstream of
            # everything measured here.
            case = Case()
            case.commit()
            bucket[0] = []
            with scope(case.sid), call_census() as census, retry_account() as account:
                started = time.monotonic()
                try:
                    await anchor(thesis=thesis, antithesis=antithesis, context=CONTEXT)
                except Exception as exc:  # noqa: BLE001
                    # Catch so one failed call does not discard the other four
                    # real-LLM calls. Without this a raising pole propagates out of
                    # the loop and the whole run is lost.
                    print(f"\n  {thesis[:38]:40}FAILED: {type(exc).__name__}: {exc}")
                    continue
                waited = time.monotonic() - started

            poles = bucket[0]
            if len(poles) != 2:
                print(
                    f"\n  {thesis[:38]:40}SKIPPED: {len(poles)} pole span(s), expected 2"
                )
                continue

            first, second = sorted(poles, key=lambda p: p.span)
            serial = first.span + second.span
            overlap_wall = max(p.end for p in poles) - min(p.start for p in poles)
            skew = overlap_wall - second.span

            # THE HEADLINE, by inclusion-exclusion over the raw call intervals:
            # |A n B| = |A| + |B| - |A u B|. The provider seconds that genuinely ran
            # side by side, which is what the gather bought.
            busy_union = _union_seconds(
                [interval for p in poles for interval in p.intervals]
            )
            busy_sum = sum(p.busy_s for p in poles)
            overlap_provider = busy_sum - busy_union

            rows.append(
                {
                    "thesis": thesis,
                    "waited": waited,
                    "shorter": first.span,
                    "longer": second.span,
                    "serial": serial,
                    "overlap_wall": overlap_wall,
                    "skew": skew,
                    "available": first.span,  # min(A, B) on spans
                    "spread": second.span - first.span,
                    "overlap_provider": overlap_provider,
                    "busy_sum": busy_sum,
                    "busy_union": busy_union,
                    "busy_max": max(p.busy_s for p in poles),
                    "provider_min": min(p.provider_s for p in poles),
                    "provider_spread": abs(poles[0].provider_s - poles[1].provider_s),
                    "provider_mean": statistics.mean(p.provider_s for p in poles),
                    "provider_sum": sum(p.provider_s for p in poles),
                    "expected_sum": sum(p.expected_provider_s for p in poles),
                    "mixed_dtos": set(poles[0].dtos) != set(poles[1].dtos),
                    "any_simple": any(p.is_simple for p in poles),
                    "pole_retry_s": sum(p.retry_s for p in poles),
                    "pole_retries": sum(p.retries for p in poles),
                    "unknown_dtos": sorted({d for p in poles for d in p.unknown_dtos}),
                    "start_skew": abs(poles[0].start - poles[1].start),
                    "poles": list(poles),
                }
            )

            print(f"\n  {thesis[:38]:40}waited {waited:6.1f}s   "
                  f"tool busy {census.busy_s:6.1f}s   provider {census.provider_s:6.1f}s"
                  f"   parallelism {census.parallelism:4.2f}"
                  f"   retries {account.count} ({account.wasted_s:.1f}s)")
            for p in poles:
                print(
                    f"  {'':40}pole {p.span:5.1f}s  provider {p.provider_s:5.1f}s"
                    f"  busy {p.busy_s:5.1f}s  vs expected {p.expected_provider_s:5.1f}s"
                    f"  retry {p.retry_s:4.1f}s  {p.label()}  {p.text[:24]!r}"
                )
            print(
                f"  {'':40}OVERLAP PROVIDER {overlap_provider:5.1f}s"
                f"  (busy {poles[0].busy_s:.1f}+{poles[1].busy_s:.1f}"
                f" - union {busy_union:.1f})"
            )
            print(
                f"  {'':40}spans: serial {serial:5.1f}s -> gathered {overlap_wall:5.1f}s"
                f"   min(A,B) {first.span:5.1f}s   |A-B| {second.span - first.span:5.1f}s"
                f"   skew {skew:+5.2f}s"
            )

    assert rows, "no call produced two pole spans; nothing to report"

    def med(key: str) -> float:
        return statistics.median(r[key] for r in rows)

    clean = [r for r in rows if r["pole_retry_s"] == 0 and not r["mixed_dtos"]]
    print(f"\n  n={len(rows)}   retry-free and same-DTO-mix: n={len(clean)}")

    # ------------------------------------------------------------------ headline
    print(
        f"\n  MEASURED OVERLAP (the saving the gather bought):"
        f" median {med('overlap_provider'):.2f}s"
    )
    print(
        f"    against {MEASURED_AT_TOOL_S}s measured at the tool and {PREDICTED_S}s"
        f" predicted by the per-DTO arithmetic"
    )
    print(
        f"    median busy: pole sum {med('busy_sum'):.1f}s, union"
        f" {med('busy_union'):.1f}s, larger pole {med('busy_max'):.1f}s"
    )
    if clean:
        print(
            f"    retry-free subgroup (n={len(clean)}): median"
            f" {statistics.median(r['overlap_provider'] for r in clean):.2f}s"
        )
    print(
        "    Not an identity on the other columns and not inflated by retry sleep or"
        "\n    framework overhead: a serialized pair has an empty intersection and"
        " reads 0."
    )

    # -------------------------------------------------------------- span statistics
    pole_spans = [p.span for r in rows for p in r["poles"]]
    mean_pole = statistics.mean(pole_spans)
    mean_available = statistics.mean(r["available"] for r in rows)
    bias = mean_pole - mean_available
    print(
        f"\n  SPAN BIAS (secondary; `bias == mean_spread / 2` exactly, so this and the"
        f"\n  spread below are ONE reading): mean pole {mean_pole:.2f}s - mean min(A,B)"
        f" {mean_available:.2f}s = {bias:.2f}s"
    )
    spreads = [r["spread"] for r in rows]
    print(
        f"    mean spread E|A-B| {statistics.mean(spreads):.2f}s"
        f"  median {statistics.median(spreads):.2f}s"
        f"  min {min(spreads):.2f}s  max {max(spreads):.2f}s"
        + (
            f"  stdev {statistics.stdev(spreads):.2f}s"
            if len(spreads) > 1
            else "  stdev n/a"
        )
    )
    print(f"    against the ~5.0s this mechanism needed to close the gap alone")

    # The same bias from PROVIDER seconds — the level the ~5.8s prediction was built
    # at. Spans are a strictly larger quantity, so a divergence localises the
    # contamination.
    provider_bias = statistics.mean(r["provider_mean"] for r in rows) - statistics.mean(
        r["provider_min"] for r in rows
    )
    print(
        f"    same bias computed on PROVIDER seconds: {provider_bias:.2f}s"
        f"  (mean provider spread {statistics.mean(r['provider_spread'] for r in rows):.2f}s)"
    )

    if clean:
        clean_spreads = [r["spread"] for r in clean]
        clean_bias = statistics.mean(clean_spreads) / 2
        print(
            f"    QUOTABLE (retry-free, same DTO mix, n={len(clean)}):"
            f" mean spread {statistics.mean(clean_spreads):.2f}s -> bias"
            f" {clean_bias:.2f}s, residual {GAP_TO_EXPLAIN_S - clean_bias:+.2f}s"
        )
    else:
        print(
            f"    NOT QUOTABLE: every row either retried or had a mixed DTO mix, both"
            "\n    of which manufacture spread. The span bias says nothing here."
        )

    retried = [r for r in rows if r["pole_retry_s"] > 0]
    if retried:
        print(
            f"    {len(retried)}/{len(rows)} row(s) retried, median waste"
            f" {statistics.median(r['pole_retry_s'] for r in retried):.1f}s — a single"
            "\n    retry is ~5.4s of span and meets the 5.0s threshold by itself."
        )

    print(
        f"    NOTE: residual ~= 0 and `overlap_provider ~= {MEASURED_AT_TOOL_S}s` are"
        " the same statement rearranged, not two findings."
    )

    # ------------------------------------------------------------------ structural
    mixed = [r for r in rows if r["mixed_dtos"]]
    print(
        f"\n  STRUCTURAL SPREAD: {len(mixed)}/{len(rows)} row(s) had poles with"
        f" DIFFERENT DTO sets ({sum(r['any_simple'] for r in rows)} with an"
        f" `is_simple` pole)."
    )
    print(
        "    A mixed mix is a structural spread, not a latency one. An `is_simple`"
        "\n    count of 0 means the guard did not need to fire, NOT that it was"
        " checked and clean."
    )

    # ------------------------------------------------------------------ contention
    retry_free_poles = [p for r in rows for p in r["poles"] if p.retry_s == 0]
    provider_sum = sum(p.provider_s for p in retry_free_poles)
    expected_sum = sum(p.expected_provider_s for p in retry_free_poles)
    print(
        f"\n  CONTENTION (retry-free poles only, n={len(retry_free_poles)}):"
        f" provider {provider_sum:.1f}s against {expected_sum:.1f}s expected"
        f" from the pre-change per-DTO means"
    )
    if expected_sum:
        print(
            f"    {provider_sum - expected_sum:+.1f}s,"
            f" {(provider_sum / expected_sum - 1) * 100:+.0f}%"
        )
    else:
        print("    no expected baseline available; ratio not computable")
    print(
        "    Reference limits: 2 of its 8 classifications came from the thesis-only"
        "\n    branch, and HeadlineDto's mean is a single call."
    )
    unknown = sorted({d for r in rows for d in r["unknown_dtos"]})
    if unknown:
        print(
            f"    INVALID: pole(s) made call(s) with no reference mean"
            f" ({', '.join(unknown)}), so `expected` understates and the figure above"
            "\n    is inflated by an unknown amount. Do not quote it."
        )

    # ---------------------------------------------------------------- interference
    print(
        f"\n  OVERLAP vs INTERFERENCE (spans): median gathered"
        f" {med('overlap_wall'):.1f}s against median max(busy) {med('busy_max'):.1f}s"
        f" and median sum(busy) {med('busy_sum'):.1f}s"
    )
    print(
        "    Near max(busy) = the two poles really overlapped. Near sum(busy) = they"
        "\n    queued. Confounded by retry sleep, which is in the wall and not in busy"
        f"\n    — median pole retry waste {med('pole_retry_s'):.1f}s."
    )
    print(f"    median start skew {med('start_skew'):.3f}s (gather should make this ~0)")

    print(
        f"\n  for reference only, NOT a row of this table (different Case regime):"
        f" the tool-level measurement was ~{MEASURED_AT_TOOL_S}s"
    )

    # Coherence only — this probe measures, it does not gate.
    for r in rows:
        # The claim the whole `skew ~= 0` argument rests on, and the only one of these
        # that can fail on a wrongly-built row: `gather` starts both in one tick.
        assert r["start_skew"] < 0.5, (
            f"{r['thesis'][:30]}: the two poles started {r['start_skew']:.2f}s apart,"
            " but `asyncio.gather` schedules both in the same event-loop tick — so"
            " these two spans are not one call's poles"
        )
        # Fires exactly when the two intervals are DISJOINT, which is the orphan case.
        # (For overlapping intervals `max(end) - min(start) <= A + B` always holds.)
        assert r["overlap_wall"] <= r["serial"] + 0.05, (
            f"{r['thesis'][:30]}: gathered wall {r['overlap_wall']:.1f}s exceeds the"
            f" serial sum {r['serial']:.1f}s, impossible for two intervals that"
            " overlap — so they do not, and these are not one call's poles"
        )
        assert r["overlap_provider"] >= -0.05, (
            f"{r['thesis'][:30]}: negative intersection"
            f" {r['overlap_provider']:.2f}s, so the interval union is wrong"
        )
        for p in r["poles"]:
            assert p.busy_s <= p.span + 0.05, (
                f"{r['thesis'][:30]}: a pole was provider-busy {p.busy_s:.1f}s inside a"
                f" {p.span:.1f}s span, so the nested census is seeing another pole's"
                " calls and every per-pole figure is wrong"
            )
