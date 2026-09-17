"""Pool two or more saved stems into ONE endpoint — but only if they may be pooled.

    poetry run python tests/e2e/read_pooled.py <stem> <stem> [... --pair A2 A1.7]
    poetry run python tests/e2e/read_pooled.py r21-strong-current-build r22-strong-pooled

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
touches nothing outside `tests/e2e/`.

So the build check is not advisory. This script computes the endpoint ONLY when
every stem agrees on `prompt_sha`, and prints REFUSED otherwise. `--force` exists
for the case where a human has an argument, and it stamps the output with the
fact that it was forced so a forced number cannot be quoted as an ordinary one.

A run with NO recorded `build` block is never poolable without `--force`: absent
provenance reads as ABSENT, not as "same build as the other one". Every pre-r21
stem in this archive is in that category.

`prompt_sha` IS NOT ENOUGH, AND A15 IS THE CASE THAT PROVED IT
==============================================================
The prompt check watches the prompt SURFACE. It cannot see an arm whose input is
a BUILT ARTIFACT. A1.5 is exactly that arm — its whole context is a pre-built
graph dumped as static text — and across `a15-floor` -> `weave-offturn` that dump
went from **9,841 chars, `woven=0 transformations=0`** to **~26,000 chars,
`woven=5 transformations=42`**, because `abe386d` moved pathway construction off
the turn. Same `prompt_sha` on both, so the prompt gate passes them, and pooling
the two would average two different arms and call it 24 pairs of one. So the
recorded `static_context_provenance` of each arm under test must agree across
stems too, and it is a REFUSAL and not a warning for the same reason the prompt
check is: a gate you can read past is a gate for a reader who already knows.

THE DIMENSION-GROUP PROBLEM, WHICH `a15-floor` CORRECTED BY HAND
===============================================================
Three of the twelve judged dimensions (`NON_INFERIORITY_DIMENSIONS`: warmth,
actionability, conversational_fit) are the base model's home turf. They are
reported as a bound the framework arm must not fall through, and they are NEVER
part of a superiority headline. `Deltas.composite` blends all twelve, so
`a15-floor` recomputed its own table by hand and every headline it printed
changed — and on `A1.5 vs A1` that matters more than usual, because
`actionability +1.25` is an NI row and the largest mover in the set.

So the primary line here is the STRUCTURAL composite over the judged dimensions
that are not NI, and the NI group is printed under it as a bound with no verdict
word attached. The blended-all-twelve number is not printed at all: it is not the
endpoint of anything, and the only thing it has ever been used for is being
quoted by mistake.

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
exactly the move the pre-registration exists to forbid.

AND THE POSITIVE CASE IS NOT HYPOTHETICAL, WHICH THIS FILE USED TO IMPLY
=======================================================================
Swept over the archive on 2026-09-17: of 37 saved (stem, arm-pair) sets with a
computable ICC, **17 are POSITIVE**, up to +0.697 — r21 is the minority case, not
the rule. So the flat interval is anti-conservative in nearly half of everything
here, and the "if a later run shows a positive ICC" this section used to say was
describing sets that already existed. Two mitigations, both in the printout:

- When ICC > 0 the primary row is the flat interval with the DESIGN EFFECT priced
  in (`_deff_ci`) — standard error inflated by sqrt(deff), df from the effective
  n — and not the replicate-mean row. At the 3 replicates a single round produces,
  the replicate-mean interval carries t(2)=4.303 and resolves nothing whatever the
  data say, so making it primary would report a df problem as a null result.
- Sizing inherits it. `report.py` prints "needs n≈N pairs" from
  `(2.8*sd/effect)**2`, which assumes independence; at deff 1.84 the real figure
  is 1.84x that, and the archive's published n≈55 for `A1.5 vs A1` was computed
  without it (and on the blended composite, see below).

What the sweep did NOT find is a laundered win: applying the correction to all 37
sets changes the verdict on **2**, and both are recorded framework LOSSES that
become unresolved. Nothing published here rests on the uncorrected interval in
the flattering direction, which is the one thing worth checking before believing
a correction discovered by whoever wrote it.
"""
from __future__ import annotations

import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.e2e.models import (NON_INFERIORITY_DIMENSIONS, Arm,  # noqa: E402
                              Comparison, RunRecord)
