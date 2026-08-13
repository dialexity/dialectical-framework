"""Measure this bench's own noise floor from every saved run.

    poetry run python tests/bench/noise_floor.py

Answers the question the judged-delta table cannot answer about itself: how big
must a gap be before it means anything? Pools the per-(run, arm-pair, dimension)
delta lists in `results/` and reports the within-dimension sd, then the 95%
half-width and the 80%-power MDE at the replicate counts this bench actually
runs.

Why it exists as a committed script rather than a one-off: the floor is a
property of the JUDGE and the rubric, so it drifts whenever either changes
(a re-worded dimension, a different judge model, a new scenario). A number
pasted into a comment goes stale silently; this re-derives it. `MEANINGFUL_GAP`
in `report.py` cites the median sd this prints, and
`TestDeltasCarryTheirUncertainty` asserts the citation is there.

As of 2026-08-13 (300 delta rows): median within-dimension sd **1.11** rubric
steps, so the 95% half-width is ~0.63 at n=12 and ~1.25 at n=3. Nearly every
gap this bench has ever printed is inside that, which is why the table now
prints intervals instead of bare means.
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

#: Replicate-count columns worth reporting: 3 and 6 are the `by session:` and
#: per-dimension granularities the report renders, 12 is a full r16-shaped run,
#: and 24/48 are what a resolvable run would cost.
_N_COLUMNS = (3, 6, 12, 24, 48)


def delta_rows() -> list[tuple[str, str, str, list[float]]]:
    """(stem, arm-pair, dimension, deltas) for every saved comparison set."""
    rows: list[tuple[str, str, str, list[float]]] = []
    for path in sorted(RESULTS.glob("*.json")):
        if path.stem.endswith("-runs"):
            continue
        try:
            d = json.loads(path.read_text())
        except Exception:  # noqa: BLE001 — a truncated record must not stop the sweep
            continue
        by_pair: dict[str, list[dict]] = defaultdict(list)
        for c in d.get("comparisons") or []:
            if c.get("error"):
                continue
            by_pair[f"{c['arm_a']} vs {c['arm_b']}"].append(c)
        for pair, comps in by_pair.items():
            by_dim: dict[str, list[float]] = defaultdict(list)
            for c in comps:
                for dim, (a, b) in c["scores"].items():
                    by_dim[dim].append(a - b)
            for dim, vals in by_dim.items():
                # n<3 has no usable spread; including it would drag the median
                # toward whatever a 2-sample sd happens to be.
                if len(vals) >= 3:
                    rows.append((path.stem, pair, dim, vals))
    return rows


def main() -> int:
    rows = delta_rows()
    if not rows:
        print("no saved comparisons in", RESULTS)
        return 1

    sds = [st.stdev(v) for *_ , v in rows]
    ns = [len(v) for *_, v in rows]
    sds_sorted = sorted(sds)
    median_sd = st.median(sds)

    print(f"delta rows (run x arm-pair x dimension): {len(rows)}")
    print(f"n per row: median {int(st.median(ns))}  min {min(ns)}  max {max(ns)}")
    print(
        "within-dimension sd of the delta: "
        f"median {median_sd:.2f}  mean {st.mean(sds):.2f}  "
        f"p10 {sds_sorted[len(sds_sorted) // 10]:.2f}  "
        f"p90 {sds_sorted[9 * len(sds_sorted) // 10]:.2f}"
    )
    print()
    print("at the median sd, per dimension:")
    print(f"  {'n':>4} {'SE':>6} {'95% half-width':>16} {'MDE (80% power)':>17}")
    for n in _N_COLUMNS:
        se = median_sd / math.sqrt(n)
        # 2.8 ~ (t_.975 + t_.80) for these n; exact enough for a planning number.
        print(f"  {n:>4} {se:>6.2f} {1.96 * se:>16.2f} {2.8 * se:>17.2f}")
    print()
    print(
        "Read this as: a printed gap smaller than its row's half-width is not a\n"
        "small effect, it is an unmeasured one. `report.MEANINGFUL_GAP` is a\n"
        "FIXED threshold kept only for the cross-tier trend and sits below this\n"
        "floor deliberately — the per-row intervals are the number to read."
    )

    # The noisiest and quietest dimensions are worth naming: a dimension whose
    # sd is twice the median needs twice the replicates to say anything, and
    # that is a rubric problem, not a framework one.
    per_dim: dict[str, list[float]] = defaultdict(list)
    for _stem, _pair, dim, vals in rows:
        per_dim[dim].append(st.stdev(vals))
    print("\nper-dimension median sd (higher = needs more replicates to resolve):")
    for dim, vals in sorted(per_dim.items(), key=lambda kv: -st.median(kv[1])):
        print(f"  {dim:24} {st.median(vals):.2f}  (rows: {len(vals)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
