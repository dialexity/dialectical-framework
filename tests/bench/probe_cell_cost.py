"""What does a cell cost, per arm and per tier?

    poetry run python tests/bench/probe_cell_cost.py
    poetry run python tests/bench/probe_cell_cost.py ladder-return

Free — reads `duration_s` off the saved archive, calls no model.

`RunRecord.duration_s` has been recorded since the first run and reported
nowhere, so every "A2 costs 5x A1" claim in this folder's notes was re-derived
by hand from a scrolling log. This is that derivation, once.

WHY IT IS WORTH A FILE
======================
Wall-clock is the binding constraint on the design of every run here: n, arms and
tiers are chosen against a budget of hours, and the pre-registration has to state
them before looking. A multiplier carried in someone's head gets applied to the
wrong baseline.

WHAT IT SHOWED, AND WHERE IT CORRECTED ME (2026-08-14)
======================================================
The claim I had been carrying — "A2 is ~5x A1 at BOTH tiers" — does not survive
its own measurement. Archive-wide it is **5.0x strong, 6.8x weak, and 14.7x on
`cofounder_ladder_return` alone**. The reading it supported still holds and is
the useful part: the multiplier tracks the FRAMEWORK (6N transformations per
wheel), not the model, since a strong A1 cell costs ~2x a weak one while the
A2/A1 ratio moves the other way. So raising the tier is cheap and raising the
arm is not, which is why r18 could swap the model without cutting n.

But "~5x at both tiers" was the strong tier's number generalised, and the lane
r18 actually runs is the most expensive one in the archive. Hence the per-tier
and per-stem breakdown below: a single pooled multiplier is what let a
tier-specific figure pass as a universal one.

The median is the headline, not the mean: A2 cells have a long right tail (a run
that explores more wheels takes proportionally longer, up to 2150s against a
753s median on this lane), and a mean lets one outlier set the budget.
"""

from __future__ import annotations

import statistics
import sys
from collections import defaultdict
from pathlib import Path

BENCH_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH_DIR.parent))

from bench.models import RunRecord  # noqa: E402
from bench.report import load_records  # noqa: E402

RESULTS = BENCH_DIR / "results"


def _stems(needle: str | None) -> list[str]:
    return sorted(
        p.stem
        for p in RESULTS.glob("*.json")
        # `-runs.json` is a duplicate copy of the same runs: including it doubles
        # every count. The bug that cost a corrected figure once already.
        if not p.stem.endswith(("-runs", "-rejudged"))
        and not p.stem.startswith("smoke")
        and (needle is None or needle in p.stem)
    )


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else None
    stems = _stems(needle)
    if not stems:
        print(f"no saved runs match {needle!r}")
        return 1

    by_tier_arm: dict[tuple[str, str], list[float]] = defaultdict(list)
    for stem in stems:
        payload = load_records(RESULTS / f"{stem}.json")
        by_cell: dict[tuple[str, str], list[float]] = defaultdict(list)
        for raw in payload.get("runs", []):
            try:
                run = RunRecord.model_validate(raw)
            except Exception:  # noqa: BLE001
                continue
            if not run.duration_s:
                continue
            by_cell[(run.tier, run.arm.value)].append(run.duration_s)
            by_tier_arm[(run.tier, run.arm.value)].append(run.duration_s)
        if not by_cell:
            continue
        total = sum(sum(v) for v in by_cell.values()) / 3600
        print(f"\n{stem}  ({total:.2f}h of wall-clock)")
        print(f"  {'tier':8}{'arm':7}{'n':>4}{'median':>9}{'mean':>9}{'max':>9}{'total':>8}")
        for (tier, arm), seconds in sorted(by_cell.items()):
            print(
                f"  {tier:8}{arm:7}{len(seconds):>4}"
                f"{statistics.median(seconds):>8.0f}s"
                f"{statistics.fmean(seconds):>8.0f}s"
                f"{max(seconds):>8.0f}s"
                f"{sum(seconds)/3600:>7.2f}h"
            )

    # Per TIER, never pooled across them. Pooling is how "~5x A1" — the strong
    # tier's ratio — got quoted as if it held everywhere, when weak is 6.8x.
    print("\nThe multiplier the budget is built on, PER TIER (pooling hid a 5.0 vs 6.8):")
    for tier in sorted({t for t, _ in by_tier_arm}):
        baseline = (
            statistics.median(by_tier_arm[(tier, "A1")])
            if (tier, "A1") in by_tier_arm
            else None
        )
        print(f"  {tier}:")
        for (a_tier, arm), seconds in sorted(by_tier_arm.items()):
            if a_tier != tier:
                continue
            median = statistics.median(seconds)
            ratio = f"{median / baseline:.1f}x A1" if baseline else "—"
            print(f"    {arm:7}n={len(seconds):>4}  median={median:>6.0f}s   {ratio}")
    print(
        "\nMedian, not mean: A2's right tail is long (more wheels explored = longer),\n"
        "and a budget set from a mean is set by its worst cell. And the ratio is\n"
        "LANE-dependent on top of tier — read the per-stem block above for the lane\n"
        "you are about to size, not the pooled figure."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
