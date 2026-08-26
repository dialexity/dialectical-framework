"""Probe: of `anchor`'s wall clock, how much is work and how much is sleep?

WHY
===
r26 measured `anchor` on the weak tier at a **282.8s median, 812.5s max** over ten
single-tool rounds, and both the round write-up and `test_context_refresh_cost.py`
took that as the tool's price. The ten values were:

    36.5  38.9  43.4  43.5  107.8  457.9  807.9  808.2  812.3  812.5

Four inside 5 seconds of each other at ~810s is a ceiling, not a workload. Every
value fits ~40s of work plus a rung of `use_brain`'s ParseError ladder (10s
doubling to a 120s cap = 750s over ten attempts): 107.8 ≈ 40+70, 457.9 ≈ 40+390,
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
family as the double-encoding in `test_double_encoded_response.py`: the answer is
correct and the envelope is wrong, and the retry re-samples the same tendency,
which is why it can ladder all the way to the 750s cap and still succeed.

That makes the fix a schema/salvage question rather than a latency one, and it is
NOT made here: `_salvage_double_encoded` sets the precedent for unwrapping exactly
one known-bad envelope when the payload validates, but widening what the framework
accepts from a model is a reasoning-layer decision with its own review.
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

#: How many of them to run. Three is ~21 minutes when they ladder, which is worth
#: paying once for a median and not worth paying to re-read a log line.
ANCHOR_CALLS = max(1, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_ANCHOR_N", "3"))))


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

    case = Case()
    case.commit()

    rows = []
    with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
        for thesis, antithesis in TENSIONS[:ANCHOR_CALLS]:
            with retry_account() as account:
                started = time.monotonic()
                await anchor(
                    thesis=thesis, antithesis=antithesis, context=CONTEXT
                )
                waited = time.monotonic() - started
            rows.append((thesis, waited, account))
            print(
                f"\n  {thesis[:38]:40}"
                f"waited {waited:7.1f}s   "
                f"working {max(0.0, waited - account.wasted_s):7.1f}s   "
                f"slept {account.sleep_s:6.1f}s   "
                f"discarded attempts {account.failed_attempt_s:6.1f}s   "
                f"retries {account.count} {dict(account.kinds) or ''}"
            )

    waits = [r[1] for r in rows]
    works = [max(0.0, r[1] - r[2].wasted_s) for r in rows]
    retried = [r for r in rows if r[2].count]
    print(
        f"\n  n={len(rows)}   median waited {statistics.median(waits):.1f}s"
        f"   median working {statistics.median(works):.1f}s"
        f"   laddered on {len(retried)}/{len(rows)} calls"
    )
    print(f"  r26 recorded, same tier and scenario: median 282.8s, max 812.5s (n=10)")
    if not retried:
        print(
            "  NO retries observed — this run does not reproduce r26's ladder."
            " Report that, and do not carry the theory forward on r26's histogram"
            " alone."
        )

    # An assertion, so the probe is a test rather than a script: the accounting
    # must be arithmetically coherent whatever the provider did. Nothing here
    # asserts a duration — this probe measures, it does not gate.
    for _, waited, account in rows:
        assert account.wasted_s <= waited + 1.0, (
            "recorded retry waste exceeds the call's own wall clock — the"
            " accountant is double-counting or the clocks disagree"
        )
