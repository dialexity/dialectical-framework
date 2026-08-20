"""Exact power for the two designs this archive actually uses.

WHY THIS EXISTS
===============
The parentage probe (`probe_tetrad_pole.py`) pre-registered a bar, cleared it on
one run, missed it on a replication, and was written up as NOT CONFIRMED. All of
that was careful. None of it was informative, because the probe had **28% power**
for the effect it was hunting: 72 minus-aspect slots per arm, a baseline rate near
18%, and a fix that pooled to about 9%. A design that misses a real effect 7 times
in 10 produces a NOT CONFIRMED verdict whether or not the fix works, so the
verdict carried almost no evidence either way — and the one run that DID clear the
bar was, on those numbers, the favourable tail rather than a signal.

That was knowable before spending a single provider call. It was not computed,
because "pre-register the endpoint and the bar" felt like the whole of the
discipline. It is not: **an endpoint and a bar with no power calculation is a
coin-flip dressed as a hypothesis test.** Pre-registration stops you from moving
the goalposts after the fact; it does nothing about goalposts too small to hit.

So: before registering any bar in this archive, size it here. If the affordable n
cannot reach ~0.8, the honest options are to enrich the population until the base
rate is high enough, change the endpoint to one with more information per cell, or
say up front that the run is a screen and a null will be uninterpretable. Running
it anyway and reporting the number as a finding is the one option that is not open.

NOT A DUPLICATE OF THE SIZING TOOLS THAT ALREADY EXISTED — AND THAT IS THE POINT
=================================================================================
`noise_floor.py` and `endpoint_power.py` size the JUDGED lane: continuous rubric
scores, within-dimension sd, 80%-power MDE, "a 0.5-step effect needs ~19 pairs".
That lane has had a power discipline since 2026-08-13. This module is its missing
counterpart for COUNT endpoints — a defect rate out of n slots, compared with
Fisher or McNemar — which is what every `probe_*.py` measures and what none of
them sized. So the archive did not lack the idea of powering a run; it applied it
on one lane and not the other, and the two lanes differ only in whether the
endpoint is a mean or a proportion. Worth remembering as its own failure mode:
**a discipline that lives in one lane's tooling does not transfer itself.**

RETROSPECTIVE POWER OF THIS ARCHIVE'S RUNS (see `retrospective()`)
  parentage, aspect-level, n=72/arm, 18% -> 9%   power 0.28
  parentage, tetrad-level, n=36/arm, 30% -> 17%  power 0.18
  classifier form test, 12/arm, no effect        (a null band was registered,
      which is why that run IS interpretable — see probe_classifier_stability)

WHICH TEST
==========
`fisher_power` — two independent arms, e.g. a baseline run vs a post-fix run.
`mcnemar_power` — the SAME cells measured under both arms (one process, one
    classification cache, both prompts). Pairing only pays when the arms are
    genuinely correlated: it roughly doubles power if the fix acts almost
    monotonically (it only ever removes defects), and buys nearly nothing once
    generation noise dominates the discordance. Both are tabulated by
    `compare_designs` so the assumption is visible instead of assumed.

Usage:
  poetry run python tests/e2e/power.py                    # the standing tables
  poetry run python tests/e2e/power.py 0.40 0.20 48 96    # p1 p2 n_lo n_hi
"""

from __future__ import annotations

import sys
from math import comb

_TINY = 1e-13


# --- the tests ----------------------------------------------------------------


def fisher_exact_two_sided(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact p for [[a, b], [c, d]].

    Duplicated from `probe_tetrad_pole.py` rather than imported: importing it
    would make this module drag in pytest and a provider config, and a power
    calculator has to be runnable as a bare script while designing a run.
    """
    n = a + b + c + d
    row1, row2 = a + b, c + d
    col1, col2 = a + c, b + d

    def hyper(x: int) -> float:
        return comb(col1, x) * comb(col2, row1 - x) / comb(n, row1)

    observed = hyper(a)
    lo = max(0, row1 - col2)
    hi = min(row1, col1)
    return min(
        1.0,
        sum(hyper(x) for x in range(lo, hi + 1) if hyper(x) <= observed + 1e-12),
    )


def mcnemar_exact_two_sided(b: int, c: int) -> float:
    """Two-sided exact (binomial) McNemar p for b vs c discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2**n)


# --- power --------------------------------------------------------------------


def _binomial_window(n: int, p: float, sd: float = 7.0) -> tuple[int, int]:
    """Range of counts holding all but a negligible tail of the mass.

    Enumerating 0..n twice and calling an O(n) Fisher inside is cubic and takes
    minutes at n in the hundreds. Seven SDs each side leaves under 1e-11 outside,
    which is far below the precision anything here is reported to.
    """
    mean = n * p
    spread = sd * (n * p * (1 - p)) ** 0.5 + 2
    return max(0, int(mean - spread)), min(n, int(mean + spread) + 1)


def fisher_power(n: int, p1: float, p2: float, alpha: float = 0.05) -> float:
    """P(Fisher p < alpha) for two independent arms of n each at rates p1, p2.

    Exact up to a truncated tail (see `_binomial_window`): enumerates both
    binomials rather than sampling, so the number does not itself carry
    Monte-Carlo error — the whole point is to stop mistaking noise for signal.
    """
    a_lo, a_hi = _binomial_window(n, p1)
    c_lo, c_hi = _binomial_window(n, p2)
    # For fixed `a`, significance is monotone in `c` on each side of the null, so
    # the verdict is cached per (a, c) rather than recomputed across the sweep.
    total = 0.0
    for a in range(a_lo, a_hi + 1):
        pa = comb(n, a) * p1**a * (1 - p1) ** (n - a)
        if pa < _TINY:
            continue
        for c in range(c_lo, c_hi + 1):
            pc = comb(n, c) * p2**c * (1 - p2) ** (n - c)
            if pc < _TINY:
                continue
            if fisher_exact_two_sided(a, n - a, c, n - c) < alpha:
                total += pa * pc
    return total


