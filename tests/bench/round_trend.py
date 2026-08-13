"""Does the round-by-round loop converge? Free, over every saved judged run.

    poetry run python tests/bench/round_trend.py

`endpoint_power.py` sizes a comparison WITHIN one run: how many judged cells buy
a given effect, given that the 12 dimensions are repeated measures on one
transcript pair. That is the right question for "A2 vs its opponent, today".

It is the WRONG question for the loop this bench is actually running. Every round
r1..r16 changed `src/`, judged one run, and read the result as evidence about the
change. That comparison is BETWEEN BUILDS, and its unit is the RUN, not the cell —
so the relevant sd is the spread of run composites, and every round to date has
spent n=1 per side.

WHAT THE ARCHIVE SAYS ABOUT ITS OWN LOOP
========================================
Eleven single-scenario weak-tier rounds on `cofounder_equity`, each slot- and
stratum-balanced (see below) rather than taken naive:

    r1 -0.54   r2 -0.35   r3 -0.08   r4 -0.54   r5 -0.39   r6 -0.85
    r7 -0.76   r10 -0.89  r14 -0.82  r15 -0.30  r16 -0.50

    mean -0.547   sd 0.258   band [-0.89, -0.08]   all 11 negative

Two numbers decide whether 16 rounds of work show anything:

1. **Between-round scatter against within-round noise.** A round's own composite
   carries a 95% half-width of about ±0.40, i.e. se ≈ 0.20. If every build shared
   one true mean, the run-to-run sd would ALSO be ≈ 0.20. Observed: 0.258. Ratio
   **1.27**. The scatter is barely larger than the noise that would exist if no
   fix had done anything at all — so the archive cannot attribute its own
   variation to its own changes.

2. **Trend.** Correlation of composite with round order is **-0.34** (slope
   -0.026/round). Sixteen rounds of fixes point, if anything, slightly DOWN. The
   loop is not converging; it is resampling one distribution.

The uncomfortable corollary is a sizing fact, not an opinion:

    to see a  +0.2 improvement between two builds:  30 runs/build (~81h judged each)
              +0.3                                  14 runs/build (~38h)
              +0.5                                   5 runs/build (~14h)

Every round so far spent ONE. A single-run round can only register a fix worth
about a full step — larger than the entire archive's spread — so the design was
never able to confirm a fix, only to fail to. r15's -0.30 and r14's -0.82 are two
draws from the same jar, and reading either as a verdict on its round is the error
the whole ledger repeats.

This is the argument for changing the round SHAPE (freeze a build, batch several
fixes, judge many runs, or move to a machine-countable endpoint), not for buying
more of the same round.

WHAT DID MOVE, AND WHY IT IS THE WRONG THING
============================================
Splitting the 12 dimensions into REGISTER (warmth, conversational_fit,
cross_turn_coherence, actionability, earned_confidence) and SUBSTANCE
(entanglement, non_triviality, blindspot_specificity, tension_coverage,
convergence, decision_closure, paired_recipe) — the framework's own turf — and
pooling by era:

                   REGISTER          SUBSTANCE
    r1-r5           -0.519            -0.360
    r6-r14          -0.946            -0.693     (the era that turned the machinery ON)
    r15-r16         -0.133            -0.333

    late - early   +0.386 [+0.07,+0.70] RESOLVES   +0.027 [-0.39,+0.44] covers zero

**Every gain the archive can resolve is register.** Substance is unchanged to two
decimal places across sixteen rounds. And the mechanism is visible in the
transcripts rather than inferred: A2's replies went 416 -> 272 words and 7.25 ->
2.71 bullets per turn between r7 and r16, against A1.7's steady ~310 words / ~1.1
bullets. The arm improved by becoming shorter, flatter, and more prose-like —
converging on its opponent's shape.

That is the ceiling-not-floor failure stated as a measurement: the loop has been
closing the gap by shedding what makes the arm different, and `probe_readside_reach.py`
shows why it costs nothing to shed — the structure was not reaching the reply
anyway. A round that improves register is buying back a tax. Only a round that
moves SUBSTANCE is evidence the framework does something a prompt cannot, and no
round in the ledger has done that.

WHY THE NUMBERS HERE ARE NOT THE ONES IN THE REPORT
===================================================
The report prints the naive cell mean. This script balances twice, because the
judge scores the second transcript higher regardless of content (`position_bias`,
measured at +0.35 in `decision-strong-r3`) and slot assignment is only exactly
even in some rounds:

  * SLOT balance — average A2-as-X against A2-as-Y, then take the midpoint, so a
    7/5 slot split cannot leak bias into the round's number. It moved r14 from
    -0.778 to -0.836 and r15 from -0.132 to -0.204.
  * STRATUM balance — do that per session label and average the labels, because
    slot bias only cancels inside a stratum whose own split is even. r16 goes
    -0.368 -> -0.502 this way; r6/r7 have strata with no split at all, so they
    fall back to the slot figure (reported, with the fallback visible).

Balancing does not rescue the trend, which is the point of doing it here: the
jump from r14 to r15 survives (-0.82 -> -0.30) and is still inside the scatter.

A measurement script: prints and exits, reads only saved records, costs nothing.
Pinned by `TestTheLoopIsNotConverging`.
"""

