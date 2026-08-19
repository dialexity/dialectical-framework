"""Compare the composite endpoint against its subscales, over every saved run.

    poetry run python tests/e2e/endpoint_power.py

`noise_floor.py` measures the spread of a single dimension's delta.
`judge_variance.py` says 70% of that spread is real cell variation, so it cannot
be judged away. This script asks the remaining question: given that the 12 rubric
dimensions are repeated measures on the SAME transcript pair, does averaging them
within a pair buy enough to make a run affordable?

It does, and the ratio is unusually stable. Across all 25 saved (run, arm-pair)
sets the composite's sd is **0.76** against a per-dimension median of **1.08** —
a ratio of **0.70** that barely moves between runs, arm pairs or tiers. A
0.5-step effect needs ~19 pairs on the composite against ~37 on a dimension.

Which is why `report.py` prints the composite ABOVE the dimension table: it is
the endpoint the product claim rests on and the only one this bench can resolve
at a price worth paying. Note the trap the report also prints: the composite is
quieter AND its effect is diluted by dimensions that show nothing, so it does not
always need fewer pairs than whichever subscale moved furthest. Sizing on that
subscale is choosing an endpoint after seeing the data.

A measurement script: prints and exits. The estimator it shares with the report
is `Deltas.composite*`, pinned by `TestThePrimaryEndpointIsPrinted`.
"""

from __future__ import annotations

import json
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def rows() -> list[tuple[str, str, int, float, float]]:
    """(stem, arm pair, pairs, sd of composite, median per-dimension sd)."""
    out: list[tuple[str, str, int, float, float]] = []
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
            composite = [
                st.mean([a - b for a, b in c["scores"].values()])
                for c in comps
                if c["scores"]
            ]
            per_dim: dict[str, list[float]] = defaultdict(list)
            for c in comps:
                for dim, (a, b) in c["scores"].items():
                    per_dim[dim].append(a - b)
            sds = [st.stdev(v) for v in per_dim.values() if len(v) >= 3]
            if len(composite) >= 3 and sds:
                out.append(
                    (path.stem, pair, len(composite), st.stdev(composite), st.median(sds))
                )
    return out


def main() -> int:
    data = rows()
    if not data:
        print("no saved comparisons in", RESULTS)
        return 1

    print(f"{'run':34}{'pair':16}{'pairs':>6}{'sd_comp':>9}{'sd_dim':>8}{'ratio':>7}")
    for stem, pair, n, sc, sd in data:
        print(f"{stem[:33]:34}{pair[:15]:16}{n:>6}{sc:>9.2f}{sd:>8.2f}{sc / sd:>7.2f}")

    comps = [r[3] for r in data]
    dims = [r[4] for r in data]
    ratios = [r[3] / r[4] for r in data if r[4]]
    mc, md = st.median(comps), st.median(dims)
    print()
    print(f"median sd composite {mc:.2f}   per-dimension {md:.2f}   ratio {mc / md:.2f}")
    # The ratio's own spread is the interesting part: a stable ratio means the
    # composite's advantage is a property of the rubric, not of one lucky run.
    print(
        f"ratio across {len(ratios)} sets: median {st.median(ratios):.2f}  "
        f"min {min(ratios):.2f}  max {max(ratios):.2f}"
    )
    print()
    print("pairs needed at 80% power:")
    print(f"  {'effect':>7} {'composite':>10} {'per-dim':>9}")
    for effect in (0.3, 0.5, 0.7, 1.0):
        print(
            f"  {effect:>7.1f} {math.ceil((2.8 * mc / effect) ** 2):>10} "
            f"{math.ceil((2.8 * md / effect) ** 2):>9}"
        )
    print()
    print(
        "Read this as: the composite is the affordable endpoint, not a free one.\n"
        "Even there, nothing under ~0.4 steps is reachable at a run size this\n"
        "bench has ever used — so a fix worth measuring has to be a big one."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