def mcnemar_power(
    n: int, p_arm1_only: float, p_arm2_only: float, alpha: float = 0.05
) -> float:
    """P(exact McNemar p < alpha) for n paired cells.

    `p_arm1_only` / `p_arm2_only` are DISCORDANCE rates, not defect rates: the
    probability that a given cell is a defect under arm 1 and clean under arm 2,
    and vice versa. Concordant pairs carry no information for this test, which is
    exactly why the assumption about them has to be stated rather than absorbed
    into a defect rate.
    """
    p_conc = 1 - p_arm1_only - p_arm2_only
    if p_conc < 0:
        raise ValueError("discordance rates sum above 1")
    b_lo, b_hi = _binomial_window(n, p_arm1_only)
    c_lo, c_hi = _binomial_window(n, p_arm2_only)
    total = 0.0
    for b in range(b_lo, b_hi + 1):
        for c in range(c_lo, min(c_hi, n - b) + 1):
            lp = (
                comb(n, b)
                * comb(n - b, c)
                * p_arm1_only**b
                * p_arm2_only**c
                * p_conc ** (n - b - c)
            )
            if lp < _TINY:
                continue
            if mcnemar_exact_two_sided(b, c) < alpha:
                total += lp
    return total


def min_n_for(
    p1: float, p2: float, target: float = 0.80, cap: int = 600, step: int = 12
) -> int | None:
    """Smallest per-arm n reaching `target` power, or None if `cap` is hit.

    Cost note, learned the expensive way: this is cubic in n, so the default cap of
    600 is a usability limit and not an opinion about designs. Very low base rates
    push the answer far past it — halving 3.1% needs n=1600/arm, and evaluating a
    SINGLE `fisher_power` at that n runs for minutes. If you find yourself raising
    `cap` into the thousands, the tool is telling you the honest answer already:
    that endpoint is not affordable, and the design needs a different endpoint or a
    denser population rather than a bigger n.
    """
    for n in range(step, cap + 1, step):
        if fisher_power(n, p1, p2) >= target:
            return n
    return None


# --- readouts -----------------------------------------------------------------


def _table(label: str, p1: float, p2: float, ns: tuple[int, ...]) -> None:
    cells = "  ".join(f"n={n}: {fisher_power(n, p1, p2):.2f}" for n in ns)
    need = min_n_for(p1, p2)
    tail = f"0.80 at n={need}" if need else "0.80 unreachable under cap"
    print(f"  {label:34s} {cells}   [{tail}]")


def retrospective() -> None:
    """What this archive's already-published runs were actually able to see."""
    print("=== retrospective power of runs already in the archive ===")
    _table("parentage aspect 18%->9%", 0.18, 0.09, (72, 144, 216, 288))
    _table("parentage tetrad 30%->17%", 0.30, 0.17, (36, 72, 108, 144))
    print(
        "\n  The parentage probe ran at n=72/arm aspect-level: power 0.28. Both its\n"
        "  runs (4/72 clearing the bar, 9/72 missing it) are consistent with a real\n"
        "  effect AND with none. The replication did not overturn the first run; the\n"
        "  design could not distinguish them in the first place."
    )


def enrichment() -> None:
    """Why a rare-event endpoint has to be enriched, not just re-run bigger."""
    print("\n=== enrichment: the same fix on a defect-prone population ===")
    _table("40% -> 20%", 0.40, 0.20, (48, 72, 96, 144))
    _table("40% -> 15%", 0.40, 0.15, (48, 72, 96, 144))
    _table("35% -> 20%", 0.35, 0.20, (48, 72, 96, 144))
    print(
        "\n  Doubling a base rate buys more power than doubling n. But enrichment must\n"
        "  select on a PROPERTY known in advance (e.g. 'the poles are mutually\n"
        "  exclusive options, not opposites' — a structural claim CLAUDE.md already\n"
        "  makes), never on which cells failed in the runs being compared against.\n"
        "  Selecting on the outcome makes the baseline arm's rate partly a product of\n"
        "  the selection, and any result about the DIFFERENCE inherits that."
    )


def pairing() -> None:
    """Whether running both arms on the same cells is worth the machinery."""
    print("\n=== paired (both prompts, same cells, one run) vs unpaired ===")
    for label, (pb, pf) in {
        "near-monotone fix  11%/2%": (0.11, 0.02),
        "moderate noise      9%/4%": (0.09, 0.04),
        "noise-dominated     8%/5%": (0.08, 0.05),
    }.items():
        cells = "  ".join(
            f"n={n}: {mcnemar_power(n, pb, pf):.2f}" for n in (72, 108, 144, 216)
        )
        print(f"  {label:34s} {cells}")
    print(
        "\n  Pairing is not a free win. It pays only insofar as the two arms agree on\n"
        "  the easy cells; once the same prompt run twice disagrees as often as the\n"
        "  two prompts do, the pairs are not really paired and McNemar is weaker than\n"
        "  Fisher on the same n. The parentage prompt gave 4/72 and 9/72 on identical\n"
        "  inputs, so noise-dominated is the row to plan against, not the first row."
    )


def main(argv: list[str]) -> None:
    if len(argv) == 5:
        p1, p2 = float(argv[1]), float(argv[2])
        lo, hi = int(argv[3]), int(argv[4])
        ns = tuple(sorted({lo, (lo + hi) // 2, hi}))
        _table(f"{p1:.0%} -> {p2:.0%}", p1, p2, ns)
        return
    retrospective()
    enrichment()
    pairing()


if __name__ == "__main__":
    main(sys.argv)
