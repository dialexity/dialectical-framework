"""Where the search stands: coverage, gaps, and what is unread. Free.

    poetry run python tests/e2e/status.py            # the whole board
    poetry run python tests/e2e/status.py coverage   # one section, named
    poetry run python tests/e2e/status.py --help

WHY THIS EXISTS AS A SCRIPT AND NOT AS PROSE
============================================
The archive's numbers were re-derived by hand in every session that touched it,
and the hand-derived ones kept being wrong: an A1.7/graph attribution stated
backwards, "20 poolable strong pairs" that were 5 replicates re-judged twice,
a per-session table averaged across two rounds. Each error survived because the
figure lived in a sentence, and a sentence cannot be re-run.

So the rule for `/e2e` and for `README.md`: **prose carries judgement, this
script carries numbers.** If a status claim cannot be printed from here, it is
not a status claim, it is a memory.

IT READS THROUGH `valid_comparisons`, WHICH IS THE WHOLE POINT
=============================================================
Reading `payload["comparisons"]` directly is the mistake this module exists to
stop making. A dead cell (empty transcript, timed-out cell, an A2 run that
collapsed to A1) judges fine and scores like a catastrophically bad arm, so raw
counts are inflated by exactly the rows that must not vote. `valid_comparisons`
applies `drop_invalid`; the difference between the two counts is reported below
as `dropped`, because a scenario whose coverage is mostly dead cells looks
identical to a well-covered one until you print it.
"""

from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
if str(E2E_DIR.parent) not in sys.path:  # `python tests/e2e/status.py` directly
    sys.path.insert(0, str(E2E_DIR.parent))

from e2e.across_runs import RESULTS, SUPERSEDED, _stems, valid_comparisons
from e2e.models import SUBSTANCE_DIMENSIONS, Comparison, RunRecord
from e2e.report import drop_invalid, load_records
from e2e.scenarios import ALL_SCENARIOS


def _all_valid() -> list[tuple[str, Comparison]]:
    """(stem, comparison) for every poolable run, invalid cells removed."""
    out: list[tuple[str, Comparison]] = []
    for stem in _stems():
        for comparison in valid_comparisons(stem):
            out.append((stem, comparison))
    return out


def cell_id(stem: str, comparison: Comparison) -> tuple[str, str, int]:
    """The identity of one independent cell — the archive's unit of analysis.

    `stem` is load-bearing and was omitted on the first attempt. Replicate 1 of
    `ladder-return-r16` and replicate 1 of `ladder-return-r18` are different
    cells run against different BUILDS; keying on `(tier, replicate)` collapses
    every round into one and under-reports independent evidence several-fold.

    Every section that counts cells goes through here rather than building the
    tuple inline, so the unit cannot differ between two sections of one board —
    and so a test can pin it (`TestTheStatusBoardReadsTheArchiveCorrectly`).
    """
    return (stem, comparison.tier, comparison.replicate)


def _raw_and_dropped() -> tuple[Counter, Counter]:
    """Per scenario: judged rows as saved, and how many `drop_invalid` removes.

    Both are needed. Raw alone overstates coverage; valid alone hides that a
    scenario's cells are dying, which is a harness or arm defect rather than a
    coverage fact.
    """
    raw: Counter = Counter()
    dropped: Counter = Counter()
    for stem in _stems():
        payload = load_records(RESULTS / f"{stem}.json")
        comparisons = [
            Comparison.model_validate(c) for c in payload.get("comparisons") or []
        ]
        runs = [RunRecord.model_validate(r) for r in payload.get("runs") or []]
        kept, _n_dropped = drop_invalid(comparisons, runs)
        # `drop_invalid` returns a COUNT, not the rows, and the count is
        # archive-wide rather than per scenario. Identity-diffing the kept list
        # is what attributes a drop to the scenario that suffered it.
        kept_ids = {id(c) for c in kept}
        for c in comparisons:
            raw[c.scenario_key] += 1
            if id(c) not in kept_ids:
                dropped[c.scenario_key] += 1
    return raw, dropped


