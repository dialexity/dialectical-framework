"""Re-simulate the r23 control power table at a new archive sd.

WHY THIS IS A FILE AND NOT A SCRATCH SNIPPET
============================================
`test_the_power_table_is_reproducible_from_the_archives_own_sd` pins the
NI-composite sd to 2dp so that a round which shifts it has to re-simulate the
table before its percentages are quoted again. That check has now fired three
times (r26, `a15-floor`, `weave-offturn`) and each firing was answered with an
ad-hoc simulation whose code did not survive. This is that code, kept, so the
fourth firing costs a command rather than a reconstruction.

THE TEST RULE, WHICH IS THE PART EASY TO GET WRONG
==================================================
r23's pre-registered reading is "the NI composite CI on either control excludes
zero ON THE POSITIVE SIDE", i.e. a two-sided 95% t interval whose LOWER bound is
above zero. That is one-sided 2.5%, which is why the original table's true-null
row reads 3% and not 5%: a re-simulation that fires on a one-sided 5% test
reproduces the eight effect cells and doubles the null row, which is a
difference in test rule and not in sd. Use this rule, or compare nothing.
"""

from __future__ import annotations

import argparse
import random
import statistics as st
from math import sqrt

#: t(n-1) at 0.975. Table rather than a dependency: the three n values r23 uses
#: are fixed by the pre-registration, and a scipy import here would make a
#: provenance script depend on a package the harness does not otherwise need.
T_CRIT = {7: 2.365, 11: 2.201, 15: 2.131}


def fires(effect: float, sd: float, n: int, rng: random.Random) -> bool:
    """One trial: does the 95% interval sit strictly above zero?"""
    xs = [rng.gauss(effect, sd) for _ in range(n)]
    m = st.fmean(xs)
    half = T_CRIT[n - 1] * st.stdev(xs) / sqrt(n)
    return m - half > 0.0


def table(sd: float, trials: int, seed: int = 23) -> dict[float, dict[int, int]]:
    rng = random.Random(seed)
    out: dict[float, dict[int, int]] = {}
    for effect in (0.50, 0.75, 1.00, 0.00):
        out[effect] = {
            n: round(100 * sum(fires(effect, sd, n, rng) for _ in range(trials)) / trials)
            for n in (8, 12, 16)
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sd", type=float, action="append", required=True,
                    help="archive NI-composite sd; repeat to compare")
    ap.add_argument("--trials", type=int, default=200_000)
    args = ap.parse_args()

    #: The table as it stands in rounds.md, so a drift is visible without
    #: opening the file. Simulated at 0.831 over 414 pairs, 40k trials.
    published = {0.50: (31, 48, 61), 0.75: (59, 81, 92), 1.00: (83, 96, 99),
                 0.00: (3, 3, 3)}

    print(f"{'effect':>8s}  {'published (0.831)':>18s}", end="")
    for sd in args.sd:
        print(f"  {'sd ' + format(sd, '.3f'):>18s}", end="")
    print("   worst cell drift")
    worst = 0
    for effect in (0.50, 0.75, 1.00, 0.00):
        row = f"{effect:+8.2f}  {'/'.join(str(x) for x in published[effect]):>18s}"
        for sd in args.sd:
            t = table(sd, args.trials)[effect]
            cells = [t[8], t[12], t[16]]
            row += f"  {'/'.join(str(c) for c in cells):>18s}"
            worst = max(worst, max(abs(c - p) for c, p in zip(cells, published[effect])))
        print(row)
    print(f"\nworst cell drift against the published table: {worst} point(s)")
    print("The table STANDS if this is <= 1 — r23's own criterion." if worst <= 1
          else "The table must be REPLACED: a cell moved by more than a point.")


if __name__ == "__main__":
    main()
