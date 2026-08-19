"""Read one saved stem in the PRE-REGISTERED order: gates first, delta second.

    poetry run python tests/e2e/read_prereg.py <stem> [hi_arm] [lo_arm]
    poetry run python tests/e2e/read_prereg.py r21-strong-current-build A2 A1.7

Free — reads the saved archive, calls no model. Not a pytest file on purpose: the
autouse `cleanup_graph_db` fixture would `DETACH DELETE` a live bench run's graph,
so the one script you want to run WHILE cells are in flight must not be a test.

WHY THIS IS CODE AND NOT A HABIT
================================
Every pre-registration block in this README ends with the same two sentences —
check the invalidating conditions BEFORE reading the delta, and read the delta
against the readings fixed in advance. Both were then done by hand, in whatever
order the interesting number happened to catch the eye. That is precisely the
archive's documented failure mode: "a result read after the fact acquires the
reading that fits it."

So the order is a function. It prints the build, then the gates, then the
endpoint, and it prints the verdict word — WINS / LOSES / UNRESOLVED — from the
interval rather than from prose written afterwards.

TWO BUGS THIS SCRIPT ALREADY CAUGHT IN ITSELF, both before r21 landed:

1. `Deltas.add` does NO arm filtering. Hand-feeding a `Deltas` every comparison
   in a file pooled all arm pairs into one number and printed a confident
   "FRAMEWORK WINS (+0.455, n=72)" for a stem whose real A2-vs-A1.7 line is
   +0.185 and unresolved. `collect_deltas` keys by (arm_a, arm_b); use it.
2. The X/Y gate pooled every arm pair too, so a balanced split could hide a
   lopsided one inside the pair actually being read.

Validated by reproducing the three strong-tier A2-vs-A1.7 sets the r21 block
pre-registered as its baseline: -0.299, +0.146, -0.208. Those come from the
canonical stems, NOT the `-rejudged` copies (which score the same cells twice and
which `across_runs._stems` excludes for that reason) — reading the wrong pair of
files here reproduces neither number and would have silently redefined the
baseline the run was pre-registered against.

AND A THIRD, caught while r23's cells were still in flight — same shape, one axis
over. Both bugs above were "the code pooled an axis the reading distinguishes";
this script kept doing it for SCENARIO. The endpoint loop keyed on tier alone and
GATE 2's strata on (tier, session), so a stem holding two scenarios printed one
composite over both. r23 is exactly that stem, and its pre-registration says, in
the same breath as the command that invokes this script: "read each control
SEPARATELY — never pooled into one 'controls' number." A pooled control is not a
weaker control, it is a different and unasked question: two tripwires averaged
together can each fire while their mean sits quietly inside zero.

So the per-scenario breakdown prints FIRST and the pooled line prints after,
labelled. The order is deliberate for the same reason the gates precede the
endpoint — whichever number is printed first is the one that gets read. The
pooled line is kept rather than removed because the r21/r22 baselines this
archive is measured against were computed pooling `cofounder_equity` with
`cofounder_ladder_return`; deleting it would make those numbers unreproducible
by the one script that is supposed to reproduce them. Pooling is a legitimate
reading. Pooling *silently*, in a file that holds a control, is the bug.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.e2e.models import Arm, Comparison, RunRecord  # noqa: E402
from tests.e2e.report import (  # noqa: E402
    collect_deltas,
    drop_invalid,
    invalid_cells,
    load_records,
)

RESULTS = Path(__file__).resolve().parent / "results"

WINS = "FRAMEWORK WINS (CI entirely above zero)"
LOSES = "FRAMEWORK LOSES (CI entirely below zero)"
UNRESOLVED = "UNRESOLVED (CI covers zero) — a bound, not a verdict"
NO_INTERVAL = "no interval"


def verdict_for(ci: tuple[float, float] | None) -> str:
    """The verdict word, derived from the interval and from nothing else.

    A pure function on purpose, and separate from `read` on purpose: `results/`
    is gitignored, so a verdict rule that lived inside the file-reading loop
    could only ever be checked on the archive of whoever happened to have run
    the bench. This is the one line of this script that must not be able to
    drift, so it is testable without any saved run.

    Note what is NOT here: no tolerance, no "grazes zero" band, no
    "directionally positive". r21 came in at [-0.003, +0.653] — three
    thousandths from a win — and the whole value of pre-registration is that
    such an interval reads UNRESOLVED without anyone having to be strong-minded
    about it in the moment.
    """
    if ci is None:
        return NO_INTERVAL
    if ci[0] > 0:
        return WINS
    if ci[1] < 0:
        return LOSES
    return UNRESOLVED


POOLED_HEADER = "POOLED ACROSS {n} SCENARIOS — not a per-control reading"


def scenarios_in(comparisons: list[Comparison], hi: Arm, lo: Arm) -> list[str]:
    """Which scenarios the arm pair was judged on, sorted.

    Filtered to the pair being read for the same reason `collect_deltas` keys by
    it: a scenario present only for some other arm pair is not part of this
    reading, and counting it would make the script announce a split it is not
    about to print.
    """
    return sorted({c.scenario_key for c in comparisons if (c.arm_a, c.arm_b) == (hi, lo)})


def print_endpoint(
    comparisons: list[Comparison],
    runs: list[RunRecord],
    hi: Arm,
    lo: Arm,
    heading: str,
) -> None:
    """One endpoint block: composite, sd, CI and verdict per tier.

    Takes already-filtered comparisons so the caller decides the slice — the
    per-scenario and pooled blocks are then literally the same code over
    different inputs, which is the only way the two can't drift apart.
    """
    print("=" * 74)
    print(heading)
    print("=" * 74)
    grouped = collect_deltas(comparisons)
    deltas = grouped.get((hi, lo))
    if deltas is None:
        print(
            f"  no judged pairs for {hi.value} vs {lo.value}; slice has: "
            f"{sorted(a.value + ' vs ' + b.value for a, b in grouped)}"
        )
        return
    for tier in sorted({r.tier for r in runs}):
        composite = deltas.composite(tier)
        if composite is None:
            print(f"  {tier:7} no pairs")
            continue
        ci = deltas.composite_ci(tier)
        sd = deltas.composite_sd(tier)
        ci_s = "n/a" if ci is None else f"[{ci[0]:+.3f},{ci[1]:+.3f}]"
        sd_s = "n/a" if sd is None else f"{sd:.3f}"
        print(
            f"  {tier:7} composite {composite:+.3f}  sd {sd_s}  "
            f"95%CI {ci_s}  pairs n={deltas.composite_n(tier)}"
        )
        print(f"          -> {verdict_for(ci)}")


def read(stem: str, pair: tuple[str, str] = ("A2", "A1.7")) -> int:
    path = RESULTS / f"{stem}.json"
    if not path.exists():
        print(f"NO SUCH STEM: {path}")
        return 1
    payload = load_records(path)
    runs = [RunRecord.model_validate(r) for r in payload["runs"]]
    comparisons = [Comparison.model_validate(c) for c in payload["comparisons"]]
    hi, lo = Arm(pair[0]), Arm(pair[1])

    print("=" * 74)
    print(f"BUILD — {stem}")
    print("=" * 74)
    build = payload.get("build")
    if not build:
        # Absent is not "same build as the next one" — see `report.build_provenance`.
        print("  ABSENT (run predates provenance recording) — NOT 'same build'")
    else:
        for key in ("git_sha", "dirty", "prompt_file", "prompt_sha", "error"):
            if key in build:
                print(f"  {key:12} {build[key]}")

    print()
    print("=" * 74)
    print("GATE 1 — invalidating checks (BEFORE any delta is read)")
    print("=" * 74)
    errored = [r for r in runs if r.error]
    print(f"  cells                     {len(runs)}")
    print(f"  cells with `error` set    {len(errored)}")
    for r in errored:
        print(f"      {r.arm.value}|{r.tier}|{r.replicate}|{r.branch}: {r.error}")

    with_turn_errors = [r for r in runs if r.turn_errors]
    print(f"  cells with turn_errors    {len(with_turn_errors)}")
    for r in with_turn_errors:
        print(
            f"      {r.arm.value}|{r.tier}|{r.replicate}|{r.branch}: "
            f"{len(r.turn_errors)} turn(s) -> {r.turn_errors[0][:90]}"
        )

    collapsed = [r for r in runs if r.collapsed_to_a1]
    print(f"  A2 collapsed_to_a1        {len(collapsed)}")
    for r in collapsed:
        print(f"      {r.arm.value}|{r.tier}|{r.replicate}|{r.branch}")

    print(f"  all_turns_errored         {len([r for r in runs if r.all_turns_errored])}")
    print(f"  invalid_as_evidence       {len(invalid_cells(runs))}")

    kept, dropped = drop_invalid(comparisons, runs)
    print(
        f"  comparisons               {len(comparisons)} "
        f"(dropped {dropped}, kept {len(kept)})"
    )

    print()
    print("=" * 74)
    print("GATE 2 — judge-side: X/Y split per stratum")
    print("=" * 74)
    # Orientation balance WITHIN the pair being read. A judge that always sees the
    # framework as X can score position rather than content, and a lopsided split
    # is what cost r4 a re-judge.
    # Keyed by scenario too: a lopsided X/Y split inside ONE scenario averages
    # away against the other one's, which is bug #2 above with the scenario axis
    # substituted for the arm axis.
    strata: dict[tuple[str, str, str], list[str]] = {}
    for c in kept:
        if (c.arm_a, c.arm_b) != (hi, lo):
            continue
        key = (c.tier, c.scenario_key, c.session_label or "-")
        strata.setdefault(key, []).append(c.x_arm.value)
    for key, xs in sorted(strata.items()):
        counts: dict[str, int] = {}
        for x in xs:
            counts[x] = counts.get(x, 0) + 1
        print(f"  {key[0]:7} {key[1]:22} {key[2]:10} n={len(xs):3d}  X-arm: {counts}")

    print()
    scenarios = scenarios_in(kept, hi, lo)
    if not scenarios:
        print("=" * 74)
        print(f"ENDPOINT — composite, {hi.value} vs {lo.value} (the pre-registered one)")
        print("=" * 74)
        print(
            f"  no judged pairs for {hi.value} vs {lo.value}; file has: "
            f"{sorted(a.value + ' vs ' + b.value for a, b in collect_deltas(kept))}"
        )
        return 1

    if len(scenarios) > 1:
        # First, and once per scenario. A control read pooled answers a question
        # nobody pre-registered.
        for scenario in scenarios:
            slice_ = [c for c in kept if c.scenario_key == scenario]
            print_endpoint(
                slice_,
                runs,
                hi,
                lo,
                f"ENDPOINT — {scenario} — composite, {hi.value} vs {lo.value}",
            )
            print()

    heading = f"ENDPOINT — composite, {hi.value} vs {lo.value} (the pre-registered one)"
    if len(scenarios) > 1:
        heading = f"ENDPOINT — {POOLED_HEADER.format(n=len(scenarios))}"
    print_endpoint(kept, runs, hi, lo, heading)

    return 0


if __name__ == "__main__":
    out_stem = sys.argv[1] if len(sys.argv) > 1 else "r21-strong-current-build"
    out_pair = (sys.argv[2], sys.argv[3]) if len(sys.argv) > 3 else ("A2", "A1.7")
    raise SystemExit(read(out_stem, out_pair))
