"""The same-arm placebo: does this judge pay for words when the ARM is held?

    poetry run python tests/e2e/probe_same_arm_placebo.py           # the plan, free
    poetry run python tests/e2e/probe_same_arm_placebo.py --read    # the verdict, free
    poetry run pytest tests/e2e/probe_same_arm_placebo.py -s --real-llm   # 32 judge calls

RESULT (2026-09-17, wave 1, 32 pairs) — added after the run; everything from
"WHY THIS EXISTS" down was written before any judge call and is unedited.
============================================================================
**CONFOUND REFUTED. Slope -0.133 rubric steps per 1,000 assistant words, CI
[-0.569, +0.303]** (t=-0.65, residual sd 0.860, ICC by stem +0.09 so deff 1.08).
The interval excludes the archive's cross-arm +1.137, the marquee set's +3.268,
AND the +0.569 registered below as consequential, while containing zero — at power
1.00 against the first of those. With the arm held constant, **words buy nothing**,
so the cross-arm length slope travels with the ARM and `read_length_confound.py`'s
adjusted column must NOT be adopted: subtracting it deletes real effect. The
marquee `A1.5 vs A1` reading therefore goes back to its RAW +0.514 and its sizing
problem (~68 pairs), not to the length-matched +0.095.

Checks: mean composite delta **-0.000** [-0.310, +0.310], so the two branch runs
are exchangeable as this design assumes; tie rate 31.8% against the cross-arm
26.7%, inside the attenuation guard; position split exactly 16/16. Slot bias came
out **-0.181** — same sign as the +0.35 to +0.40 Y-slot advantage `judge._x_is_a`
was built against, and this is the first population where nothing else can explain
it. Secondary: r=**+0.79** over the 12 dimensions (+0.76 to +0.83 leave-one-out)
at `placebo = 0.39 x cross-arm - 0.51`, so the SHAPE of the judge's length
response reproduces and the LEVEL does not — and a near-uniform offset across all
12 dimensions is what an arm effect travelling with length looks like, not a judge
habit. Wave 2 was registered as conditional on INDETERMINATE; wave 1 decided, so
the remaining 142 pairs stay unjudged. Full write-up: `rounds.md`,
`### placebo-w1`.

WHY THIS EXISTS — IT IS THE ONE THING `read_length_confound.py` CANNOT SETTLE
============================================================================
That file measured a length slope in every corner of the archive: **29 of 36
(stem, arm-pair) sets positive, pooled within-set +1.14 rubric steps per 1,000
assistant words over 530 pairs** (t=+8.53), and **+3.27** on the 24 pairs that
carry the marquee `A1.5 vs A1` floor question, where it takes the raw +0.514 down
to +0.095 [-0.21, +0.40] at gap zero. Its own closing paragraph says why no
adjustment can be adopted off that: a slope is a correlation, and length is
either a

  * **CONFOUNDER** — the judge pays for words, and the adjusted figure is then
    the honest one; or a
  * **MEDIATOR** — the graph makes the arm say more useful things and length is
    the channel the gain arrives through, and adjusting DELETES the effect.

Telling them apart needs a comparison where the manipulation is absent and only
length moves. The archive contains **zero same-arm comparisons** across every
stem, so it cannot be read off what has already been paid for. This probe builds
that comparison.

WHAT A SAME-ARM PAIR IS, AND WHY IT IS EXCHANGEABLE
===================================================
Every multi-session scenario runs two BRANCHES off one opening: `wobble_a` and
`wobble_b` each re-run the base `decide` session before diverging. So one
(arm, tier, scenario, replicate) cell holds **two independent samples of the same
script from the same arm** — same prompt, same model, same simulator beats, same
build. Under the design's own logic their expected quality difference is zero and
which one is called A is arbitrary; what differs is generation noise, and one
component of that noise is how much the assistant said. `A1.5` replicate 1 of
`weave-offturn` is 1,781 words in one branch and 2,033 in the other.

That is the placebo. Judge the two against each other with the same instrument
that produced every number above, regress the composite delta on the word gap,
and read the slope in a population where NO arm manipulation exists.

WHAT IT HOLDS CONSTANT, AND WHAT IT DOES NOT — SAY THIS BESIDE THE RESULT
========================================================================
It holds the ARM, not the CONTENT. Within one arm a run that had more to say may
both say more and deserve more, so a positive same-arm slope is not by itself
proof of judge bias — it is proof that **length pays whoever writes it, with no
manipulation in the picture.** That is exactly the quantity an adjustment
decision needs: if the manipulation-free slope matches the cross-arm slope, then
the cross-arm slope carries no arm-specific information and A1.5's margin is not
separable from its verbosity. If the manipulation-free slope is flat, the
cross-arm slope travels with the arm and adjusting for it would delete a real
effect. Neither reading requires knowing whether the judge is "biased".

The stronger design — one transcript against a length-trimmed copy of ITSELF —
is available for a SET of extracted items (`probe_step2_isolate_ab.py` trims a
candidate list) and not for a conversation: dropping turns from the middle of an
exchange does not shorten it, it breaks it, and trimming the tail tests coverage
of the ending. So content-identical is out of reach here and provenance-identical
is what this buys.

PRE-REGISTERED — WRITTEN BEFORE ANY JUDGE CALL, WITH THE SIZING MEASURED
========================================================================
**Population.** Every same-arm cross-branch pair in `results/` on the session
label the two branches SHARE, deduplicated by transcript fingerprint (the
re-judged stems hold byte-identical transcripts: 203 raw candidates collapse to
**174**), excluding any cell `RunRecord.invalid_as_evidence` flags — the dead-cell
hazard `read_length_confound.py` documents is worse here, since an empty
transcript is at once the shortest and the worst-scoring point available.

**Side assignment is by BRANCH NAME, never by length.** `wobble_a`'s record is A.
Assigning the longer side to A would make every gap positive and silently convert
the slope question into an intercept question.

**Wave 1 (n=32), fixed before the run:** all 12 same-arm pairs of the two stems
and two arms the marquee reading is about (`weave-offturn` and
`feasibility-offturn`, A1 and A1.5 — this is the 6+6 design this probe was
scoped as), plus the largest-|gap| remaining pairs, at most 2 per stem, to 32.
Enrichment is on the COVARIATE, which cannot bias a slope, and the outcome does
not exist for any candidate — the archive has never judged a same-arm pair, so
there is nothing to select on even by accident. The per-stem cap stops one
noisy round supplying the fit.

**Power, from measured inputs rather than hoped-for ones.** The archive's own
pooled within-set residual sd of this composite is **0.838** rubric steps (530
pairs, 36 sets), and wave 1's gap spread is known exactly because the selection
is deterministic: sd 766 words over 32 pairs. That gives se(slope) = **0.20 per
1,000 words**, so power is **~0.82** at the consequential threshold below and
**~1.00** at the archive slope. This is the step `power.py`'s own entry in the
skill says the archive keeps skipping, and it is exact here rather than
conditional on an unmeasured premise, because both inputs are already measured.

**PRIMARY endpoint.** OLS slope of the structural composite delta (mean over
non-NI dimensions, exactly `read_length_confound`'s composite) on the assistant
word gap, over wave 1. Interval: flat, and design-effect-corrected on the
residual ICC clustered by STEM when deff > 1 — the corrected one decides.

  * **CONFOUND CONFIRMED** — CI excludes 0 AND point estimate >= **+0.57** per
    1,000 words (half the archive's +1.14). Reading: at least half the cross-arm
    length slope reproduces with no manipulation at all, so the marquee delta is
    not separable from verbosity and the ADJUSTED figures become the honest read
    with the raw ones as the caveat.
  * **CONFOUND REFUTED** — CI excludes +1.14 AND contains 0. Reading: without the
    manipulation there is no length payment, the cross-arm slope travels with the
    arm, and adjusting would delete a real effect: the RAW figures stand.
  * **REVERSAL** — CI entirely below 0. Length is penalised within arm; treat as
    REFUTED and say so separately, because it also means the cross-arm positive
    slope cannot be a property of the judge alone.
  * **INDETERMINATE** — anything else, explicitly including the underpowered
    outcome where the CI contains both 0 and +1.14. Registering this null band
    rather than only a success bar is what keeps a dead hypothesis from
    surviving on "needs more data".

**ATTENUATION GUARD, asymmetric on purpose.** Same-arm transcripts are more alike,
and a judge that answers "tie" more often compresses every delta toward zero,
which biases toward REFUTED and not toward CONFIRMED. Archive-wide the
dimension-level tie rate is **26.7%** (1,922 of 7,197 scores; 27.2% on the
marquee stems alone). If wave 1's tie rate exceeds that by more than 15 points,
**REFUTED is withheld** and reported as attenuation-limited INDETERMINATE.
CONFIRMED needs no such guard: a slope found despite compression is real.

**SECONDARY, registered, not decisive.** The cross-arm slope has a SHAPE, and it
is not a blanket halo — measured free off the archive before this probe ran, per
1,000 words: actionability +1.76, paired_recipe +1.57, non_triviality +1.28,
entanglement +1.21, tension_coverage +1.10, cross_turn_coherence +0.98,
blindspot_specificity +0.94, earned_confidence +0.88, decision_closure +0.61,
convergence +0.44, warmth +0.07, and **conversational_fit NEGATIVE at -0.64**
(t=-6.30). The judge discounts length exactly where its own rubric tells it to
("natural conversation at appropriate length") and pays for it on the substance
dimensions. So the question is not "is there a halo" but "does the same
dimension-by-dimension response appear with no manipulation": Pearson r over the
12 dimensions between wave 1's slope vector and the frozen vector above, and
r >= +0.60 alongside a positive primary reads as the SAME mechanism reproduced
without an arm difference.

**CHECKS.** (1) Exchangeability: the mean composite delta over wave 1 must be
within +-0.30 of zero — branch A is arbitrary, so a larger mean means the two
branch runs are not exchangeable (an order or drift effect), which is a caveat on
the primary rather than an invalidation, and it is a threshold this design could
realistically miss. (2) Slot bias, reported raw: same-arm pairs are the archive's
first clean instrument for it, since the true delta is zero in expectation, and
`judge._x_is_a` was built against a measured +0.35 to +0.40 Y-slot advantage.
Wave 1's arm groups are all even-sized, so the alternation is exact and the split
must come out 16/16. (3) Every rationale is saved; a slope with no reading of the
notes behind it is a number, per this bench's own rule.

**WAVE 2, registered now so pooling cannot be a post-hoc rescue.** If wave 1 is
INDETERMINATE, judge ALL remaining deduped candidates (142) with no change to the
instrument, and the POOLED read over wave 1 + wave 2 is final. If wave 1 decides,
wave 2 is not run.

The judge model is `config.judge_model`, whose default has not changed since the
harness was created (`git log -S DEFAULT_JUDGE` returns exactly the commit that
added it), which is what makes a slope measured today comparable to the archive's.

WHERE THE OUTPUT GOES, AND WHY NOT INTO `results/` PROPER
=========================================================
`results/placebo/`, a SUBDIRECTORY. Every archive-wide reader globs
`results/*.json` non-recursively, and a saved `Comparison` with `arm_a == arm_b`
would enter `read_pooled`, `across_runs`, `noise_floor` and `read_length_confound`
itself as an ordinary arm pair — a placebo silently pooled into the very figures
it exists to interpret. The subdirectory is invisible to all of them.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import statistics as st
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.models import NON_INFERIORITY_DIMENSIONS, RunRecord  # noqa: E402
from e2e.read_length_confound import (  # noqa: E402
    ARCHIVE_SLOPE_PER_WORD,
    _regress,
    assistant_words,
)
from e2e.read_pooled import _ci, _icc, _t95  # noqa: E402
from e2e.report import load_records  # noqa: E402

RESULTS = E2E_DIR / "results"
PLACEBO_DIR = RESULTS / "placebo"

#: The stems and arms the marquee length reading is about. Their same-arm pairs
#: are taken WHOLE rather than sampled: a placebo for a specific published number
#: has to contain the cells that number was computed on.
MARQUEE_STEMS = ("weave-offturn", "feasibility-offturn")
MARQUEE_ARMS = ("A1", "A1.5")

WAVE_ONE_N = 32
#: No stem may supply more than this outside the marquee block, so one round's
#: generation noise cannot become the fit.
PER_STEM_CAP = 2

#: Half the archive's pooled within-set cross-arm slope (+1.137 per 1,000 words).
#: The CONSEQUENTIAL threshold, not the instrument's reach: at this value half of
#: every published length adjustment is reproducible with no manipulation, which
#: is enough to change which figure gets quoted.
CONSEQUENTIAL_SLOPE_PER_WORD = ARCHIVE_SLOPE_PER_WORD / 2

#: Pooled within-set residual sd of the structural composite over the archive's
#: 530 cross-arm pairs in 36 sets (measured 2026-09-17). Used for sizing only —
#: the run reports its own.
ARCHIVE_RESIDUAL_SD = 0.838

#: Dimension-level tie rate of the archive's cross-arm judgements: 1,922 of 7,197
#: scores. The attenuation guard's baseline.
CROSS_ARM_TIE_RATE = 0.267
TIE_ATTENUATION_MARGIN = 0.15

#: Exchangeability check on the mean composite delta (rubric steps).
EXCHANGEABILITY_MAX = 0.30

#: Registered minimum correlation for "the same dimension-by-dimension response".
VECTOR_R_MIN = 0.60

#: Cross-arm length slope PER DIMENSION, rubric steps per 1,000 assistant words,
#: pooled within-set over the archive (2026-09-17, same 36 sets as the composite
#: figure). FROZEN HERE BEFORE THE PROBE RAN so the secondary comparison cannot be
#: tuned to the result. Note the shape: `conversational_fit` is NEGATIVE and
#: `warmth` is flat, so this judge is not applying a blanket length halo — it pays
#: on substance and discounts on fit, exactly as its prompt asks.
CROSS_ARM_DIMENSION_SLOPE: dict[str, float] = {
    "actionability": +1.764,
    "paired_recipe": +1.570,
    "non_triviality": +1.284,
    "entanglement": +1.207,
    "tension_coverage": +1.098,
    "cross_turn_coherence": +0.981,
    "blindspot_specificity": +0.937,
    "earned_confidence": +0.879,
    "decision_closure": +0.610,
    "convergence": +0.442,
    "warmth": +0.067,
    "conversational_fit": -0.638,
}


# --- candidates (free) --------------------------------------------------------


@dataclass
class Pair:
    """One same-arm cross-branch pair, before any judging."""

    stem: str
    arm: str
    tier: str
    scenario_key: str
    replicate: int
    label: str
    branch_a: str
    branch_b: str
    words_a: int
    words_b: int
    #: sha256 prefixes of the two transcripts, in (A, B) order. The dedup key:
    #: a re-judged stem re-saves the same transcripts under a new name, and
    #: counting them twice would double a data point rather than add one.
    fingerprint: tuple[str, str] = ("", "")
    scores: dict[str, tuple[float, float]] = field(default_factory=dict)
    notes: dict[str, str] = field(default_factory=dict)
    overall_note: str = ""
    x_side: str = ""
    error: str = ""

    @property
    def gap(self) -> int:
        return self.words_a - self.words_b

    @property
    def cell(self) -> str:
        return f"{self.arm}|{self.tier}|{self.scenario_key}|{self.replicate}"

    @property
    def delta(self) -> float:
        """Structural composite, A minus B. `read_length_confound`'s composite."""
        return composite(self.scores)


