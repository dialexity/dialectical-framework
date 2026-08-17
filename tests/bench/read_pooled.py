"""Pool two or more saved stems into ONE endpoint — but only if they may be pooled.

    poetry run python tests/bench/read_pooled.py <stem> <stem> [... --pair A2 A1.7]
    poetry run python tests/bench/read_pooled.py r21-strong-current-build r22-strong-pooled

Free — reads the saved archive, calls no model. Not a pytest file, for the same
reason as `read_prereg.py`: the autouse `cleanup_graph_db` fixture would
`DETACH DELETE` a live bench run's graph.

WHY THIS EXISTS, AND WHY IT REFUSES BY DEFAULT
==============================================
Pooling is the cheapest way to buy resolution and the cheapest way to launder a
result. This archive already has the cautionary case written into its README: the
three August-10 strong-tier sets cannot be pooled with r21 because 16 commits
landed on `advisor/system_prompts.py` in between, and pooling them would turn a
build change into extra n. It also has the case where pooling IS the right move:
r21 and r22 are the same `git_sha`-lineage build, and `git diff` between them
touches nothing outside `tests/bench/`.

So the build check is not advisory. This script computes the endpoint ONLY when
every stem agrees on `prompt_sha`, and prints REFUSED otherwise. `--force` exists
for the case where a human has an argument, and it stamps the output with the
fact that it was forced so a forced number cannot be quoted as an ordinary one.

A run with NO recorded `build` block is never poolable without `--force`: absent
provenance reads as ABSENT, not as "same build as the other one". Every pre-r21
stem in this archive is in that category.

THE UNIT PROBLEM, WHICH POOLING MAKES WORSE
===========================================
The pre-registered endpoint is the flat mean over judged PAIRS, and 4 pairs come
from one replicate (2 sessions x 2 branches sharing an opening). Pairs within a
replicate are therefore not independent, and the flat CI is only honest if the
intra-replicate correlation is <= 0.

On r21 it is NEGATIVE (ICC -0.178), so the flat interval is the CONSERVATIVE one
and the replicate-level interval is tighter: [-0.003, +0.653] flat against
[+0.031, +0.619] by replicate. That is the opposite of the usual clustering
story, and it is why this script prints BOTH and treats the flat one as primary:
switching to the unit that happens to exclude zero, after seeing that it does, is
exactly the move the pre-registration exists to forbid. If a later run shows a
POSITIVE ICC, the flat interval becomes the anti-conservative one and the
replicate level must become primary — the script prints the ICC on every read so
that switch is a visible, argued decision rather than a silent one.
"""
from __future__ import annotations

import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.bench.models import Arm, Comparison, RunRecord  # noqa: E402
from tests.bench.read_prereg import verdict_for  # noqa: E402
from tests.bench.report import drop_invalid, load_records  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"

#: Student t, two-sided 95%, by degrees of freedom. Small-n honesty: using 1.96
#: at n=5 understates the interval by ~30%, and the replicate-level read is n=5.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
    24: 2.064, 29: 2.045, 39: 2.023, 49: 2.010, 59: 2.001,
}


def _t95(df: int) -> float:
    if df < 1:
        return float("nan")
    if df in _T95:
        return _T95[df]
    for key in sorted(_T95):
        if key >= df:
            return _T95[key]
    return 1.96


def _ci(values: list[float]) -> tuple[float, float] | None:
    if len(values) < 2:
        return None
    se = st.stdev(values) / math.sqrt(len(values))
    half = _t95(len(values) - 1) * se
    mean = st.fmean(values)
    return (mean - half, mean + half)


def _icc(groups: dict[object, list[float]]) -> tuple[float, float] | None:
    """One-way ANOVA ICC and the design effect, or None if it is undefined."""
    sizes = [len(v) for v in groups.values() if v]
    if len(sizes) < 2 or sum(sizes) <= len(sizes):
        return None
    flat = [v for vs in groups.values() for v in vs]
    grand = st.fmean(flat)
    k = st.fmean(sizes)
    msb = sum(
        len(vs) * (st.fmean(vs) - grand) ** 2 for vs in groups.values() if vs
    ) / (len(sizes) - 1)
    msw = sum(
        (v - st.fmean(vs)) ** 2 for vs in groups.values() if vs for v in vs
    ) / (sum(sizes) - len(sizes))
    if msb + (k - 1) * msw == 0:
        return None
    icc = (msb - msw) / (msb + (k - 1) * msw)
    return icc, 1 + (k - 1) * icc