from __future__ import annotations

import math
import re
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bench.models import (  # noqa: E402
    REGISTER_DIMENSIONS,
    SUBSTANCE_DIMENSIONS,
    Comparison,
)
from bench.report import load_records  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

#: Eras, in build order. The middle era is the one that turned the machinery ON
#: (the record seam, the grounding lane, the pathway seam) and it is also the
#: archive's WORST — which is the finding, not a footnote.
ERAS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "r1-r5",
        (
            "claim2-weak-r1",
            "claim2-weak-r2",
            "claim2-weak-r3",
            "claim2-weak-r4",
            "claim2-weak-r5",
        ),
    ),
    (
        "r6-r14",
        (
            "claim2-weak-r6-grounding",
            "claim2-weak-r7-readside",
            "claim2-weak-r10-pathways-judged",
            "claim2-weak-r14-accretion",
        ),
    ),
    ("r15-r16", ("claim2-weak-r15-voice", "claim2-weak-r16-floor")),
)

# Half-width a single 12-cell round reports, from the archive's per-round CIs
# (r4 ±0.47, r6 ±0.31, r10 ±0.42, r14 ±0.40, r15 ±0.48, r16 ±0.38). Used only to
# derive the se a constant-mean archive would show; the comparison is a ratio, so
# a rough central value is honest and a precise one would be false.
TYPICAL_HALF_WIDTH = 0.40


def _round_number(stem: str) -> int:
    """Sort key: `claim2-weak-r10-pathways-judged` -> 10, unnumbered -> 0."""
    match = re.search(r"-r(\d+)", stem)
    return int(match.group(1)) if match else 0


def balanced_composite(
    stem: str, *, tier: str = "weak", opponent: str = "A1.7"
) -> tuple[float, float, float, int, bool] | None:
    """(naive, slot-balanced, stratum-balanced, cells, stratum_ok) for one run.

    `opponent` is REQUIRED to be held fixed across the series. `claim1-weak-r1/r2`
    judge A2 against A1 and would otherwise enter the trend as its two most
    favourable points (-0.49, -0.07) purely because A1 is the weaker arm — a
    trend line fitted through a changing opponent measures the opponent.

    `stratum_ok` is False when some session label was judged in only one slot —
    then the stratum figure repeats the slot one rather than silently averaging a
    half-balanced stratum, and the caller prints which it got.
    """
    payload = load_records(RESULTS / f"{stem}.json")
    cells: list[tuple[str, str, float]] = []
    for raw in payload.get("comparisons") or []:
        comparison = Comparison.model_validate(raw)
        if comparison.error or comparison.tier != tier:
            continue
        arms = (comparison.arm_a.value, comparison.arm_b.value)
        if "A2" not in arms or arms[0] == arms[1]:
            continue
        if opponent not in arms:
            continue
        mine_is_a = comparison.arm_a.value == "A2"
        gaps = [
            (a - b) if mine_is_a else (b - a)
            for a, b in comparison.scores.values()
        ]
        if not gaps:
            continue
        cells.append(
            (comparison.session_label, comparison.x_arm.value, st.mean(gaps))
        )
    if len(cells) < 3:
        return None

    naive = st.mean([c[2] for c in cells])

    def midpoint(subset: list[tuple[str, str, float]]) -> float | None:
        as_x = [c[2] for c in subset if c[1] == "A2"]
        as_y = [c[2] for c in subset if c[1] != "A2"]
        if not as_x or not as_y:
            return None
        return (st.mean(as_x) + st.mean(as_y)) / 2

    slot = midpoint(cells)
    slot = naive if slot is None else slot

    labels = sorted({c[0] for c in cells})
    per_label = [
        value
        for label in labels
        if (value := midpoint([c for c in cells if c[0] == label])) is not None
    ]
    stratum_ok = len(per_label) == len(labels)
    stratum = st.mean(per_label) if stratum_ok else slot
    return naive, slot, stratum, len(cells), stratum_ok