def composite(scores: dict[str, tuple[float, float]]) -> float:
    """Mean (A - B) over the dimensions the headline is made of.

    Identical to `read_length_confound._align`'s rule — NON_INFERIORITY dimensions
    are excluded — because a placebo scored on a different composite than the
    figure it interprets is not a placebo for it.
    """
    deltas = [
        a - b
        for dimension, (a, b) in scores.items()
        if dimension not in NON_INFERIORITY_DIMENSIONS
    ]
    return st.fmean(deltas) if deltas else float("nan")


def _transcript(session: dict) -> str:
    return "\n\n".join(
        f"USER: {turn.get('user') or ''}\n\nASSISTANT: {turn.get('assistant') or ''}"
        for turn in session["turns"]
    )


def _scenario_resolves(key: str) -> bool:
    from e2e.scenarios import scenarios_for

    try:
        return bool(scenarios_for([key]))
    except Exception:  # noqa: BLE001 — a key retired since the run was saved
        return False


def candidates() -> tuple[list[Pair], list[str]]:
    """(deduped candidate pairs, notes about what was dropped and why).

    Deterministic: sorted by the pair's own coordinates, so wave 1's selection is
    reproducible from the archive alone with no stored state.
    """
    notes: list[str] = []
    seen: dict[tuple[str, str], Pair] = {}
    raw = 0
    unresolved: set[str] = set()
    for path in sorted(RESULTS.glob("*.json")):
        if path.name.endswith("-runs.json"):
            continue
        try:
            payload = load_records(path)
        except Exception:  # noqa: BLE001
            notes.append(f"{path.stem}: unreadable")
            continue
        runs = payload.get("runs") or []
        try:
            dead = {
                (r.arm.value, r.tier, r.replicate)
                for r in (RunRecord.model_validate(x) for x in runs)
                if r.invalid_as_evidence
            }
        except Exception as exc:  # noqa: BLE001 — too old to validate
            notes.append(f"{path.stem}: run records do not validate ({type(exc).__name__})")
            continue
        groups: dict[tuple, list[dict]] = {}
        for record in runs:
            if record.get("error"):
                continue
            key = (
                record["arm"],
                record["tier"],
                record["scenario_key"],
                record["replicate"],
            )
            groups.setdefault(key, []).append(record)
        for key, members in sorted(groups.items()):
            # Exactly two records under two distinct branch names. Anything else
            # is not a two-branch cell and has no same-arm pair in it.
            if len(members) != 2:
                continue
            if len({m.get("branch") or "-" for m in members}) != 2:
                continue
            if (key[0], key[1], key[3]) in dead:
                continue
            if not _scenario_resolves(key[2]):
                unresolved.add(key[2])
                continue
            first, second = sorted(members, key=lambda m: m.get("branch") or "-")
            shared = sorted(
                {s["label"] for s in first["sessions"]}
                & {s["label"] for s in second["sessions"]}
                # A branch session is a DIFFERENT script in the two records, so it
                # is not exchangeable and must never enter this population.
                - {first.get("branch"), second.get("branch")}
            )
            for label in shared:
                session_a = first["sessions"][
                    [s["label"] for s in first["sessions"]].index(label)
                ]
                session_b = second["sessions"][
                    [s["label"] for s in second["sessions"]].index(label)
                ]
                words_a, words_b = assistant_words(session_a), assistant_words(session_b)
                if not words_a or not words_b:
                    continue
                raw += 1
                fingerprint = (
                    hashlib.sha256(_transcript(session_a).encode()).hexdigest()[:16],
                    hashlib.sha256(_transcript(session_b).encode()).hexdigest()[:16],
                )
                if fingerprint in seen:
                    continue
                seen[fingerprint] = Pair(
                    stem=path.stem,
                    arm=key[0],
                    tier=key[1],
                    scenario_key=key[2],
                    replicate=key[3],
                    label=label,
                    branch_a=first.get("branch") or "-",
                    branch_b=second.get("branch") or "-",
                    words_a=words_a,
                    words_b=words_b,
                    fingerprint=fingerprint,
                )
    if unresolved:
        notes.append(
            f"scenario keys no longer defined, cells skipped: {sorted(unresolved)}"
        )
    notes.append(f"{raw} raw candidates deduplicated to {len(seen)} by transcript")
    pairs = sorted(
        seen.values(),
        key=lambda p: (p.arm, p.stem, p.scenario_key, p.replicate, p.label),
    )
    return pairs, notes


