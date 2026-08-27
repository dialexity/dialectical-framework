"""Probe: is `explore` slow because it makes MANY calls, or FEW in a long chain?

WHY
===
r26 measured `explore` at a **196.0s median** on the weak tier and nothing could
say what that bought. The same round measured `anchor` at 282.8s, which turned out
to be ~41s of work plus 750s of pointless sleeping (`probe_anchor_retry_cost.py`).
With the parse curve flat that particular blend is gone, so `explore`'s remaining
cost is work — and "work" splits two ways that look identical on a wall clock and
have opposite fixes:

- **VOLUME.** Many calls, already fanned out. Wall clock is set by the longest
  dependent path, so the lever is asking for LESS (fewer wheels deepened, fewer
  insight bands, fewer audits). Adding workers does nothing; the workers are there.
- **DEPTH.** Few calls in a sequential chain. Wall clock IS the chain, so the lever
  is restructuring it — and no amount of concurrency helps.

The framework claims both on paper. `ExplorationPipeline` runs wheels concurrently
and `ExploreTransformations` parallelizes edge pairs, Phase 1 edges, Phase 2
candidates and audits — that is the volume side. Meanwhile each Transformation is
documented as **4 sequential `TransformationGeneration` calls + 2 audits**, and a
1-PP wheel carries `2 × len(INSIGHT_CATEGORIES)` = 6 Transformations — that is the
depth side. Which dominates is not derivable from the docs.

WHAT IT MEASURES, AND THE MISTAKE TO AVOID READING IT
=====================================================
`utils/call_census.py` around the tool. **Two levers, and they are not the same
lever** — the first version of this probe treated parallelism as a verdict and got
this exactly backwards on its own first run, printing "fan-out, so ask for less"
about a tool whose wall clock was a chain:

- **LATENCY follows `busy_s` and `depth`.** `busy_s` is wall time with at least one
  call in flight, and it is a floor on the tool's duration under its current
  dependency structure. `depth` (`busy_s / mean_call_s`) estimates how many
  sequential stages that floor is made of. Latency shrinks only by taking calls off
  the critical path — fewer stages, or faster ones.
- **COST follows `provider_s`.** That is total provider time bought, concurrent
  calls counted separately. Asking for less (fewer deepened wheels, insight bands,
  audits) reduces `provider_s` directly, and reduces latency ONLY where it removes
  a stage.
- **`parallelism` (`provider_s / busy_s`) is neither.** It reports the compression
  already achieved — how much wider than one the work runs. High parallelism with
  high depth means both are true at once: wide stages, many of them. It answers
  "is there headroom left in concurrency?", not "what should I fix?".

`wall − busy_s` is everything that was NOT a provider call — graph writes and
orchestration. Note it ALSO absorbs any wait for the `utils/concurrency.py`
semaphore, so check `DIALEXITY_MAX_CONCURRENT_LLM_CALLS` before reading it as
orchestration; unset (the default) it contributes nothing.

The per-caller table is the actionable output: it names which concern to go and
look at, ordered by provider time rather than by call count, because one 90s call
outranks thirty 1s ones for that purpose.

READING IT HONESTLY
===================
- **1 PP is the FLOOR of explore's cost, not its median.** The default is one
  perspective (`DIALEXITY_PROBE_EXPLORE_PP`), which is the circular-causality base
  case: one cycle, one self-referencing wheel, 6 Transformations. r26's 196.0s
  median came from whatever the Advisor happened to have mapped. So a small
  `waited` here does NOT refute the 196.0s figure — but `parallelism` and `depth`
  DO transfer, because widening N adds parallel branches without lengthening the
  per-Transformation chain. That asymmetry is the reason 1 PP is worth measuring:
  it answers the actionable half cheaply.
- **`ExpandPolarity` setup is deliberately outside the census and the timer.**
  Only the tool under test is measured.
- A retry account runs alongside, so a laddering call cannot masquerade as work —
  the mistake that made r26's `anchor` median unreadable.

    poetry run pytest tests/e2e/probe_explore_cost.py -s --real-llm

`-o log_cli=true --log-cli-level=WARNING` is worth adding for the same reason as
the `anchor` probe: this PASSES while retrying, so pytest otherwise collects and
discards the warnings that name a failing DTO. `DIALEXITY_PROBE_EXPLORE_PP=2`
widens to two perspectives (12 Transformations — roughly double the provider time,
and the run to make if the question is specifically about the 196.0s median).

RESULT, 2026-08-27 — BOTH, and the audit is the line item
=========================================================
Weak tier, 1 PP, 6 Transformations::

    waited 103.8s   working 95.7s   slept 2.0s   retries 1 {'parse': 1}
    calls 47   provider 367.8s   in-flight 88.6s   not in a call 15.2s
    PARALLELISM 4.15x   depth ~11.3 stages   mean call 7.8s

**Neither lever wins; both readings are true.** 85% of the wall clock had a call in
flight, ~11 stages deep — so the latency is structural and there is no missing
`gather` to add. And the fan-out is genuinely working: 367.8s of provider time
compressed 4.15x. `explore` is wide stages, many of them.

The per-caller table is where the actionable finding is, and it took the DTO label
to see it at all::

    147.4s  x12  TransitionAuditDto        <- 40% of ALL provider time
     56.8s  x6   ReSideCompletionDto
     46.2s  x6   CategoryReframingDto
     40.2s  x6   AcMinusCompletionDto
     27.0s  x6   ActionCandidateDto
     23.3s  x6   HsScoringDto
     13.9s  x2   SynthesisPairDto
     11.8s  x2   ApexPairDto
      1.2s  x1   _AutoPresetResolutionDto via BuildWheels._resolve_auto_preset

**The audit is the most expensive concern in the framework by a factor of three** —
12 calls (2 per Transformation, exactly as `CLAUDE.md` documents) at ~12.3s each
against a 7.8s mean. It is expensive on BOTH levers, which is rare: it dominates
`provider_s`, and being the closing stage of each Transformation chain it also sits
on the critical path. Every other row is 6 calls — one per Transformation — so the
audit is the only place where "ask for less" is available without removing a
generation stage.

**ACTED ON (2026-08-27): the audit is now opt-in and off by default** —
`settings.audit_transformations`. Not batched, removed from the default path: a
blast-radius trace found no code consumer at all (the `FeasibilityEstimation` is
rendered where present and omitted where absent; the critique Rationale it writes
has no reader anywhere), so the cheapest correct answer to "ask for less" was to
stop asking. **A re-run of this probe will therefore show 35 calls, not 47, and
`TransitionAuditDto` absent from the table** — that is the change, not a
regression. Set `DIALEXITY_AUDIT_TRANSFORMATIONS=true` to reproduce the numbers
above. Two consequences worth carrying: the per-caller table is now 6 calls in
every row, so the concern that dominates provider time is whichever generation
stage is slowest rather than a self-evaluation layer; and the depth estimate drops
by the audit's stage, since it closed each Transformation's chain.

The concern itself did not go away — `audit_feasibility` runs it on the one or two
pathways a person asks about (2 calls each, capped at 4 pathways, free on a repeat
ask). So the spend this probe measured has not moved elsewhere in `explore`: it
moved out of the build entirely and into whatever fraction of conversations raise
achievability, which is the number worth measuring next if this line item ever
looks large again.

Two things this run also surfaced, neither of them about cost:

- `SynthesisPairDto` returned `s_plus` and omitted required `s_minus`. A
  MISSING-FIELD defect, not an envelope one — `_salvage_envelope` correctly
  declined, since no rule may invent a field the model never sent. Under the flat
  parse curve it cost 2s; the old 10s→120s ladder would have charged 10s for the
  same single retry, and 150s had it failed four times as it did on the previous
  run of this probe. Worth fixing in the prompt, not in the retry loop.
- Twelve `Rationale <hash> has a hash but no row in the database` warnings from
  `relationship_manager.py:393`. Not diagnosed here — could be a probe-setup
  artefact of committing outside a pipeline, or a genuine integrity bug.
"""