def series(
    *, tier: str = "weak", opponent: str = "A1.7"
) -> list[tuple[str, float, float, float, int, bool]]:
    """One row per comparable judged run, in round order.

    Comparable means THREE things held fixed, because a trend line is only about
    the builds if nothing else moved under it:

      * one scenario — multi-scenario `claim2` is excluded for the reason
        `composite_rows` gives: it averages the `career_offer` poor-fit control,
        which the framework is EXPECTED to lose, into the same number.
      * one tier — the strong tier is a different jar (mean -0.06 against -0.51).
      * one opponent — see `balanced_composite`.
    """
    rows: list[tuple[str, float, float, float, int, bool]] = []
    for path in sorted(RESULTS.glob("*.json")):
        stem = path.stem
        if stem.endswith("-runs") or stem == "claim2":
            continue
        payload = load_records(path)
        scenarios = {
            c.get("scenario_key") for c in payload.get("comparisons") or []
        }
        if len(scenarios) != 1:
            continue
        measured = balanced_composite(stem, tier=tier, opponent=opponent)
        if measured is None:
            continue
        rows.append((stem, *measured))
    rows.sort(key=lambda row: (_round_number(row[0]), row[0]))
    return rows


def convergence(values: list[float]) -> tuple[float, float, float, float]:
    """(mean, sd, correlation with round order, slope per round)."""
    mean, sd = st.mean(values), st.stdev(values)
    order = list(range(len(values)))
    mean_order = st.mean(order)
    covariance = sum(
        (x - mean_order) * (y - mean) for x, y in zip(order, values)
    )
    spread_order = sum((x - mean_order) ** 2 for x in order)
    spread_values = sum((y - mean) ** 2 for y in values)
    denominator = math.sqrt(spread_order * spread_values)
    correlation = covariance / denominator if denominator else 0.0
    return mean, sd, correlation, covariance / spread_order


def runs_per_build(sd: float, effect: float) -> int:
    """Two-sample size at alpha 0.05 / power 0.80, in RUNS per build."""
    return math.ceil(2 * (1.96 + 0.84) ** 2 * sd**2 / effect**2)


def era_cells(
    stems: tuple[str, ...], dimensions: tuple[str, ...], *, tier: str = "weak"
) -> list[float]:
    """One value per judged cell: its mean gap over `dimensions` only.

    Cell-level on purpose and NOT a significance claim on its own — the same
    caution `dimension_shape` carries. It is used here for a difference between
    two eras of several runs each, where the question is the direction of a
    ~0.4-step move and the alternative is no estimate at all.
    """
    values: list[float] = []
    wanted = set(dimensions)
    for stem in stems:
        for raw in load_records(RESULTS / f"{stem}.json").get("comparisons") or []:
            comparison = Comparison.model_validate(raw)
            if comparison.error or comparison.tier != tier:
                continue
            arms = (comparison.arm_a.value, comparison.arm_b.value)
            if "A2" not in arms or "A1.7" not in arms:
                continue
            mine_is_a = comparison.arm_a.value == "A2"
            gaps = [
                (a - b) if mine_is_a else (b - a)
                for dimension, (a, b) in comparison.scores.items()
                if dimension in wanted
            ]
            if gaps:
                values.append(st.mean(gaps))
    return values