def wave_one(pairs: list[Pair]) -> list[Pair]:
    """The pre-registered 32. Pure and deterministic — see the docstring's plan."""
    marquee = [
        p for p in pairs if p.stem in MARQUEE_STEMS and p.arm in MARQUEE_ARMS
    ]
    chosen = list(marquee)
    per_stem: dict[str, int] = {}
    for p in marquee:
        per_stem[p.stem] = per_stem.get(p.stem, 0) + 1
    rest = [p for p in pairs if p not in marquee]
    # Enrichment on |gap|; ties broken by the deterministic coordinate order so
    # two runs of this function cannot disagree.
    for p in sorted(rest, key=lambda p: (-abs(p.gap), p.arm, p.stem, p.replicate)):
        if len(chosen) >= WAVE_ONE_N:
            break
        if per_stem.get(p.stem, 0) >= PER_STEM_CAP:
            continue
        per_stem[p.stem] = per_stem.get(p.stem, 0) + 1
        chosen.append(p)
    return sorted(
        chosen, key=lambda p: (p.arm, p.stem, p.scenario_key, p.replicate, p.label)
    )


def wave_two(pairs: list[Pair], wave1: list[Pair]) -> list[Pair]:
    taken = {p.fingerprint for p in wave1}
    return [p for p in pairs if p.fingerprint not in taken]