from tests.e2e.read_prereg import verdict_for  # noqa: E402
from tests.e2e.report import drop_invalid, load_records  # noqa: E402

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


def _deff_ci(values: list[float], deff: float) -> tuple[float, float]:
    """The flat interval with the correlation priced in, not assumed away.

    Same mean — clustering does not bias the mean, only its precision. The
    standard error is inflated by sqrt(design effect) and the t multiplier is
    taken from the EFFECTIVE n, so a set of 24 pairs in 6 replicates at ICC
    +0.28 is read as the ~13 independent pairs it is worth.

    Never narrower than the uncorrected interval: `deff < 1` happens whenever the
    ICC is negative, and letting a negative ICC BUY precision would turn the
    archive's most common case into free resolution. Below 1 this returns the
    plain interval, which is what the ICC <= 0 branch already treats as primary.
    """
    plain = _ci(values)
    if plain is None or deff <= 1:
        return plain if plain is not None else (float("nan"), float("nan"))
    se = st.stdev(values) / math.sqrt(len(values))
    effective = max(2, round(len(values) / deff))
    half = _t95(effective - 1) * se * math.sqrt(deff)
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


def _built_inputs(payload: dict, arms: tuple[str, ...]) -> dict[str, set[str]]:
    """Recorded `static_context_provenance` per arm, for the arms under test.

    Read off the CELLS rather than rebuilt, because the question is what the arm
    was actually handed in that run — and read as a set per arm, because a stem
    whose own cells disagree is already a heterogeneous arm before any pooling.

    Arms with no static context (A1, A2 — they build or lack a graph live) record
    None and are simply absent here. Absent is not a mismatch: there is no built
    artifact to differ.

    The comparison is on the recorded RECIPE (`perspectives=5 woven=5
    transformations=42 decisions=1`) and deliberately not on `static_context_chars`.
    Two builds of the same recipe differ in length by a few percent because the
    text is generated — `weave-offturn` and `feasibility-offturn` are 26,312 and
    25,348 chars of the identical recipe — so gating on the exact size would
    refuse every pool that has ever existed, which is the same as having no gate.
    """
    out: dict[str, set[str]] = defaultdict(set)
    for record in payload.get("runs") or []:
        provenance = record.get("static_context_provenance")
        arm = record.get("arm")
        if provenance and arm in arms:
            out[arm].add(provenance)
    return dict(out)


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
        # Scenario provenance, for the reason `build_provenance` exists one axis
        # over: a pooled estimate that cannot say WHICH SCENARIOS it measured is
        # not an estimate of anything shippable either. Added after guessing
        # wrong about this very pool — the r21+r22 headline looked like it
        # spanned two scenarios (two stems, and the README's known limit is that
        # `cofounder_equity` + `cofounder_ladder_return` carry 95% of all judged
        # cells) and in fact both stems are `cofounder_equity` alone. One
        # command now answers that instead of an inference from the stem names,
        # which is the whole argument for printing provenance rather than
        # remembering it.
        keys = sorted({c.get("scenario_key", "?") for c in payload["comparisons"]})
        print(f"  {'':34} scenarios: {', '.join(keys) or 'NONE'}")
        built = _built_inputs(payload, pair)
        for arm in sorted(built):
            for provenance in sorted(built[arm]):
                print(f"  {'':34} {arm} static context: {provenance}")

    # The second gate, which the prompt check cannot stand in for: an arm whose
    # input is a built artifact can change completely without a prompt byte
    # moving. See the A1.5 case in the module docstring.
    built_by_arm: dict[str, set[str]] = defaultdict(set)
    for payload in payloads.values():
        for arm, provenances in _built_inputs(payload, pair).items():
            built_by_arm[arm] |= provenances
    drifted = sorted(arm for arm, seen in built_by_arm.items() if len(seen) > 1)

    distinct = {s for s in shas.values() if s}
    missing = [stem for stem, s in shas.items() if not s]
    poolable = len(distinct) == 1 and not missing and not drifted

    print()
    if poolable:
        print("  POOLABLE: one prompt_sha across every stem, provenance present.")
    else:
        reason = []
        if missing:
            reason.append(f"provenance ABSENT in {', '.join(missing)}")
        if len(distinct) > 1:
            reason.append(f"{len(distinct)} distinct prompt_sha values")
        if drifted:
            reason.append(
                f"static context DIFFERS across stems for {', '.join(drifted)}"
            )
        print(f"  NOT POOLABLE: {'; '.join(reason)}")
        if not force:
            print()
            print("  REFUSED — pooling across builds launders a build change into")
            print("  extra n. Read the stems separately with read_prereg.py, or")
            print("  pass --force and say in the write-up that it was forced.")
            return 2
        print("  !! FORCED — this number is NOT an ordinary pooled endpoint.")

    # -- the endpoint ---------------------------------------------------------
    rows: list[tuple[str, Comparison]] = []
    dropped_total = 0
    for stem, payload in payloads.items():
        runs = [RunRecord.model_validate(r) for r in payload["runs"]]
        comparisons = [Comparison.model_validate(c) for c in payload["comparisons"]]
        kept, dropped = drop_invalid(comparisons, runs)
        dropped_total += dropped
        for c in kept:
            if (c.arm_a, c.arm_b) != (hi, lo) or not c.scores:
                continue
            rows.append((stem, c))

    def gather(
        dimensions: tuple[str, ...],
    ) -> tuple[list[float], dict[str, list[float]], dict[tuple[str, int], list[float]]]:
        """Cells over ONE dimension group, in all three units.

        Parameterised rather than written twice because the structural composite
        and the NI bound must be the same arithmetic on different columns; two
        copies is how a group ends up silently using a different unit from the
        block it is printed under.
        """
        flat: list[float] = []
        by_scenario: dict[str, list[float]] = defaultdict(list)
        per_replicate: dict[tuple[str, int], list[float]] = defaultdict(list)
        for stem, c in rows:
            deltas = [a - b for d, (a, b) in c.scores.items() if d in dimensions]
            if not deltas:
                continue
            cell = st.fmean(deltas)
            flat.append(cell)
            by_scenario[c.scenario_key].append(cell)
            # Replicate numbers restart per stem, so the key must carry the stem
            # or r21's rep 3 and r22's rep 3 collapse into one cluster.
            per_replicate[(stem, c.replicate)].append(cell)
        return flat, dict(by_scenario), dict(per_replicate)

    judged = tuple(sorted({d for _, c in rows for d in c.scores}))
    structural = tuple(d for d in judged if d not in NON_INFERIORITY_DIMENSIONS)
    ni_judged = tuple(d for d in judged if d in NON_INFERIORITY_DIMENSIONS)
    flat, by_scenario, per_replicate = gather(structural)

    print()
    print("=" * 74)
    print(f"ENDPOINT — {hi.value} vs {lo.value} — STRUCTURAL composite")
    print("=" * 74)
    print(
        f"  {len(judged)} judged dimension(s): {len(structural)} structural, "
        f"{len(ni_judged)} non-inferiority"
    )
    if ni_judged:
        # Named, not just counted. `a15-floor` published a headline that had
        # `actionability` inside it, and the reader could not have known.
        print(f"  held OUT of this composite: {', '.join(ni_judged)}  (bound below)")
    if len(flat) < 2:
        print(f"  only {len(flat)} judged pair(s) on the structural group — no interval")
        return 1
    print(f"  invalid cells dropped: {dropped_total}")

    mean = st.fmean(flat)
    ci = _ci(flat)
    print(
        f"  FLAT (pre-registered unit)     {mean:+.3f}  sd {st.stdev(flat):.3f}  "
        f"95%CI [{ci[0]:+.3f},{ci[1]:+.3f}]  n={len(flat)}"
    )
    print(f"          -> {verdict_for(ci)}")

    if len(by_scenario) > 1:
        # Heterogeneity, printed as a DIAGNOSTIC and never as the endpoint: the
        # headline stays the flat pooled number that was pre-registered. What
        # this row is for is the case pooling cannot survive — two scenarios
        # pulling in opposite directions average to a confident nothing, which
        # is the reading `read_prereg` now refuses to print alone for a stem
        # holding a control. Switching to whichever slice reads best is the
        # forbidden move; seeing that the slices agree is the point.
        print()
        print("  per scenario (diagnostic — the pooled line above stays primary):")
        for scenario in sorted(by_scenario):
            cells = by_scenario[scenario]
            s_ci = _ci(cells) if len(cells) > 1 else None
            ci_s = "n/a" if s_ci is None else f"[{s_ci[0]:+.3f},{s_ci[1]:+.3f}]"
            print(
                f"    {scenario:26} {st.fmean(cells):+.3f}  95%CI {ci_s}  n={len(cells)}"
            )
        signs = {st.fmean(v) > 0 for v in by_scenario.values()}
        if len(signs) > 1:
            print("    !! SCENARIOS DISAGREE IN SIGN — the pooled mean is an average")
            print("       of opposing effects; say so in the write-up.")

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
                "  treats correlated pairs as independent."
            )
            # And here is the correction to READ, rather than a demand to fall
            # back on the replicate means. At 3 replicates the replicate-level
            # interval carries t(2)=4.303 and resolves nothing whatever the data
            # say, so offering only that row means every positive-ICC set reads
            # "unresolved" for a reason that is about df and not about the arms.
            # The design effect keeps every pair and prices the correlation:
            # inflate the standard error by sqrt(deff) and take df from the
            # EFFECTIVE n. It lands between the two rows above and it is the one
            # the write-up should quote.
            corrected = _deff_ci(flat, deff)
            print(
                f"  FLAT, deff-corrected (primary) {st.fmean(flat):+.3f}  "
                f"95%CI [{corrected[0]:+.3f},{corrected[1]:+.3f}]  "
                f"effective n={len(flat) / deff:.1f} of {len(flat)}"
            )
            print(f"          -> {verdict_for(corrected)}")
            print(
                "  Sizing must carry it too: the pairs a round needs are the\n"
                f"  independence-assuming figure times {deff:.2f}."
            )

    if ni_judged:
        # The reconciliation an older write-up needs, and the guard against this
        # correction being read as a re-headline. Published rounds quote the
        # blended-twelve composite, because that is what `Deltas.composite`
        # computed when they were written; on r21+r22 the blend reads
        # +0.325 [-0.003,+0.653] UNRESOLVED and the structural endpoint reads
        # +0.372 [+0.008,+0.737], which is a WIN by eight thousandths. Switching
        # to whichever reading excludes zero, AFTER seeing that it does, is the
        # move pre-registration exists to forbid — the more so when the switch is
        # in the flattering direction and the person switching wrote the switch.
        # So a disagreement is printed as something to argue about, never as a
        # corrected verdict.
        blended, _, _ = gather(judged)
        blended_ci = _ci(blended) if len(blended) > 1 else None
        if verdict_for(blended_ci) != verdict_for(ci):
            ci_b = (
                "n/a"
                if blended_ci is None
                else f"[{blended_ci[0]:+.3f},{blended_ci[1]:+.3f}]"
            )
            print()
            print("  !! THIS STEM READS DIFFERENTLY UNDER THE OLDER BLENDED COMPOSITE:")
            print(
                f"     all {len(judged)} dimensions blended: {st.fmean(blended):+.3f} "
                f"95%CI {ci_b}"
            )
            print(f"     -> {verdict_for(blended_ci)}")
            print("     A published write-up of this stem quotes THAT number. The")
            print("     structural line above is the better endpoint and it is NOT")
            print("     licence to re-headline a finished round: say both, and say")
            print("     which one was pre-registered.")

        ni_flat, _, _ = gather(ni_judged)
        ni_ci = _ci(ni_flat) if len(ni_flat) > 1 else None
        print()
        print("=" * 74)
        print(f"NON-INFERIORITY BOUND — {'/'.join(ni_judged)} — NOT the endpoint")
        print("=" * 74)
        ci_s = "n/a" if ni_ci is None else f"[{ni_ci[0]:+.3f},{ni_ci[1]:+.3f}]"
        print(
            f"  FLAT                           {st.fmean(ni_flat):+.3f}  "
            f"95%CI {ci_s}  n={len(ni_flat)}"
        )
        # No verdict word here, deliberately. On these three dimensions the
        # question is whether the arm FALLS THROUGH a floor, and `verdict_for`
        # answers a different one ("does the interval exclude zero"). Printing
        # FRAMEWORK WINS off an NI gain is the blend error with an extra step.
        print("  Read as a floor: does the lower end fall through the margin the")
        print("  round pre-registered? A gain here is not a win and does not")
        print("  belong in a headline — it is the base model's own home turf.")
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