from __future__ import annotations

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
from dialectical_framework.graph.nodes.case import Case
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.scope_context import scope
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.retry_accounting import retry_account

#: r26's scenario, so a cost measured here is comparable to the 196.0s median
#: rather than to a scenario of this probe's own invention.
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

#: How many perspectives to weave. One is the base case and the floor of the cost;
#: two is what `advisor_max_perspectives_per_exploration` allows per call and is
#: the shape r26's median came from. Capped at the list above.
PP_COUNT = max(1, min(len(TENSIONS), int(os.getenv("DIALEXITY_PROBE_EXPLORE_PP", "1"))))


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(3600)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_explore_volume_versus_depth(di_container):
    print(f"\nmodel under test: {DEFAULT_TIER_WEAK}")
    print("(the recorded model, not a tier label — r26's had to be recovered)")
    print(f"perspectives woven: {PP_COUNT}")
    if os.getenv("DIALEXITY_MAX_CONCURRENT_LLM_CALLS"):
        print(
            "  NOTE: the concurrency semaphore is SET, so `not in a call` below"
            " includes queueing and must not be read as orchestration."
        )

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    case = Case()
    case.commit()

    with scope(case.sid), using_model(di_container, DEFAULT_TIER_WEAK):
        # Setup, outside both instruments: only the tool under test is measured.
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

        with call_census() as census, retry_account() as account:
            started = time.monotonic()
            report, transformation_hashes = await run_exploration_detailed(
                perspective_hashes=perspective_hashes,
                intent=INTENT,
                nexus_hash=None,
            )
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
    print(f"  transformations built: {len(set(transformation_hashes))}")

    # Both levers, always, and never a single verdict word: the first version of
    # this block branched on `parallelism` alone and announced "fan-out, so ask for
    # less" about a run whose wall clock was a 13-deep chain. Reporting one lever
    # as THE answer is the same failure that let r26's medians travel without their
    # interpretation, committed one layer up.
    if census.count == 0:
        print("  NO calls recorded — the census is not wired. Fix that before reading anything else.")
    else:
        chain_share = census.busy_s / waited if waited > 0 else 0.0
        print(
            f"\n  LATENCY lever — {census.busy_s:.1f}s of the {waited:.1f}s wall"
            f" ({chain_share:.0%}) had a call in flight, about {census.depth:.0f}"
            f" stages deep at {census.mean_call_s:.1f}s a stage. That is the floor"
            f" under the current dependency structure; it moves only by removing"
            f" stages from the critical path or making them faster."
        )
        print(
            f"  COST lever — {census.provider_s:.1f}s of provider time across"
            f" {census.count} calls, compressed {census.parallelism:.2f}x into"
            f" {census.busy_s:.1f}s. Asking for less cuts THIS number directly, and"
            f" cuts latency only where it removes a stage."
        )
        if census.parallelism > 2.0 and census.depth > 6:
            print(
                "  Both are large, so both readings are true at once: wide stages,"
                " many of them. Concurrency is already doing real work here — the"
                " remaining latency is structural, not a missing `gather`."
            )

    print("\n  provider time by caller (most expensive first):")
    for caller, count, seconds in census.by_caller():
        print(f"    {seconds:8.1f}s  x{count:<4d} {caller}")

    # Assertions only on coherence, never on a duration: this probe measures, it
    # does not gate. A latency threshold here would fail on a slow afternoon and
    # teach the next reader to ignore it.
    assert census.count > 0, "explore made no LLM calls at all — setup is wrong"
    assert census.busy_s <= waited + 1.0, (
        "calls were in flight for longer than the tool ran — the intervals or the"
        " clocks disagree, so nothing derived from them can be trusted"
    )
    assert census.parallelism >= 1.0 - 1e-6, (
        "parallelism below 1.0 is arithmetically impossible (provider time cannot"
        " be less than the union of its own intervals) — `busy_s` is over-merging"
    )
    assert account.wasted_s <= waited + 1.0, (
        "recorded retry waste exceeds the tool's own wall clock"
    )