def read(stems: list[str], pair: tuple[str, str], force: bool = False) -> int:
    hi, lo = Arm(pair[0]), Arm(pair[1])

    print("=" * 74)
    print(f"POOLED READ — {' + '.join(stems)}")
    print("=" * 74)

    payloads: dict[str, dict] = {}
    for stem in stems:
        path = RESULTS / f"{stem}.json"
        if not path.exists():
            print(f"NO SUCH STEM: {path}")
            return 1
        payloads[stem] = load_records(path)

    # -- the gate that must come first: may these be pooled at all? -----------
    shas: dict[str, str | None] = {}
    for stem, payload in payloads.items():
        build = payload.get("build") or {}
        sha = build.get("prompt_sha")
        shas[stem] = sha
        git_sha = (build.get("git_sha") or "")[:7] or "ABSENT"
        dirty = build.get("dirty", "ABSENT")
        print(
            f"  {stem:34} git {git_sha:8} dirty {str(dirty):6} "
            f"prompt_sha {(sha or 'ABSENT')[:7]}"
        )

    distinct = {s for s in shas.values() if s}
    missing = [stem for stem, s in shas.items() if not s]
    poolable = len(distinct) == 1 and not missing

    print()
    if poolable:
        print("  POOLABLE: one prompt_sha across every stem, provenance present.")
    else:
        reason = []
        if missing:
            reason.append(f"provenance ABSENT in {', '.join(missing)}")
        if len(distinct) > 1:
            reason.append(f"{len(distinct)} distinct prompt_sha values")
        print(f"  NOT POOLABLE: {'; '.join(reason)}")
        if not force:
            print()
            print("  REFUSED — pooling across builds launders a build change into")
            print("  extra n. Read the stems separately with read_prereg.py, or")
            print("  pass --force and say in the write-up that it was forced.")
            return 2
        print("  !! FORCED — this number is NOT an ordinary pooled endpoint.")

    # -- the endpoint ---------------------------------------------------------
    per_replicate: dict[tuple[str, int], list[float]] = defaultdict(list)
    flat: list[float] = []
    kept_total = dropped_total = 0
    for stem, payload in payloads.items():
        runs = [RunRecord.model_validate(r) for r in payload["runs"]]
        comparisons = [Comparison.model_validate(c) for c in payload["comparisons"]]
        kept, dropped = drop_invalid(comparisons, runs)
        dropped_total += dropped
        for c in kept:
            if (c.arm_a, c.arm_b) != (hi, lo) or not c.scores:
                continue
            cell = st.fmean([a - b for a, b in c.scores.values()])
            flat.append(cell)
            # Replicate numbers restart per stem, so the key must carry the stem
            # or r21's rep 3 and r22's rep 3 collapse into one cluster.
            per_replicate[(stem, c.replicate)].append(cell)
            kept_total += 1

    print()
    print("=" * 74)
    print(f"ENDPOINT — {hi.value} vs {lo.value}")
    print("=" * 74)
    if len(flat) < 2:
        print(f"  only {len(flat)} judged pair(s) — no interval")
        return 1
    print(f"  invalid cells dropped: {dropped_total}")

    mean = st.fmean(flat)
    ci = _ci(flat)
    print(
        f"  FLAT (pre-registered unit)     {mean:+.3f}  sd {st.stdev(flat):.3f}  "
        f"95%CI [{ci[0]:+.3f},{ci[1]:+.3f}]  n={len(flat)}"
    )
    print(f"          -> {verdict_for(ci)}")

    rep_means = [st.fmean(v) for v in per_replicate.values() if v]
    rep_ci = _ci(rep_means)
    if rep_ci is not None:
        print(
            f"  BY REPLICATE (secondary)       {st.fmean(rep_means):+.3f}  "
            f"sd {st.stdev(rep_means):.3f}  "
            f"95%CI [{rep_ci[0]:+.3f},{rep_ci[1]:+.3f}]  n={len(rep_means)}"
        )
        print(f"          -> {verdict_for(rep_ci)}")

    measured = _icc(dict(per_replicate))
    if measured is not None:
        icc, deff = measured
        print()
        print(f"  intra-replicate ICC {icc:+.3f}  design effect {deff:.3f}")
        if icc <= 0:
            print(
                "  ICC <= 0: pairs within a replicate are LESS alike than across,\n"
                "  so the FLAT interval is the conservative one and stays primary."
            )
        else:
            print(
                "  !! ICC > 0: the flat interval is now ANTI-conservative — it\n"
                "  treats correlated pairs as independent. The replicate-level\n"
                "  row is the honest one and the write-up must say so."
            )
    return 0


if __name__ == "__main__":
    argv = [a for a in sys.argv[1:]]
    forced = "--force" in argv
    argv = [a for a in argv if a != "--force"]
    if "--pair" in argv:
        i = argv.index("--pair")
        out_pair = (argv[i + 1], argv[i + 2])
        argv = argv[:i] + argv[i + 3:]
    else:
        out_pair = ("A2", "A1.7")
    if not argv:
        print(__doc__)
        raise SystemExit(1)
    raise SystemExit(read(argv, out_pair, force=forced))