# --- sizing (free) ------------------------------------------------------------


def _normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def power_for(pairs: list[Pair], slope_per_word: float, residual_sd: float) -> float:
    """Two-sided 0.05 power to see `slope_per_word` on these pairs' gaps.

    Exact given the two inputs, and both are MEASURED: the gaps are known before
    any call because selection is deterministic, and the residual sd comes off the
    archive's own 530 cross-arm pairs. This is the calculation the archive's own
    review notes say gets skipped, and the one that was conditional on an unmeasured
    premise the one time it was run.
    """
    gaps = [p.gap for p in pairs]
    if len(gaps) < 3:
        return float("nan")
    mean_gap = st.fmean(gaps)
    sxx = sum((g - mean_gap) ** 2 for g in gaps)
    se = residual_sd / math.sqrt(sxx)
    z = abs(slope_per_word) / se
    return 1 - _normal_cdf(1.96 - z) + _normal_cdf(-1.96 - z)


# --- the read (free) ---------------------------------------------------------


def _fit(pairs: list[Pair]) -> dict | None:
    rows = [{"gap": p.gap, "delta": p.delta} for p in pairs if p.scores]
    return _regress(rows)


def _deff_by_stem(pairs: list[Pair], fit: dict) -> tuple[float, float]:
    """(residual ICC clustered by stem, design effect).

    Clustered by STEM rather than by replicate: after deduplication each pair is a
    distinct set of transcripts, and what pairs still share is the round that
    produced them — one build, one day's provider conditions, one simulator.
    """
    clusters: dict[object, list[float]] = {}
    scored = [p for p in pairs if p.scores]
    for pair, residual in zip(scored, fit["residuals"]):
        clusters.setdefault(pair.stem, []).append(residual)
    icc = _icc(clusters)
    if icc is None:
        return float("nan"), 1.0
    return icc[0], max(1.0, icc[1])


def _slope_interval(fit: dict, deff: float) -> tuple[float, float, int]:
    """(lo, hi, df used) for the slope, with clustering priced in.

    Same treatment `read_pooled` gives a mean: inflate the standard error by
    sqrt(deff) and take t from the EFFECTIVE n. Never narrower than the flat
    interval — a negative ICC must not buy precision.
    """
    if deff <= 1:
        df = fit["df"]
        half = _t95(df) * fit["se_slope"]
        return fit["slope"] - half, fit["slope"] + half, df
    effective = max(3, round(fit["n"] / deff))
    df = effective - 2
    half = _t95(df) * fit["se_slope"] * math.sqrt(deff)
    return fit["slope"] - half, fit["slope"] + half, df


def tie_rate(pairs: list[Pair]) -> tuple[int, int]:
    """(tied dimension scores, total) over every judged dimension."""
    tied = total = 0
    for pair in pairs:
        for a, b in pair.scores.values():
            total += 1
            tied += a == b
    return tied, total


def slot_bias(pairs: list[Pair]) -> tuple[float, int, int]:
    """(mean X-side minus Y-side composite, n with A in X, n with A in Y).

    The archive's cleanest possible read on position bias: over exchangeable pairs
    the true difference is zero, so whatever this returns is the slot.
    """
    values = [
        pair.delta if pair.x_side == "a" else -pair.delta
        for pair in pairs
        if pair.scores
    ]
    x_a = sum(1 for p in pairs if p.scores and p.x_side == "a")
    x_b = sum(1 for p in pairs if p.scores and p.x_side == "b")
    return (st.fmean(values) if values else float("nan")), x_a, x_b


def dimension_slopes(pairs: list[Pair]) -> dict[str, tuple[float, int]]:
    """dimension -> (slope per 1,000 words, n). Simple OLS, no centering: these
    pairs are one set."""
    out: dict[str, tuple[float, int]] = {}
    dimensions = {d for p in pairs for d in p.scores}
    for dimension in sorted(dimensions):
        rows = [
            {"gap": p.gap, "delta": p.scores[dimension][0] - p.scores[dimension][1]}
            for p in pairs
            if dimension in p.scores
        ]
        fit = _regress(rows)
        if fit is not None:
            out[dimension] = (fit["slope"] * 1000, fit["n"])
    return out


