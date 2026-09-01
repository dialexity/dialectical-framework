"""Probe: of `anchor`'s wall clock, how much is work and how much is sleep?

WHY
===
r26 measured `anchor` on the weak tier at a **282.8s median, 812.5s max** over ten
single-tool rounds, and both the round write-up and `test_context_refresh_cost.py`
took that as the tool's price. The ten values were:

    36.5  38.9  43.4  43.5  107.8  457.9  807.9  808.2  812.3  812.5

Four inside 5 seconds of each other at ~810s is a ceiling, not a workload. Every
value fits ~40s of work plus a rung of `use_brain`'s ParseError ladder AS IT STOOD
THEN (10s doubling to a 120s cap = 750s over ten attempts; flat at 2s since
2026-08-27, so these sums are no longer reproducible — see the last section):
107.8 ≈ 40+70, 457.9 ≈ 40+390,
~810 ≈ 40+750 with the ladder exhausted. All six slow rounds reported `ok` with
`swallowed_errors: none`, and the whole 2.5-hour run logged zero warnings —
because ParseError was the one retry branch that never logged.

That was inference from a histogram. This probe measures it: it runs `anchor` for
real on the same tier and scenario content, with the retry accountant installed,
and prints waited / working / slept per call. `use_brain`'s ParseError branch now
logs too, so a laddering call announces itself while this runs.

READING IT
==========
- `slept` > 0 on any call: the r26 reading is confirmed for that call, and the
  archive's `anchor` medians are blends of two different quantities.
- All calls clean and all near ~40s: the fast values were the whole story and
  r26's slow ones came from something this probe does not reproduce (a provider
  bad afternoon, a longer context, sonnet-5 rather than haiku). Say that; do NOT
  quietly keep the ladder theory.
- All calls clean and all near ~810s: the ceiling is real and is NOT the retry
  ladder. That would be the most interesting outcome and the one that invalidates
  the hypothesis.

The model is printed from settings, not assumed from the tier label — r26's own
weak tier had to be recovered from the recorded model because the label does not
carry it.

    poetry run pytest tests/e2e/probe_anchor_retry_cost.py -s --real-llm

`-o log_cli=true --log-cli-level=WARNING` is worth adding: pytest shows captured
logs only on FAILURE, and this probe passes while laddering, so without it the
new ParseError warnings — which name the DTO that failed to parse, i.e. the
actual root cause — are collected and discarded. `DIALEXITY_PROBE_ANCHOR_N=1`
runs one tension instead of three when the question is only "which DTO".

RESULT, 2026-08-26 (haiku-4.5, weak tier, n=3, 21 minutes)
==========================================================
    waited 123.5s  working 46.8s  slept  70.0s  discarded 6.6s   3 parse retries
    waited 321.3s  working 41.4s  slept 270.0s  discarded 9.9s   5 parse retries
    waited 809.8s  working 40.1s  slept 750.0s  discarded 19.7s  9 parse retries

**3 of 3 calls laddered, and the sleep totals are exact ladder sums** —
10+20+40 = 70, +80+120 = 270, then the 120s cap nine times over = 750. Working
time is 40.1 / 41.4 / 46.8s: flat, tight, and the same ~40s the histogram's fast
values showed. So `anchor` costs about **41 seconds**; r26's 282.8s median and
812.5s max were 41 seconds of work plus up to 12.5 minutes of sleeping, and every
one of them still reported `ok` because the retry eventually succeeded.

The inference is now a measurement, and it stands as read.

WHICH SCHEMA (n=1 re-run with `log_cli`, 2026-08-26)
====================================================
    Parse failure on GroundingDto (attempt 1/10), backing off 10s
      — this call has now slept 10s: 1 validation error for GroundingDto
    particulars
      Field required [type=missing,
       input_value={'parameter_name': 'parti...ded before next raise.'}]

**`TetradGrounding`'s `GroundingDto`**, and the payload says what the model did:
it answered with a **parameter ENVELOPE** (`{"parameter_name": "particulars",
...}`) instead of the object (`{"particulars": "..."}`). The content was there —
the fragment ends in the person's own words, "…ded before next raise" — so this is
a wrapper defect, not a refusal or a truncation, on a single-field schema. Same
family as the double-encoding in `test_envelope_salvage.py`: the answer is
correct and the envelope is wrong, and the retry re-samples the same tendency,
which is why it can ladder all the way to the 750s cap and still succeed.

That makes the fix a schema/salvage question rather than a latency one.

AFTER THE GENERIC SALVAGE, 2026-08-27 (same model, same tensions, n=3)
=====================================================================
    waited 37.5s  working 37.5s  slept 0.0s   0 retries   salvaged
    waited 55.2s  working 40.3s  slept 10.0s  1 retry     salvaged + one retry
    waited 38.9s  working 38.9s  slept 0.0s   0 retries   salvaged

**3 of 3 calls emitted the descriptor again, and all 3 were unwrapped with zero
retries** — so the envelope is deterministic for this model/DTO pair, which is
exactly why re-asking could never fix it. 1254.6s -> 131.6s on the same work,
21 minutes -> 2m17s, and the tool's ~40s is now all the wait there is.

Read the log, not the timing, to tell salvage from luck: a clean run can mean the
model happened not to emit the envelope. The line to look for is
`Model returned GroundingDto as a parameter descriptor`. The first n=1 re-run
after the fix came back at 37.4s with NO such line — nothing was salvaged there,
the model simply behaved, and quoting it as verification would have been wrong.

A SECOND DIALECT OF THE SAME TENDENCY, found by the new raw-payload log
======================================================================
The middle call above retried once, on `TetradDto` — a SIX-field DTO, which
retires the idea that single-field schemas are the risk surface:

    "t_plus": "\\n<parameter name=\\"statement\\">Unified ownership enabling ..."

`t_plus` is an `AspectDto`, so an object was expected and the model wrote
Anthropic **tool-call XML** into the string slot, then derailed — `a_minus`,
`a_plus`, `t_minus` and the second axis never arrived. So the unifying diagnosis
is tool-call parameter framing leaking into structured output, in two dialects:
a JSON descriptor for the whole object, and an XML fragment inside one field.

Deliberately NOT given a salvage rule, and the distinction is the useful part:
that response was also TRUNCATED, so unwrapping `t_plus` would still have failed
validation. It NEEDED a re-ask, and got one for 10s. The rule that separates the
two cases is whether the fault is deterministic — a descriptor the model emits
3/3 times cannot be re-sampled away and must be salvaged; a derailment it emits
once recovers on the next attempt and must be retried. If the XML dialect ever
shows up in an otherwise complete response, that is when it earns a rule.

AND THE LADDER ITSELF WENT FLAT, 2026-08-27
===========================================
Both outcomes above say the same thing about waiting, so `_PARSE_RETRY_DELAY_S` is
now 2s with no doubling. Backoff is a congestion curve: it works because waiting
makes the next attempt more likely to succeed. A wrong response SHAPE has no such
property — the deterministic descriptor was never going to change, and the
stochastic derailment was already fixed on the next sample, having first slept 10s
for nothing.

What this means for READING this probe from here on: the exact-ladder-sum
signature that identified the fault (70 / 270 / 750) no longer exists, so a slow
`anchor` can no longer be diagnosed by arithmetic on its wall clock. Use the
`slept` column and the log lines. The sleep numbers above are history, not a
baseline — n=3 under the flat curve would have cost ~2 to 6s of sleep in total
where it cost 1090s. The remaining exposure is `retry_max` GENERATIONS (~40s each
here), which is a separate and still-open question from the naps.

WHAT THE CENSUS ADDED, AND WHY BOTH BRANCHES NOW RUN (2026-09-01)
================================================================
Everything above measures the tool from OUTSIDE: one wall clock, minus recorded
sleep. That was enough to retire the ladder, and it is not enough to optimise
anything, because ~38s of work has two possible shapes and they call for opposite
fixes. A CHAIN of nine 4s calls is shortened by removing stages; a FAN-OUT of
forty concurrent calls is shortened by asking for less. Wall clock alone cannot
tell them apart, and `call_census.py` had never been pointed at `anchor` — its
users were all explore-side.

So each call now runs under `call_census()` as well, and the number to read first
is **`parallelism` (`provider_s / busy_s`)**: at 1.0 the tool is a chain and the
lever is depth; well above 1.0 it is a fan-out and the lever is width. `depth`
estimates how many average calls deep the chain went, and `by_caller()` names
which concern to go and look at.

Both branches run, because they are structurally different tools sharing a name
and only one of them had ever been priced:
- **both-poles** (`thesis` + `antithesis`) — `IntroducePolarity` then
  `ExpandPolarity`, statically ~9 sequential rounds and 9-13 calls.
- **thesis-only** (`antithesis=None`) — `AnchorTheses` then `AnalysisPipeline`,
  statically ~40 calls, nearly all inside two fan-outs (11 mode points, then up
  to `MAX_POLARITIES_TO_EXPAND` concurrent expansions).

The static prediction is that the two land at SIMILAR wall clock despite ~4x the
calls. If they do, `anchor` is depth-bound and call-count is the wrong thing to
optimise. If thesis-only is much slower, the fan-out is not really fanning out.
Which branch the archive's measured rounds took is unrecorded (`arms.py` logs only
whether `context` was present), so this probe is the only place the two are
comparable.

RESULT, 2026-09-01 (haiku-4.5, weak tier, both branches, ~3m15s)
================================================================
Measured under one SHARED Case across both branches, which was a defect in this
probe and is fixed below — read the confound note before quoting the comparison.

    both-poles   waited 40.1s  38.9s  40.3s   calls 10  11  12
                 parallelism 1.12  1.15  1.16   depth ~8.9  ~9.6  ~10.3
    thesis-only  waited 36.8s  35.7s           calls 35  35
                 parallelism 4.15  4.25         depth ~8.4  ~8.2

**The branch with 3.2x the calls is not slower.** thesis-only buys ~148s of
provider time and spends 36.3s of wall clock; both-poles buys ~44s and spends
40.1s.

Resist the obvious way to say why, which is how this was first written: "both are
~9 stages deep, so both cost ~9 x 4s." **`depth` is an identity on the other two
columns** — `busy_s/mean_call_s` reduces to `count/parallelism`, so 10/1.12,
35/4.15 and the rest reproduce the printed depths exactly. Reading a shared depth
as the EXPLANATION of a shared wall clock restates the wall clock. Two figures
genuinely coincide (`mean_call_s` ~4s in both, `count/parallelism` ~9 in both) and
`depth` is just their ratio.

What the columns do support, stated separately for the two branches:
- **both-poles IS a chain.** parallelism 1.12-1.16 over 10-12 calls, and the
  stage-by-stage reconciliation below closes on its wall clock to within 6%. Here
  call count nearly IS the latency quantity.
- **thesis-only is NOT depth-bound, and `depth` mis-describes it.** Its 11 mode
  points are ONE dependency stage that `depth` reports as 11/4.2 ~ 2.6 stages —
  `CallCensus.depth`'s own docstring says it cannot see dependencies. Its real
  chain is short and wide.

So the honest cross-branch claim is narrower than "call count is not a latency
quantity": call count does not predict latency ACROSS the two branches, because
thesis-only's extra calls sit inside gathers. And the simplest account of the 3.8s
gap is not depth at all — **both-poles runs one serial stage pair that thesis-only
never runs**, the second `_resolve_statement` at ~5.8s, which is also lever 1
below. That the gap and the lever are the same size is corroboration, not proof.

Consequences:
- Steering the model toward one branch for speed is pointless. thesis-only buys
  ~3.4x the provider SECONDS, a different budget that this probe does not report:
  `record_call` does receive per-call prefill tokens on the non-streaming path, so
  the censuses hold them, but nothing here prints them and the rows are dropped.
- **MARGINAL calls inside an existing gather are cheap** — not "the fan-out is
  free". Eleven concurrent calls still cost `max(call)`, no concurrency cap was in
  force (`DIALEXITY_MAX_CONCURRENT_LLM_CALLS` unset, so `llm_concurrency_slot()`
  is a no-op), and the run decomposes to 4 expansions per thesis-only call, so
  `MAX_POLARITIES_TO_EXPAND = 5` was never even saturated.
- `parallelism 1.15` says only 15% of both-poles' provider time is CURRENTLY
  overlapped. It does not say the branch is out of opportunities — parallelism
  measures overlap achieved, not overlap available, and the two independent pole
  resolutions at `introduce_polarity.py:85-88` are sequential `await`s that this
  figure is precisely the evidence for.

THE CONFOUND, and why the comparison is weaker than it looks
-----------------------------------------------------------
All five calls above ran inside ONE `scope(case.sid)`, both-poles first, then
thesis-only over the SAME first two theses. So thesis-only's `FindPolarities` met
Statements, `OPPOSITE_OF` edges and Polarities that the both-poles branch had just
committed, and `_get_existing_oppositions` read HS off the existing Polarity via
`_lookup_hs_from_polarity` instead of paying for a classification. The run's own
numbers show it: `SemanticDedupDto` totals 12, of which 11 are the per-expansion
calls, leaving ONE `FindPolarities` dedup across two thesis-only runs.

The two branches were therefore priced on different graph state, and the cheaper
state belongs to the branch that came out faster. "thesis-only is not slower"
survives this; "thesis-only is faster" does not. The probe now opens a fresh Case
per branch, so these exact numbers are NOT reproducible by re-running it — that is
the point of the fix, and a re-run is owed before the comparison is quoted again.

Where the provider time goes, pooled over all five calls, with the mean this
probe implies (`total / calls` — a mean over few calls, not a distribution). The
concern column is ATTRIBUTION, not output: `CallRecord.label` renders as
"<Dto> via _call_with_response_model", so the printed table names the DTO and the
facilitator seam, and the concern behind it was traced by hand.

    CoherenceEvaluationDto      22 calls  123.1s   ~5.6s   ControlStatementsCheck
    TetradDto                   11 calls  112.3s  ~10.2s   AspectGeneration
    ModePointResultDto          22 calls   80.9s   ~3.7s   AntithesisExtraction
    SemanticDedupDto            12 calls   25.9s   ~2.2s   StatementDeduplication
    TaxonomyLocationDto          8 calls   24.1s   ~3.0s   StatementClassification
    ClassificationDto            8 calls   22.3s   ~2.8s   StatementClassification
    GroundingDto                11 calls   15.1s   ~1.4s   TetradGrounding
    ContextualizedTaxonomyDto    5 calls   13.0s   ~2.6s    3 AntithesisClassifi-
                                                           cation + 2 Antithesis-
                                                           Extraction
    AntithesisEvaluationDto      3 calls   12.8s   ~4.3s   AntithesisClassification
    HeadlineDto                  1 call     1.0s   ~1.0s   StatementHeadline

`ContextualizedTaxonomyDto` is the one row with two sources, and it is worth
knowing which: `contextualize_taxonomy` is a module-level helper shared by
`AntithesisClassification` and `AntithesisExtraction`, so 3 of the 5 came from the
both-poles branch and 2 from the thesis-only one, one per thesis.

The counts corroborate the static census: `TetradDto` 11 is consistent with one
per `ExpandPolarity` (an inference — nothing printed counts `ExpandPolarity`
invocations, and a pooled table cannot separate 3+8 from another split),
`CoherenceEvaluationDto` 22 with two per expansion, and `ModePointResultDto` 22
with 11 mode points x 2 thesis-only runs. That last one is exact rather than
approximate, which additionally proves all 11 mode branches came back non-empty.

`HeadlineDto` fired exactly ONCE across five calls, and the boundary is the reason
to trust it: `component_length` defaults to 7 and the short-circuit is `<=`, so of
the three theses only "Raise with the cap table as it stands" (8 words) pays for a
call — "Move the anchor accounts to my name" is exactly 7 and correctly does not.
Merging that call would buy nothing.

Reading the both-poles chain against these means closes it: 2 x (2.8 + 3.0) pole
resolution + 2.6 + 4.3 antithesis classification + 10.2 tetrad + 2.2 dedup + 1.4
grounding + 5.6 coherence = ~38s against 40.1s measured. That accounting is what
makes the levers costable, and it prices two of them DOWN:

- **`TetradDto` alone is ~10.2s, a quarter of the both-poles chain, and it is the
  reasoning** — one call producing all four aspects with HS and complementarity.
  Nothing to win here that is not a cut.
- **Hoisting the grounding extraction is worth ~1.4s, not ~4s.** It was ranked on
  a ~4s average stage; the actual call is the cheapest on the board. The argument
  for doing it anyway is no longer latency, and it was dropped on that basis.
- Gathering the two `_resolve_statement` calls saves one pole's ~5.8s (~14%),
  which is the largest safe structural saving available.

RETRIES: 0 of 5 calls laddered, so the retry sleep the archive records on three
post-fix `anchor` rounds — 8.1s, 9.8s and 10.2s — did NOT reproduce here. (Stated
without a denominator on purpose: whether that is 3 of 5 or 3 of 7 depends on
whether a turn whose `tool_retry_seconds` entry is labelled `discard+anchor`
counts as an `anchor` round, and nothing in `rounds.md` settles it.) The sleep
remains unexplained; do not attribute it to the salvaged `GroundingDto` on the
strength of this run.
"""