def coverage() -> None:
    """Which scenarios the archive actually covers — the first thing to read.

    A declared scenario with zero judged cells is not a weak result, it is an
    unopened box. The archive has historically been dominated by two of them,
    which bounds every "the framework is doing fine" reading to those two.
    """
    declared = {s.key: s.kind for s in ALL_SCENARIOS}
    raw, dropped = _raw_and_dropped()
    valid: Counter = Counter()
    tiers: dict[str, set[str]] = defaultdict(set)
    reps: dict[str, set[tuple]] = defaultdict(set)
    for stem, c in _all_valid():
        valid[c.scenario_key] += 1
        tiers[c.scenario_key].add(c.tier)
        reps[c.scenario_key].add(cell_id(stem, c))

    total = sum(valid.values()) or 1
    print("## Coverage — judged cells per scenario (valid only)\n")
    print(f"{'scenario':30} {'kind':10} {'valid':>6} {'share':>7} "
          f"{'drop':>5} {'cells':>6}  tiers")
    print("-" * 84)
    for key, kind in declared.items():
        kind_name = getattr(kind, "name", str(kind)).lower()
        tier_list = ",".join(sorted(tiers[key])) or "-"
        share = f"{100 * valid[key] / total:.1f}%" if valid[key] else "-"
        print(f"{key:30} {kind_name:10} {valid[key]:>6} {share:>7} "
              f"{dropped[key]:>5} {len(reps[key]):>6}  {tier_list}")
    print("-" * 84)
    print(f"{'TOTAL':30} {'':10} {sum(valid.values()):>6} {'':>7} "
          f"{sum(dropped.values()):>5} "
          f"{sum(len(v) for v in reps.values()):>6}")

    unopened = [k for k in declared if not valid[k]]
    if unopened:
        print(f"\nNEVER JUDGED ({len(unopened)}): {', '.join(unopened)}")
    thin = [k for k in declared if 0 < len(reps[k]) <= 3]
    if thin:
        print(f"THIN (<=3 independent cells): {', '.join(thin)}")

    ranked = valid.most_common()
    if len(ranked) >= 2:
        top2 = 100 * (ranked[0][1] + ranked[1][1]) / total
        print(f"\nCONCENTRATION: {ranked[0][0]} + {ranked[1][0]} = "
              f"{top2:.1f}% of all judged evidence.")
        print("  Every archive-wide claim is a claim about those two situations.")
    if raw and sum(dropped.values()):
        print(f"  (raw judged rows {sum(raw.values())}, "
              f"{sum(dropped.values())} dropped as invalid — see valid_comparisons)")


def unread() -> None:
    """Runs that exist on disk but were never judged, and controls never run.

    The dangerous item is not a missing scenario, it is a scenario whose RUNS
    are saved and whose judging never happened: its transcripts are paid for and
    re-judging is minutes instead of hours (`DIALEXITY_E2E_REJUDGE`).
    """
    print("## Unread — paid for, not yet read\n")
    rows = []
    for path in sorted(RESULTS.glob("*.json")):
        stem = path.stem
        if stem.endswith("-runs"):
            continue
        payload = load_records(path)
        runs = payload.get("runs") or []
        comparisons = payload.get("comparisons") or []
        if runs and not comparisons:
            scen = sorted({r.get("scenario_key") for r in runs})
            rows.append((stem, len(runs), ",".join(scen)))
    if rows:
        print(f"{'stem':38} {'runs':>5}  scenarios")
        print("-" * 84)
        for stem, n, scen in rows:
            print(f"{stem:38} {n:>5}  {scen}")
        print("\nRe-judge one without re-running it:")
        print("  DIALEXITY_E2E_REJUDGE=<stem> poetry run pytest \\")
        print("    tests/e2e/test_e2e_run.py::test_e2e_rejudge --real-llm -s")
    else:
        print("(none — every saved run has been judged)")

    if SUPERSEDED:
        print(f"\nSUPERSEDED (excluded from every pooled cut): "
              f"{', '.join(f'{k} -> {v}' for k, v in SUPERSEDED.items())}")


def deltas() -> None:
    """A2's SUBSTANCE gap per (pair, scenario, session) — never pooled blind.

    Pooling across sessions is the specific error this section refuses to make:
    on the return lane the framework LOSES inside the first session and wins at
    the return, in fixed proportion by design, so a pooled mean is an artefact of
    the scenario's shape. Sessions are printed separately, always.

    No confidence intervals here on purpose — `read_pooled.py` and
    `read_prereg.py` own the inferential apparatus. This is a board, not a claim.
    """
    print("## SUBSTANCE gap (A2 minus opponent, judge points, -4..+4)\n")
    cells: dict[tuple, list[float]] = defaultdict(list)
    clusters: dict[tuple, set] = defaultdict(set)
    for stem, c in _all_valid():
        gaps = [
            a - b
            for dim, (a, b) in c.scores.items()
            if dim in SUBSTANCE_DIMENSIONS
        ]
        if not gaps:
            continue
        key = (f"{c.arm_a.value}-{c.arm_b.value}", c.scenario_key,
               c.tier, c.session_label or "-")
        cells[key].append(sum(gaps) / len(gaps))
        clusters[key].add(cell_id(stem, c))

    print(f"{'pair':11} {'scenario':26} {'tier':7} {'session':11} "
          f"{'n':>4} {'reps':>5} {'mean':>8}")
    print("-" * 84)
    for key in sorted(cells):
        vals = cells[key]
        mean = sum(vals) / len(vals)
        print(f"{key[0]:11} {key[1]:26} {key[2]:7} {key[3]:11} "
              f"{len(vals):>4} {len(clusters[key]):>5} {mean:>+8.3f}")
    print("-" * 84)
    print("`reps` is the independent unit, `n` is not. One scenario at one tier")
    print("means the unit is replicates however many comparisons it produced.")
    print("For intervals: read_pooled.py / read_prereg.py.")


SECTIONS = {
    "coverage": coverage,
    "unread": unread,
    "deltas": deltas,
}


def main(argv: list[str]) -> int:
    if "--help" in argv or "-h" in argv:
        print(__doc__)
        print("sections:", ", ".join(SECTIONS))
        return 0
    named = [a for a in argv if not a.startswith("-")]
    chosen = named or list(SECTIONS)
    unknown = [n for n in chosen if n not in SECTIONS]
    if unknown:
        print(f"unknown section(s): {unknown}. known: {list(SECTIONS)}")
        return 2
    for i, name in enumerate(chosen):
        if i:
            print()
        SECTIONS[name]()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
