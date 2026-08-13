"""Split the bench's noise into judge noise and real cell-to-cell variation.

    poetry run python tests/bench/judge_variance.py

`noise_floor.py` says a delta's within-dimension sd is ~1.11 rubric steps. It
cannot say WHERE that comes from, and the answer changes what the next run should
buy. Two sources are confounded in it:

  * **judge noise** — the same transcript pair scored differently on a second
    pass. Cheap to beat: judge each pair K times and average, no new cells.
  * **cell variation** — different transcripts genuinely differing. Only more
    replicates reduce it, at full generation cost (~an hour of LLM per A2 cell).

Two runs in `results/` were re-judged from their saved transcripts
(`decision-strong-r3`/`-rejudged`, `decision-strong-r4`/`-rejudged`), which is
the same-pair-twice design this needs. Matching a comparison across the two
records by (scenario, tier, replicate, arm pair, session), the difference of the
two passes on one pair has variance 2*sigma_judge^2 — so sigma_judge falls out,
and sigma_cell^2 = sigma_total^2 - sigma_judge^2.

This is a MEASUREMENT script, not a test: it prints and exits 0. The numbers it
produces are quoted in `README.md`; re-run it when a new re-judged pair lands.
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

#: (original, re-judged) stems. A pair qualifies only if the second was produced
#: by DIALEXITY_BENCH_REJUDGE over the first's transcripts — same cells, new
#: judge pass. Anything else measures cell variation too and defeats the split.
_REJUDGED_PAIRS = (
    ("decision-strong-r3", "decision-strong-r3-rejudged"),
    ("decision-strong-r4", "decision-strong-r4-rejudged"),
)


def _key(c: dict) -> tuple:
    return (
        c.get("scenario_key"),
        c.get("tier"),
        c.get("replicate"),
        c.get("arm_a"),
        c.get("arm_b"),
        c.get("session_label"),
    )


def _deltas_by_key(stem: str) -> dict[tuple, dict[str, float]]:
    """key -> dimension -> (A - B), for every scorable comparison."""
    d = json.loads((RESULTS / f"{stem}.json").read_text())
    out: dict[tuple, dict[str, float]] = {}
    for c in d.get("comparisons") or []:
        if c.get("error"):
            continue
        out[_key(c)] = {dim: a - b for dim, (a, b) in c["scores"].items()}
    return out


def split_variance(
    repeat_diffs: dict[str, list[float]], totals: dict[str, list[float]]
) -> tuple[list[tuple[float, str, float, float]], float, float, float]:
    """(rows, median sigma_judge, median sigma_total, implied sigma_cell).

    Pure so it can be pinned by a test: the estimator is the whole claim here,
    and a sign error in `/sqrt(2)` or a subtraction done in sd space instead of
    variance space would produce a plausible number pointing the opposite way.
    Rows are `(judge share of variance, dimension, sigma_judge, sigma_total)`,
    descending by share.
    """
    rows: list[tuple[float, str, float, float]] = []
    judge_sds: list[float] = []
    total_sds: list[float] = []
    for dim in sorted(repeat_diffs):
        diffs, tot = repeat_diffs[dim], totals.get(dim, [])
        if len(diffs) < 3 or len(tot) < 3:
            continue
        # Var(pass1 - pass2) = 2*sigma_judge^2. The mean is NOT assumed zero —
        # a second pass can be systematically harsher — so stdev, not RMS.
        s_judge = st.stdev(diffs) / math.sqrt(2)
        s_total = st.stdev(tot)
        judge_sds.append(s_judge)
        total_sds.append(s_total)
        share = (s_judge / s_total) ** 2 if s_total else float("nan")
        rows.append((share, dim, s_judge, s_total))
    if not judge_sds:
        return [], 0.0, 0.0, 0.0
    mj, mt = st.median(judge_sds), st.median(total_sds)
    # Variance is additive, sd is not. A non-positive residual means judge noise
    # alone explains the observed spread — the cells are indistinguishable.
    resid = mt**2 - mj**2
    return sorted(rows, reverse=True), mj, mt, math.sqrt(resid) if resid > 0 else 0.0


def se_of_mean(
    sigma_judge: float, sigma_cell: float, cells: int, passes: int
) -> float:
    """SE of a dimension's mean delta for `cells` pairs judged `passes` times.

    Averaging K judge passes divides ONLY the judge component; adding cells
    divides both. That asymmetry is the decision this script exists to inform.
    """
    return math.sqrt(sigma_judge**2 / passes + sigma_cell**2) / math.sqrt(cells)


def main() -> int:
    #: dimension -> list of (pass1 - pass2) on the SAME pair
    repeat_diffs: dict[str, list[float]] = defaultdict(list)
    #: dimension -> list of pass-1 deltas, for the total spread on these cells
    totals: dict[str, list[float]] = defaultdict(list)
    matched = 0

    for original, rejudged in _REJUDGED_PAIRS:
        try:
            a, b = _deltas_by_key(original), _deltas_by_key(rejudged)
        except FileNotFoundError as exc:
            print(f"skip {original}: {exc}")
            continue
        for key, dims_a in a.items():
            dims_b = b.get(key)
            if dims_b is None:
                continue
            matched += 1
            for dim, va in dims_a.items():
                if dim in dims_b:
                    repeat_diffs[dim].append(va - dims_b[dim])
                    totals[dim].append(va)

    if not matched:
        print("no comparisons matched across any re-judged pair")
        return 1

    print(f"matched pairs judged twice: {matched}")
    print(f"dimensions: {len(repeat_diffs)}")
    print()

    rows, mj, mt, m_cell = split_variance(repeat_diffs, totals)
    if not rows:
        print("not enough repeated dimensions to estimate")
        return 1

    print(f"  {'dimension':24} {'sigma_judge':>11} {'sigma_total':>11} {'judge share':>12}")
    for share, dim, s_judge, s_total in rows:
        print(f"  {dim:24} {s_judge:>11.2f} {s_total:>11.2f} {share:>11.0%}")

    print()
    print(f"median sigma_judge  {mj:.2f}")
    print(f"median sigma_total  {mt:.2f}")
    print(f"implied sigma_cell  {m_cell:.2f}" + ("  (judge noise explains it all)" if not m_cell else ""))
    print(f"judge share of variance: {(mj / mt) ** 2:.0%}" if mt else "")
    print()

    # What each purchase buys. Printed side by side because the cheap axis is
    # only worth taking when its component dominates.
    print("SE of a dimension's mean delta, by what you buy:")
    print(f"  {'cells':>6} {'K=1':>7} {'K=2':>7} {'K=3':>7}")
    for n in (12, 24, 48):
        row = [se_of_mean(mj, m_cell, n, k) for k in (1, 2, 3)]
        print(f"  {n:>6} " + " ".join(f"{v:>7.2f}" for v in row))
    print()
    print(
        "Read this as: re-judging is only a substitute for replicates insofar as\n"
        "the judge share is large. Where sigma_cell dominates, K>1 buys nothing\n"
        "and the run needs cells — which cost LLM hours, not judge dollars."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