def _pearson(xs: list[float], ys: list[float]) -> float:
    if len(xs) < 3:
        return float("nan")
    mx, my = st.fmean(xs), st.fmean(ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx and syy else float("nan")


def verdict(
    lo: float, hi: float, slope: float, tie_share: float
) -> tuple[str, list[str]]:
    """The registered decision, and the reasons it came out that way.

    Pure, so the bars can be pinned by a test and cannot drift into whatever the
    run produced.
    """
    reasons: list[str] = []
    attenuated = tie_share > CROSS_ARM_TIE_RATE + TIE_ATTENUATION_MARGIN
    if lo > 0 and slope >= CONSEQUENTIAL_SLOPE_PER_WORD:
        reasons.append(
            f"CI [{lo * 1000:+.3f},{hi * 1000:+.3f}] excludes 0 and the estimate "
            f"{slope * 1000:+.3f} reaches the consequential "
            f"{CONSEQUENTIAL_SLOPE_PER_WORD * 1000:+.3f} per 1,000 words"
        )
        return "CONFOUND CONFIRMED", reasons
    if hi < 0:
        reasons.append(
            f"CI [{lo * 1000:+.3f},{hi * 1000:+.3f}] lies entirely below zero — "
            "length is PENALISED with the arm held constant"
        )
        return "REVERSAL (refuted, and the other way)", reasons
    if hi < ARCHIVE_SLOPE_PER_WORD and lo < 0 < hi:
        if attenuated:
            reasons.append(
                f"would have refuted, but the tie rate {tie_share:.1%} exceeds the "
                f"cross-arm {CROSS_ARM_TIE_RATE:.1%} by more than "
                f"{TIE_ATTENUATION_MARGIN:.0%} — compression biases toward this "
                "verdict, so it is withheld"
            )
            return "INDETERMINATE (attenuation-limited)", reasons
        reasons.append(
            f"CI [{lo * 1000:+.3f},{hi * 1000:+.3f}] excludes the archive's "
            f"{ARCHIVE_SLOPE_PER_WORD * 1000:+.3f} and contains 0"
        )
        return "CONFOUND REFUTED", reasons
    reasons.append(
        f"CI [{lo * 1000:+.3f},{hi * 1000:+.3f}] does not separate 0 from the "
        f"archive's {ARCHIVE_SLOPE_PER_WORD * 1000:+.3f} — the registered null band"
    )
    return "INDETERMINATE", reasons


# --- persistence -------------------------------------------------------------


def save(pairs: list[Pair], *, wave: int, judge_model: str) -> Path:
    from e2e.report import build_provenance

    PLACEBO_DIR.mkdir(parents=True, exist_ok=True)
    path = PLACEBO_DIR / f"wave{wave}.json"
    path.write_text(
        json.dumps(
            {
                "wave": wave,
                "judge_model": judge_model,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "build": build_provenance(),
                "rows": [
                    {
                        "stem": p.stem,
                        "arm": p.arm,
                        "tier": p.tier,
                        "scenario_key": p.scenario_key,
                        "replicate": p.replicate,
                        "label": p.label,
                        "branch_a": p.branch_a,
                        "branch_b": p.branch_b,
                        "words_a": p.words_a,
                        "words_b": p.words_b,
                        "fingerprint": list(p.fingerprint),
                        "x_side": p.x_side,
                        "scores": {k: list(v) for k, v in p.scores.items()},
                        "notes": p.notes,
                        "overall_note": p.overall_note,
                        "error": p.error,
                    }
                    for p in pairs
                ],
            },
            indent=2,
        )
    )
    return path


def load(wave: int) -> tuple[list[Pair], str]:
    path = PLACEBO_DIR / f"wave{wave}.json"
    payload = json.loads(path.read_text())
    pairs = []
    for row in payload["rows"]:
        pair = Pair(
            stem=row["stem"],
            arm=row["arm"],
            tier=row["tier"],
            scenario_key=row["scenario_key"],
            replicate=row["replicate"],
            label=row["label"],
            branch_a=row["branch_a"],
            branch_b=row["branch_b"],
            words_a=row["words_a"],
            words_b=row["words_b"],
            fingerprint=tuple(row["fingerprint"]),
        )
        pair.scores = {k: (v[0], v[1]) for k, v in row["scores"].items()}
        pair.notes = row.get("notes") or {}
        pair.overall_note = row.get("overall_note") or ""
        pair.x_side = row.get("x_side") or ""
        pair.error = row.get("error") or ""
        pairs.append(pair)
    return pairs, payload.get("judge_model", "(not recorded)")


# --- printing ----------------------------------------------------------------


def print_plan() -> int:
    pairs, notes = candidates()
    chosen = wave_one(pairs)
    print("=" * 78)
    print("SAME-ARM PLACEBO — the plan (free, no judge calls)")
    print("=" * 78)
    for note in notes:
        print(f"  {note}")
    print(f"  candidates {len(pairs)} in {len({p.stem for p in pairs})} stems; "
          f"wave 1 selects {len(chosen)}, wave 2 holds "
          f"{len(wave_two(pairs, chosen))}")
    print()
    print(f"  {'stem':30} {'arm':5} {'tier':6} {'scenario':18} {'rep':>3} "
          f"{'A':>6} {'B':>6} {'gap':>6}")
    for p in chosen:
        print(f"  {p.stem[:30]:30} {p.arm:5} {p.tier:6} {p.scenario_key[:18]:18} "
              f"{p.replicate:3d} {p.words_a:6d} {p.words_b:6d} {p.gap:+6d}")
    gaps = [p.gap for p in chosen]
    sxx = sum((g - st.fmean(gaps)) ** 2 for g in gaps)
    se = ARCHIVE_RESIDUAL_SD / math.sqrt(sxx)
    print()
    print(f"  gap sd {st.stdev(gaps):.0f} words, mean {st.fmean(gaps):+.0f}; "
          f"se(slope) {se * 1000:+.3f} per 1,000 words at the archive's "
          f"residual sd {ARCHIVE_RESIDUAL_SD}")
    for name, slope in (
        ("consequential (half archive)", CONSEQUENTIAL_SLOPE_PER_WORD),
        ("archive within-set", ARCHIVE_SLOPE_PER_WORD),
        ("marquee set's own (+3.27)", 0.00327),
    ):
        print(f"    power at {name:30} {slope * 1000:+6.3f}/1kw: "
              f"{power_for(chosen, slope, ARCHIVE_RESIDUAL_SD):.2f}")
    print()
    print("  Arm balance (the X/Y alternation is exact only in an even group):")
    counts: dict[str, int] = {}
    for p in chosen:
        counts[p.arm] = counts.get(p.arm, 0) + 1
    for arm, n in sorted(counts.items()):
        print(f"    {arm:6} {n:3d} {'even' if n % 2 == 0 else 'ODD — one residual'}")
    return 0


def print_read(waves: list[int]) -> int:
    pairs: list[Pair] = []
    models: set[str] = set()
    for wave in waves:
        try:
            loaded, model = load(wave)
        except FileNotFoundError:
            print(f"wave {wave} has not been judged — "
                  f"{PLACEBO_DIR / f'wave{wave}.json'} does not exist")
            return 1
        pairs.extend(loaded)
        models.add(model)
    scored = [p for p in pairs if p.scores]
    failed = [p for p in pairs if not p.scores]

    print("=" * 78)
    print(f"SAME-ARM PLACEBO — wave {'+'.join(str(w) for w in waves)} "
          f"— judge {', '.join(sorted(models))}")
    print("=" * 78)
    if failed:
        print(f"  {len(failed)} pair(s) failed to judge and are OUT of every "
              f"figure below:")
        for p in failed:
            print(f"    {p.stem} {p.arm} rep{p.replicate}: {p.error}")
    print(f"  {'stem':28} {'arm':5} {'rep':>3} {'X':>2} {'A':>6} {'B':>6} "
          f"{'gap':>6} {'delta':>7}")
    for p in scored:
        print(f"  {p.stem[:28]:28} {p.arm:5} {p.replicate:3d} "
              f"{p.x_side.upper():>2} {p.words_a:6d} {p.words_b:6d} "
              f"{p.gap:+6d} {p.delta:+7.3f}")

    fit = _fit(scored)
    if fit is None:
        print("\n  NOT FITTABLE — too few pairs, or a gap that barely varies.")
        return 1
    icc, deff = _deff_by_stem(scored, fit)
    lo, hi, df = _slope_interval(fit, deff)
    flat_half = _t95(fit["df"]) * fit["se_slope"]
    residual_sd = st.stdev(fit["residuals"])
    tied, total = tie_rate(scored)
    tie_share = tied / total if total else float("nan")

    print()
    print("  PRIMARY — slope of the structural composite on the word gap")
    print(f"    pairs {fit['n']}   residual sd {residual_sd:.3f} "
          f"(archive cross-arm {ARCHIVE_RESIDUAL_SD})   r {fit['r']:+.2f}   "
          f"r2 {fit['r'] ** 2:.2f}")
    print(f"    SLOPE {fit['slope'] * 1000:+.3f} per 1,000 words   "
          f"flat CI [{(fit['slope'] - flat_half) * 1000:+.3f},"
          f"{(fit['slope'] + flat_half) * 1000:+.3f}]   "
          f"t={fit['slope'] / fit['se_slope']:+.2f}")
    print(f"    residual ICC by stem {icc:+.2f}, deff {deff:.2f} -> "
          f"DECIDING CI [{lo * 1000:+.3f},{hi * 1000:+.3f}] on df {df}")
    print(f"    for comparison: archive cross-arm "
          f"{ARCHIVE_SLOPE_PER_WORD * 1000:+.3f}, marquee set's own +3.270, "
          f"consequential {CONSEQUENTIAL_SLOPE_PER_WORD * 1000:+.3f}")
    label, reasons = verdict(lo, hi, fit["slope"], tie_share)
    print()
    print(f"  REGISTERED VERDICT: {label}")
    for reason in reasons:
        print(f"    - {reason}")

    print()
    print("  CHECKS")
    mean_delta = st.fmean(p.delta for p in scored)
    ci = _ci([p.delta for p in scored]) or (float("nan"), float("nan"))
    ok = abs(mean_delta) <= EXCHANGEABILITY_MAX
    print(f"    exchangeability: mean composite delta {mean_delta:+.3f} "
          f"CI [{ci[0]:+.3f},{ci[1]:+.3f}] — "
          f"{'within' if ok else 'OUTSIDE'} +-{EXCHANGEABILITY_MAX:.2f}")
    bias, x_a, x_b = slot_bias(scored)
    print(f"    slot bias (X minus Y, true delta zero in expectation): "
          f"{bias:+.3f}   split {x_a}/{x_b}")
    print(f"    tie rate {tied}/{total} = {tie_share:.1%} against the archive's "
          f"{CROSS_ARM_TIE_RATE:.1%} — "
          f"{'compression risk' if tie_share > CROSS_ARM_TIE_RATE + TIE_ATTENUATION_MARGIN else 'comparable'}")

    print()
    print("  SECONDARY — is it the same dimension-by-dimension response?")
    slopes = dimension_slopes(scored)
    shared = [d for d in CROSS_ARM_DIMENSION_SLOPE if d in slopes]
    print(f"    {'dimension':24} {'placebo':>9} {'cross-arm':>10} {'n':>4}")
    for dimension in sorted(shared, key=lambda d: -CROSS_ARM_DIMENSION_SLOPE[d]):
        slope, n = slopes[dimension]
        print(f"    {dimension:24} {slope:+9.3f} "
              f"{CROSS_ARM_DIMENSION_SLOPE[dimension]:+10.3f} {n:4d}")
    ys = [slopes[d][0] for d in shared]
    xs = [CROSS_ARM_DIMENSION_SLOPE[d] for d in shared]
    r = _pearson(ys, xs)
    print(f"    Pearson r over {len(shared)} dimensions: {r:+.2f} "
          f"(registered >= {VECTOR_R_MIN:+.2f} reads as the same mechanism)")
    # SHAPE vs LEVEL. A correlation only says the ORDERING survived. Regressing
    # the placebo's vector on the frozen one splits that into how much of each
    # dimension's response reproduces (the gain) and how much of the whole vector
    # does not (the offset) — and a uniform offset across all 12 dimensions is
    # what an arm effect travelling with length looks like, not a judge habit.
    fit_vector = _regress(
        [{"gap": x, "delta": y} for x, y in zip(xs, ys)]
    )
    if fit_vector is not None:
        print(f"    placebo = {fit_vector['slope']:+.2f} x cross-arm "
              f"{fit_vector['intercept']:+.2f}: the ORDERING reproduces at "
              f"{fit_vector['slope']:.0%} of its cross-arm size, on a level "
              f"{fit_vector['intercept']:+.2f} away")
    # r over 12 slopes each estimated from the same n pairs is not a stable
    # statistic; the leave-one-out range says whether one dimension is carrying it.
    loo = [
        _pearson(
            [y for d, y in zip(shared, ys) if d != drop],
            [x for d, x in zip(shared, xs) if d != drop],
        )
        for drop in shared
    ]
    print(f"    leave-one-dimension-out r ranges {min(loo):+.2f} to {max(loo):+.2f} "
          f"(dropped one at a time — one leverage point can make this number up)")

    print()
    print("  PER ARM (descriptive — no arm has the n to carry a slope alone)")
    print(f"    {'arm':6} {'n':>3} {'slope':>9} {'mean gap':>9} {'mean delta':>11}")
    for arm in sorted({p.arm for p in scored}):
        group = [p for p in scored if p.arm == arm]
        group_fit = _fit(group)
        slope = f"{group_fit['slope'] * 1000:+9.3f}" if group_fit else "        -"
        print(f"    {arm:6} {len(group):3d} {slope} "
              f"{st.fmean(p.gap for p in group):+9.0f} "
              f"{st.fmean(p.delta for p in group):+11.3f}")

    if label.startswith("INDETERMINATE") and 2 not in waves:
        print()
        print("  WAVE 2 IS NOW OWED, and it was registered before wave 1 ran: judge")
        print("  every remaining deduped candidate with no instrument change and")
        print("  read the POOLED result. Pooling was not invented after seeing this.")
    return 0


# --- the judged lane ---------------------------------------------------------


def _records_for(pair: Pair) -> tuple[RunRecord, RunRecord]:
    """The two branch records behind one pair, re-validated from the archive.

    Re-read rather than carried through `Pair`: the transcripts are large, the
    plan lane must stay cheap, and the fingerprint pins that what is judged is
    what was selected.
    """
    payload = load_records(RESULTS / f"{pair.stem}.json")
    members = [
        RunRecord.model_validate(r)
        for r in payload["runs"]
        if r["arm"] == pair.arm
        and r["tier"] == pair.tier
        and r["scenario_key"] == pair.scenario_key
        and r["replicate"] == pair.replicate
    ]
    by_branch = {m.branch or "-": m for m in members}
    return by_branch[pair.branch_a], by_branch[pair.branch_b]


async def judge_wave(di_container, pairs: list[Pair], judge_model: str) -> None:
    """Fill `pairs` in place. One outer `using_model`, so this can run concurrent.

    `modelctx.using_model` mutates a PROCESS-GLOBAL container, and the runner's
    docstring is explicit that two concurrent cells would answer on each other's
    model. Holding the judge model for the whole gather makes every inner block
    inside `compare()` capture and restore the SAME model, so the mutation is a
    no-op per call and concurrency is safe. Wrapping each coroutine individually
    would not be: the first to finish restores the base model under its still
    running siblings.
    """
    from e2e.judge import E2EJudge, _x_is_a
    from e2e.modelctx import using_model
    from e2e.scenarios import scenarios_for

    arms = sorted({p.arm for p in pairs})
    judge = E2EJudge(di_container, judge_model)
    semaphore = asyncio.Semaphore(4)
    ordinals: dict[str, int] = {}
    plan: list[tuple[Pair, int, int]] = []
    for pair in pairs:
        ordinal = ordinals.get(pair.arm, 0)
        ordinals[pair.arm] = ordinal + 1
        # Ordinals count PER ARM because `pair_key` is per arm ("A2|A2"), and the
        # stratum is the arm for the same reason. Every wave-1 arm group is
        # even-sized, so the alternation lands exactly 50/50 with no residual.
        plan.append((pair, ordinal, arms.index(pair.arm)))

    async def one(pair: Pair, ordinal: int, stratum: int) -> None:
        async with semaphore:
            run_a, run_b = _records_for(pair)
            scenario = scenarios_for([pair.scenario_key])[0]
            comparison = await judge.compare(
                scenario=scenario,
                run_a=run_a,
                run_b=run_b,
                session_label=pair.label,
                ordinal=ordinal,
                stratum_index=stratum,
            )
            pair.x_side = (
                "a"
                if _x_is_a(
                    "",
                    ordinal=ordinal,
                    pair_key=f"{pair.arm}|{pair.arm}",
                    stratum_index=stratum,
                )
                else "b"
            )
            if comparison.error:
                pair.error = comparison.error
            pair.scores = {k: (float(v[0]), float(v[1])) for k, v in comparison.scores.items()}
            pair.notes = dict(comparison.notes)
            pair.overall_note = comparison.overall_note
            if pair.scores:
                print(
                    f"  judged {pair.stem[:26]:26} {pair.arm:5} "
                    f"rep{pair.replicate} X={pair.x_side.upper()} "
                    f"gap {pair.gap:+6d} -> {pair.delta:+.3f}",
                    flush=True,
                )
            else:
                print(
                    f"  FAILED {pair.stem} {pair.arm} rep{pair.replicate}: "
                    f"{pair.error}",
                    flush=True,
                )

    with using_model(di_container, judge_model):
        await asyncio.gather(*(one(*args) for args in plan))


def main(argv: list[str]) -> int:
    if "--read" in argv:
        waves = [int(a) for a in argv if a.isdigit()] or [1]
        if (PLACEBO_DIR / "wave2.json").exists() and waves == [1]:
            waves = [1, 2]
        return print_read(waves)
    return print_plan()


def _selection_or_skip() -> list[Pair]:
    """Wave 1 off the local archive, or a skip.

    `tests/e2e/results/` is gitignored, so a fresh checkout has no archive and
    these guards have nothing to check. Skipping says that; failing would report
    a missing archive as a broken pre-registration.
    """
    pairs, _ = candidates()
    if len(pairs) < WAVE_ONE_N:
        pytest.skip(f"local archive holds {len(pairs)} same-arm candidates")
    return wave_one(pairs)


class TestThePreRegistrationIsAuditable:
    """Free guards. Re-collected into the default suite by subclassing in
    `test_e2e.py` — no `probe_*.py` is collected under pytest's `test_*.py`
    pattern, so guards left only here would run when named and never again."""

    def test_selection_is_deterministic(self):
        """Wave 1 is reproducible from the archive with no stored state, so the
        registered set cannot quietly become a different 32."""
        first = _selection_or_skip()
        assert first == wave_one(candidates()[0])
        assert len(first) == WAVE_ONE_N
        assert len({p.fingerprint for p in first}) == WAVE_ONE_N

    def test_side_assignment_is_length_blind(self):
        """A is the first branch NAME. Assigning the longer transcript to A would
        make every gap positive and turn the slope question into an intercept
        question."""
        first = _selection_or_skip()
        assert all(p.branch_a < p.branch_b for p in first)
        assert any(p.gap < 0 for p in first)
        assert any(p.gap > 0 for p in first)

    def test_marquee_block_is_present_whole(self):
        """A placebo for a published number has to contain the cells that number
        was computed on: 6 A1 + 6 A1.5 pairs on the two marquee stems."""
        first = _selection_or_skip()
        marquee = [
            p for p in first if p.stem in MARQUEE_STEMS and p.arm in MARQUEE_ARMS
        ]
        assert len(marquee) == 12
        assert {p.arm for p in marquee} == set(MARQUEE_ARMS)
        assert {p.stem for p in marquee} == set(MARQUEE_STEMS)

    def test_arm_groups_are_even_so_the_position_split_is_exact(self):
        """`ordinal` alternates within the arm, so the X/Y split is exactly 50/50
        only in an even-sized group — see `judge._x_is_a` on odd strata."""
        counts: dict[str, int] = {}
        for p in _selection_or_skip():
            counts[p.arm] = counts.get(p.arm, 0) + 1
        assert all(n % 2 == 0 for n in counts.values()), counts

    def test_only_exchangeable_sessions_are_in_the_population(self):
        """Never a branch session. `wobble_a` is a DIFFERENT script in the two
        records, so its two transcripts are not two samples of one thing."""
        pairs, _ = candidates()
        for p in pairs:
            assert p.label not in {p.branch_a, p.branch_b}

    def test_the_docstring_power_numbers_are_the_ones_the_code_computes(self):
        """The sizing quoted in the pre-registration, recomputed. Both inputs are
        measured, so this is arithmetic and not a hope."""
        first = _selection_or_skip()
        assert power_for(first, CONSEQUENTIAL_SLOPE_PER_WORD, ARCHIVE_RESIDUAL_SD) == \
            pytest.approx(0.82, abs=0.03)
        assert power_for(first, ARCHIVE_SLOPE_PER_WORD, ARCHIVE_RESIDUAL_SD) > 0.99

    def test_registered_bars_cannot_drift(self):
        """The bars live in a pure function so this can hold them. A threshold
        that moves after the data arrives is not a pre-registration."""
        tie = CROSS_ARM_TIE_RATE
        hot = CROSS_ARM_TIE_RATE + TIE_ATTENUATION_MARGIN + 0.01
        assert verdict(0.0008, 0.0016, 0.0012, tie)[0] == "CONFOUND CONFIRMED"
        assert verdict(-0.0004, 0.0006, 0.0001, tie)[0] == "CONFOUND REFUTED"
        assert verdict(-0.0020, -0.0008, -0.0014, tie)[0].startswith("REVERSAL")
        # Contains both 0 and the archive slope: the registered NULL band, which
        # is what stops an underpowered run reading as a refutation.
        assert verdict(-0.0006, 0.0020, 0.0007, tie)[0] == "INDETERMINATE"
        # Significant but below the consequential threshold is not a confirmation.
        assert verdict(0.0001, 0.0005, 0.0003, tie)[0] == "INDETERMINATE"
        # Compression withholds a REFUTATION only, because it biases toward one.
        assert (
            verdict(-0.0004, 0.0006, 0.0001, hot)[0]
            == "INDETERMINATE (attenuation-limited)"
        )
        assert verdict(0.0008, 0.0016, 0.0012, hot)[0] == "CONFOUND CONFIRMED"

    def test_clustered_interval_is_never_narrower_than_the_flat_one(self):
        """A negative ICC must not buy precision — the same rule `read_pooled`
        applies to a mean."""
        fit = {"slope": 0.001, "se_slope": 0.0002, "df": 30, "n": 32}
        flat = _slope_interval(fit, 1.0)
        for deff in (0.4, 1.0, 1.6, 3.0):
            lo, hi = _slope_interval(fit, deff)[:2]
            assert hi - lo >= (flat[1] - flat[0]) - 1e-12

    def test_output_stays_out_of_every_archive_sweep(self):
        """Archive readers glob `results/*.json` NON-recursively. A same-arm
        comparison saved as an ordinary stem would enter `read_pooled`,
        `noise_floor` and `read_length_confound` as a legitimate arm pair — the
        placebo pooled into the very numbers it exists to interpret."""
        assert PLACEBO_DIR.parent == RESULTS
        assert PLACEBO_DIR.name not in {p.name for p in RESULTS.glob("*.json")}
        assert (PLACEBO_DIR / "wave1.json") not in set(RESULTS.glob("*.json"))

    def test_the_recorded_result_is_what_the_docstrings_quote(self):
        """The saved wave-1 record must still produce the numbers three files now
        quote off it — this docstring, `read_length_confound.py`'s and the
        README's. A verdict that lives only in prose drifts from the data behind
        it; recomputed here, it cannot."""
        if not (PLACEBO_DIR / "wave1.json").exists():
            pytest.skip("wave 1 has not been judged in this checkout")
        pairs, _ = load(1)
        scored = [p for p in pairs if p.scores]
        assert len(scored) == WAVE_ONE_N
        fit = _fit(scored)
        _, deff = _deff_by_stem(scored, fit)
        lo, hi, _ = _slope_interval(fit, deff)
        tied, total = tie_rate(scored)
        assert fit["slope"] * 1000 == pytest.approx(-0.133, abs=0.002)
        assert (lo * 1000, hi * 1000) == pytest.approx((-0.569, +0.303), abs=0.01)
        # The three exclusions that make it a refutation rather than a null.
        assert hi < CONSEQUENTIAL_SLOPE_PER_WORD < ARCHIVE_SLOPE_PER_WORD
        assert verdict(lo, hi, fit["slope"], tied / total)[0] == "CONFOUND REFUTED"
        # Exchangeability is the premise the whole probe rests on.
        assert st.fmean(p.delta for p in scored) == pytest.approx(0.0, abs=0.01)
        assert slot_bias(scored)[1:] == (16, 16)

    def test_composite_matches_the_reading_it_interprets(self):
        """Scored on `read_length_confound`'s composite, or it is a placebo for a
        different number than the one in question."""
        scores = {d: (5.0, 3.0) for d in CROSS_ARM_DIMENSION_SLOPE}
        scores.update({d: (1.0, 5.0) for d in NON_INFERIORITY_DIMENSIONS})
        assert composite(scores) == pytest.approx(2.0)


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_same_arm_placebo_wave_one(di_container):
    """Spends the 32 pre-registered judge calls.

    NOT `@traced` — conftest's tracer serialises the test's arguments as span
    input and `di_container` is cyclic.
    """
    from e2e.config import E2EConfig

    config = E2EConfig.from_env()
    chosen = wave_one(candidates()[0])
    print(
        f"\n  judging {len(chosen)} same-arm pairs on {config.judge_model}\n",
        flush=True,
    )
    await judge_wave(di_container, chosen, config.judge_model)
    path = save(chosen, wave=1, judge_model=config.judge_model)
    print(f"\n  saved {path}\n", flush=True)
    print_read([1])
    assert any(p.scores for p in chosen), "every judge call failed"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