from __future__ import annotations

import logging
import os
import statistics
import time

import pytest

from e2e.config import DEFAULT_TIER_WEAK
from e2e.modelctx import using_model

from dialectical_framework.agents.advisor.tools.anchor import anchor
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import CallCensus, call_census
from dialectical_framework.utils.retry_accounting import retry_account

#: r26's scenario, weak tier, `cofounder_equity` — the cell whose ten `anchor`
#: rounds produced the histogram above. Same shape of input, so a difference in
#: cost is not a difference in the question being asked.
CONTEXT = (
    "My cofounder holds 45% of the equity. Two anchor accounts are 60% of our "
    "revenue and both CEOs call him, not me. I gave him direct feedback in March "
    "and nothing has changed since. I have to decide before the next raise."
)

TENSIONS = [
    ("Buy out the cofounder now", "Keep the partnership intact"),
    ("Move the anchor accounts to my name", "Leave the relationships where they are"),
    ("Raise with the cap table as it stands", "Fix the equity split before raising"),
]

#: How many of them to run. Three is ~2m20s now (~21 minutes before the salvage
#: and the flat curve), which is worth paying once for a median and not worth
#: paying to re-read a log line.
ANCHOR_CALLS = max(1, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_ANCHOR_N", "3"))))

#: How many of the same theses to run again with `antithesis=None`. Two rather
#: than three because the question this branch answers is its SHAPE (chain or
#: fan-out), which one call already shows and a second only confirms; the median
#: that needs n=3 is the both-poles one the archive can be compared against.
#: Settable to 0 to re-run the original probe exactly as it was.
PIPELINE_CALLS = max(
    0, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_ANCHOR_PIPELINE_N", "2")))
)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_probe_anchor_work_versus_sleep(di_container):
    # Pinned to the bench's weak tier rather than whatever `.env` holds: the
    # figures being re-checked are that tier's, and `settings.ai_model` on this
    # machine is a different model entirely.
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print("(the recorded model, not a tier label — r26's had to be recovered)")

    # The ParseError log line landed 2026-08-26 and is the point: a laddering
    # call must be audible while it happens, not reconstructed afterwards.
    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    rows = []
    with using_model(di_container, DEFAULT_TIER_WEAK):
        # A Case PER BRANCH, and this is a correction, not a tidy-up. The first
        # run of this comparison shared one Case across both branches, and since
        # thesis-only runs SECOND on the same theses, its `FindPolarities` found
        # the Statements and `OPPOSITE_OF` edges the both-poles branch had just
        # committed and read their HS straight off the existing Polarity — no
        # provider call. The two branches were therefore priced on different
        # graph state, and the cheaper state was the one whose branch came out
        # faster. Visible in that run's own numbers: `SemanticDedupDto` totalled
        # 12 where 11 were the per-expansion calls, leaving ONE dedup across two
        # thesis-only runs. Within a branch the Case is still shared, which is
        # what the r26 comparison above was measured on.
        for branch, pairs in (
            ("both-poles", TENSIONS[:ANCHOR_CALLS]),
            ("thesis-only", [(t, None) for t, _ in TENSIONS[:PIPELINE_CALLS]]),
        ):
            if not pairs:
                continue
            print(f"\n{branch}:")
            case = Case()
            case.commit()
            for thesis, antithesis in pairs:
                # The census is installed OUTSIDE the awaited call, so every task
                # the tool's internal `gather`s create inherits it: a context var
                # set before a task is copied into it, and one set after is
                # invisible to it. Getting this backwards is how a fan-out
                # measures as a chain.
                with scope(case.sid), call_census() as census, retry_account() as account:
                    started = time.monotonic()
                    await anchor(
                        thesis=thesis, antithesis=antithesis, context=CONTEXT
                    )
                    waited = time.monotonic() - started
                rows.append((branch, thesis, waited, account, census))
                print(
                    f"\n  {thesis[:38]:40}"
                    f"waited {waited:7.1f}s   "
                    f"working {max(0.0, waited - account.wasted_s):7.1f}s   "
                    f"slept {account.sleep_s:6.1f}s   "
                    f"discarded attempts {account.failed_attempt_s:6.1f}s   "
                    f"retries {account.count} {dict(account.kinds) or ''}"
                )
                # `parallelism` first, because it decides which lever is even
                # worth costing: 1.0 means shorten the chain, >1 means ask for
                # less. `busy_s` is union time, so it is the part of `waited`
                # that had a call in flight — the remainder is graph writes,
                # sleep, and framework overhead.
                print(
                    f"  {'':40}"
                    f"calls {census.count:4}   "
                    f"provider {census.provider_s:7.1f}s   "
                    f"busy {census.busy_s:7.1f}s   "
                    f"parallelism {census.parallelism:5.2f}   "
                    f"depth ~{census.depth:4.1f}   "
                    f"mean call {census.mean_call_s:5.1f}s"
                )

    for branch in ("both-poles", "thesis-only"):
        branch_rows = [r for r in rows if r[0] == branch]
        if not branch_rows:
            continue
        waits = [r[2] for r in branch_rows]
        works = [max(0.0, r[2] - r[3].wasted_s) for r in branch_rows]
        retried = [r for r in branch_rows if r[3].count]
        counts = [r[4].count for r in branch_rows]
        print(
            f"\n  {branch}: n={len(branch_rows)}"
            f"   median waited {statistics.median(waits):.1f}s"
            f"   median working {statistics.median(works):.1f}s"
            f"   median calls {statistics.median(counts):.0f}"
            f"   median parallelism {statistics.median(r[4].parallelism for r in branch_rows):.2f}"
            f"   laddered on {len(retried)}/{len(branch_rows)}"
        )

    # Pooled across branches on purpose: this names which CONCERN to go and look
    # at, and a concern shared by both branches should be read as the sum of its
    # appearances. Per-branch call counts are on the rows above.
    pooled = CallCensus(calls=[c for r in rows for c in r[4].calls])
    if pooled.count:
        print(f"\n  where the provider time went, both branches pooled:")
        for label, count, seconds in pooled.by_caller():
            print(f"    {label[:58]:60}{count:4} calls  {seconds:7.1f}s")

    print(f"\n  r26 recorded, same tier and scenario: median 282.8s, max 812.5s (n=10)")
    if not [r for r in rows if r[3].count]:
        print(
            "  NO retries observed — this run does not reproduce r26's ladder."
            " Report that, and do not carry the theory forward on r26's histogram"
            " alone."
        )

    # An assertion, so the probe is a test rather than a script: the accounting
    # must be arithmetically coherent whatever the provider did. Nothing here
    # asserts a duration — this probe measures, it does not gate.
    for branch, _, waited, account, census in rows:
        assert account.wasted_s <= waited + 1.0, (
            "recorded retry waste exceeds the call's own wall clock — the"
            " accountant is double-counting or the clocks disagree"
        )
        # A census that saw nothing means the contextvar did not reach the tool's
        # inner tasks, and every shape figure above would be a silent zero rather
        # than a reading. Worth failing on: the whole point of this addition is
        # the shape.
        assert census.count > 0, (
            f"{branch}: the census recorded no provider calls, so it was not"
            " installed where `use_brain` could see it"
        )
        # `busy_s` is a union of intervals inside one call, so it cannot exceed
        # the call's own wall clock. If it does, the intervals are wrong and
        # `parallelism` and `depth` are both meaningless.
        assert census.busy_s <= waited + 1.0, (
            f"{branch}: busy time exceeds the call's wall clock"
        )