def register_versus_substance(
    *, tier: str = "weak"
) -> tuple[list[tuple[str, float, float, int]], dict[str, tuple[float, float]]]:
    """(per-era means, {group: (late-early delta, se)}).

    The question the composite cannot answer: did the loop improve the product or
    its manners? Only the manners resolve.
    """
    table: list[tuple[str, float, float, int]] = []
    for name, stems in ERAS:
        register = era_cells(stems, REGISTER_DIMENSIONS, tier=tier)
        substance = era_cells(stems, SUBSTANCE_DIMENSIONS, tier=tier)
        if register and substance:
            table.append((name, st.mean(register), st.mean(substance), len(register)))

    moves: dict[str, tuple[float, float]] = {}
    early, late = ERAS[0][1], ERAS[-1][1]
    for label, dimensions in (
        ("register", REGISTER_DIMENSIONS),
        ("substance", SUBSTANCE_DIMENSIONS),
    ):
        first, last = (
            era_cells(early, dimensions, tier=tier),
            era_cells(late, dimensions, tier=tier),
        )
        if len(first) < 2 or len(last) < 2:
            continue
        se = math.sqrt(st.variance(first) / len(first) + st.variance(last) / len(last))
        moves[label] = (st.mean(last) - st.mean(first), se)
    return table, moves


def main() -> int:
    rows = series()
    if len(rows) < 3:
        print("not enough saved single-scenario weak-tier runs in", RESULTS)
        return 1

    print(f"{'round':34}{'naive':>8}{'slot':>8}{'stratum':>9}{'cells':>7}")
    for stem, naive, slot, stratum, cells, stratum_ok in rows:
        flag = "" if stratum_ok else "  (slot only: a stratum had one slot)"
        print(f"{stem[:33]:34}{naive:>+8.3f}{slot:>+8.3f}{stratum:>+9.3f}{cells:>7}{flag}")

    values = [row[3] for row in rows]
    mean, sd, correlation, slope = convergence(values)
    negative = sum(1 for v in values if v < 0)
    print()
    print(
        f"{len(values)} rounds: mean {mean:+.3f}  sd {sd:.3f}  "
        f"band [{min(values):+.2f}, {max(values):+.2f}]  negative {negative}/{len(values)}"
    )

    implied = TYPICAL_HALF_WIDTH / 1.96
    print()
    print("IS THE ROUND-TO-ROUND VARIATION THE FIXES, OR THE NOISE?")
    print(f"  a single round's own se, from its printed CI      {implied:.3f}")
    print(f"  sd between rounds, if every build were identical  {implied:.3f}")
    print(f"  sd between rounds, observed                       {sd:.3f}")
    print(f"  ratio {sd / implied:.2f}  — 1.0 means the rounds are one distribution resampled")

    print()
    print(f"TREND  correlation with round order {correlation:+.3f}   slope {slope:+.4f}/round")
    print(
        "  A loop that improves its subject shows a positive slope well outside\n"
        "  the scatter. This one does not."
    )

    table, moves = register_versus_substance()
    if table:
        print()
        print("WHAT DID MOVE: MANNERS, NOT PRODUCT")
        print(f"  {'era':10}{'REGISTER':>10}{'SUBSTANCE':>11}{'cells':>7}")
        for name, register, substance, cells in table:
            print(f"  {name:10}{register:>+10.3f}{substance:>+11.3f}{cells:>7}")
        for label, (delta, se) in moves.items():
            verdict = "RESOLVES" if abs(delta) > 1.96 * se else "covers zero"
            print(
                f"  {label:10} late - early {delta:>+7.3f}  "
                f"95% CI [{delta - 1.96 * se:+.2f}, {delta + 1.96 * se:+.2f}]  {verdict}"
            )
        print(
            "  A2 went 416 -> 272 words and 7.25 -> 2.71 bullets per turn over the same\n"
            "  span (A1.7 steady at ~310/~1.1): the register gain came from converging on\n"
            "  the opponent's shape. That is ceiling-not-floor failing, as a number."
        )

    print()
    print("WHAT A ROUND WOULD HAVE TO COST TO SETTLE ITS OWN QUESTION:")
    print(f"  {'effect':>8}{'runs/build':>12}{'hours judged per side':>24}")
    for effect in (0.2, 0.3, 0.5, 0.8):
        needed = runs_per_build(sd, effect)
        print(f"  {effect:>+8.1f}{needed:>12}{needed * 2.7:>21.0f}h")
    print("  Every round in the ledger spent ONE run per build.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
