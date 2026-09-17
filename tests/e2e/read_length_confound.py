"""Is a judged win a win, or is it the longer transcript? Read off the archive.

    poetry run python tests/e2e/read_length_confound.py weave-offturn \\
        feasibility-offturn A1.5 A1
    poetry run python tests/e2e/read_length_confound.py --sweep

Every delta in this archive comes from a judge shown two transcripts at once. If
that judge rewards length, then any arm that happens to write more collects
structural points it did not earn, and no amount of replication removes it — it
is bias, not variance, exactly like the position bias `judge.py::_x_is_a` exists
to cancel. Position was cancelled by DESIGN. Length never was: nothing in the
bench equalises how much an arm says, and `weave-offturn`'s own limit 2 has been
carrying "a length-matched re-run is the outstanding fix" since it was written.

This reads the confound for free, off transcripts already paid for. For each
judged pair it computes the ASSISTANT-WORD GAP (hi arm minus lo arm, over the
one session that comparison judged) and regresses the structural composite delta
on it. Three numbers come out: the slope (what a thousand extra words is worth
in rubric steps), the intercept at gap zero (the length-matched estimate), and
the split between the pairs where the hi arm was longer and the ones where it
was not.

WHAT IT FOUND ON THE `A1.5 vs A1` FLOOR QUESTION (2026-09-17, the 24 poolable
pairs `read_pooled.py` admits):

  * slope **+3.27 rubric steps per 1,000 words**, CI [+1.93, +4.61], t=+5.02,
    r=+0.73 — length explains 53% of the variance in the endpoint
  * raw endpoint **+0.514**; at gap zero **+0.095**, CI [-0.21, +0.40]
  * the 6 pairs where A1 was the longer transcript read **-0.98** for A1.5; the
    18 where A1.5 was longer read **+1.01**. Median split: **-0.29** below the
    median gap, **+1.32** above it
  * mean gap +128 words, which at the archive-wide slope is +0.15 of the +0.514

So the floor question's positive mean and the verbosity gap are the same
observation twice, and NO adjustment rescues it: at the set's own slope the
estimate is +0.095 [-0.21, +0.40], at the archive-wide slope +0.368 [-0.01,
+0.74], and every interval spans zero. The honest summary is that A1.5-vs-A1 is
unresolved AND its point estimate is not separable from how much more A1.5 said.

AND THE SLOPE IS NOT A PROPERTY OF THIS PAIR — IT IS EVERYWHERE (`--sweep`):
**29 of 36** (stem, arm-pair) sets in the archive have a POSITIVE length slope
(sign test p=0.0003), median +0.97 per 1,000 words, |t|>2 in 11 of them; pooled
within-set over all **530 pairs in 36 sets: +1.14, CI [+0.88, +1.40]**, t=+8.53.
Within a set, whichever transcript was longer scored better — including sets
whose mean delta is NEGATIVE, so this is not "the better arm writes more".

THE DEAD-CELL DROP IS LOAD-BEARING AND IT IS NOT INHERITED CAUTION. An arm that
never ran leaves an empty transcript, which is at once the shortest possible and
the worst-scoring possible: a single point at the extreme of BOTH axes, which is
how you manufacture a slope. Applying `invalid_cells` the way `drop_invalid` does
took `r22-strong-pooled-rejudge` from 20 pairs at +1.82 (t=+3.48) to 16 at +1.02
(t=+1.00) — four dead rows were most of that set's slope — and the archive figure
from +1.19 to +1.14. Any future regression against a transcript PROPERTY inherits
this hazard, whichever property it is.

SETTLED BY THE PLACEBO — DO NOT ADOPT THE ADJUSTED FIGURES. A slope is a
correlation, and length was either a CONFOUNDER (the judge pays for words) or a
MEDIATOR (the graph makes the arm say more useful things, and length is how the
gain arrives). Adjusting for a confounder removes bias; adjusting for a mediator
removes the effect, and the archive could not tell them apart because it holds no
comparison of an arm against ITSELF.

`probe_same_arm_placebo.py` built that comparison and it came out REFUTED. The two
`decide` transcripts of one (arm, tier, scenario, replicate) are the same script
sampled twice — same prompt, same model, same simulator, expected true delta zero,
length varying by generation noise alone. Judged on this very instrument, 32
pre-registered same-arm pairs (gap sd 766 words, power 1.00 at the figure below,
0.82 at half of it) give a slope of **-0.13 per 1,000 words, CI [-0.57, +0.30]**,
against the +1.14 pooled here and the +3.27 on the marquee set. The interval
excludes both — and excludes even the +0.57 registered as the consequential
threshold — while containing zero. With the manipulation removed, **words buy
nothing.** Mean composite delta came out -0.000, so the two branches are
exchangeable as the design assumes.

So the cross-arm slope travels with the ARM, not with the judge's appetite for
words: the RAW figures are the estimate, and the adjusted ones are neither the
honest read nor a bound on bias — they are an over-correction that would delete
real effect. What the per-dimension vectors add: the ORDERING of which dimensions
respond to length does reproduce (r=+0.79 over 12 dimensions, +0.76 to +0.83
leave-one-out, `conversational_fit` negative in both), but only at
`placebo = 0.39 x cross-arm - 0.51` — the shape is a judge property, the LEVEL is
not, and a near-uniform offset across all 12 dimensions is what an arm effect
travelling with length looks like rather than a judge habit.

What the placebo still cannot do, and it belongs beside the sentence above: it
holds the ARM, not the CONTENT. A within-arm coupling where a run with more to say
both says more and deserves more would show up here as a positive slope — it did
not, which is why this reads as a refutation, but a content-identical trim is out
of reach for a conversation (dropping middle turns breaks it; trimming the tail
tests the ending) and provenance-identical is what was bought.

WHICH DIRECTION IT CUTS IS NOT ALWAYS THE FLATTERING ONE, AND THAT IS THE
STRONGEST REASON TO TRUST THE INSTRUMENT. A2 is the SHORTER arm in every marquee
set: -229 and -230 words against A1.7 in `r21`/`r22`, -120 and -84 in the two
`ladder-return` stems. So adjusting there moves A2's numbers UP (r21 +0.372 raw
against +0.521 adjusted, r22 +0.153 against +0.388), which is the direction a
reader should distrust in a tool written by whoever quotes it. Nothing here
adopts those figures: the sweep prints them next to the raw ones and stops.

WHY THE BRANCH HAS TO BE RECOVERED, AND WHY ORDER IS ALLOWED TO DO IT.
`Comparison` records no `branch` (see its docstring — `session_label` was added
for exactly this class of complaint and `branch` was not), but the length gap
needs the specific pair of transcripts that comparison saw, and the two `decide`
transcripts of one (arm, replicate) are DIFFERENT runs: A1.5 rep 1 is 1,781
words in the `wobble_a` branch and 2,033 in `wobble_b`, against A1's 1,753 and
1,650, so the gap is +28 in one and +383 in the other. Assigning them the wrong
way round scrambles the covariate on the very rows that carry the signal.

`runner.judge_pairs` iterates a deterministic list (`self.runs`, then that
record's sessions), so file order recovers the branch — and `_align` REPLAYS that
loop rather than assuming a pattern, then refuses unless every recorded field of
every comparison matches the replay. The check that makes this more than a hope:
half the rows name their own branch, because a wobble session's label IS the
branch. If the replay's `wobble_a`/`wobble_b` rows line up with the recorded
labels, the interleaving is confirmed and the `decide` rows sitting between them
are pinned by construction. A stem that fails any of this is DROPPED with a
reason, never guessed at.
"""

from __future__ import annotations

import glob
import math
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.models import NON_INFERIORITY_DIMENSIONS, RunRecord  # noqa: E402
from e2e.read_pooled import _ci, _deff_ci, _icc, _t95  # noqa: E402
from e2e.report import invalid_cells, load_records  # noqa: E402

RESULTS = E2E_DIR / "results"

#: Rubric steps of structural composite per assistant word, pooled WITHIN set
#: over the whole archive. Measured 2026-09-17: 530 pairs in 36 (stem, arm-pair)
#: sets, +1.137 per 1,000 words, CI [+0.876, +1.398], t=+8.53. Kept as a constant
#: so a single set's own slope — estimated on a dozen points and therefore free
#: to be steep by luck — can be read against the archive's, and printed by
#: `--sweep` so drift shows up instead of hiding behind this number.
ARCHIVE_SLOPE_PER_WORD = 0.001137


def assistant_words(session: dict) -> int:
    """Words the ARM wrote in one session. The simulator's turns are not the
    arm's verbosity, and the judge is shown the whole exchange either way, so
    counting both sides would move with the simulator instead of the arm."""
    return sum(len((t.get("assistant") or "").split()) for t in session["turns"])


def _cell_key(record: dict) -> tuple:
    return (
        record["arm"],
        record["tier"],
        record["scenario_key"],
        record["replicate"],
        record.get("branch") or "-",
    )


def _align(payload: dict, pair: tuple[str, str]) -> tuple[list[dict], str]:
    """(rows, "") for one arm pair, or ([], reason) if the replay does not hold.

    Replays `runner.judge_pairs`' loop over this payload's own run list and zips
    the result against the comparisons in file order. Refusal beats a guess here:
    a mis-assigned branch does not look wrong anywhere downstream, it just moves
    the covariate onto the wrong row.
    """
    runs = payload.get("runs") or []
    index = {_cell_key(r): r for r in runs}
    replay: list[tuple[dict, dict, dict]] = []
    for record in runs:
        if record["arm"] != pair[0] or record.get("error"):
            continue
        other = index.get((pair[1],) + _cell_key(record)[1:])
        if other is None or other.get("error"):
            continue
        for session in record["sessions"]:
            match = [s for s in other["sessions"] if s["label"] == session["label"]]
            if match:
                replay.append((record, session, match[0]))

    comparisons = [
        c
        for c in payload.get("comparisons") or []
        if (c["arm_a"], c["arm_b"]) == pair
    ]
    if not comparisons:
        return [], "no comparisons for this pair"
    if len(replay) != len(comparisons):
        return [], f"replay is {len(replay)} sessions against {len(comparisons)} comparisons"
    # A stem old enough to predate `session_label` cannot be validated at all —
    # and that is a different refusal from an order that failed to replay. Saying
    # "session_label disagrees" about a field the run never wrote reads as a
    # broken instrument instead of an archive too old for one.
    if not any(c.get("session_label") for c in comparisons):
        return [], "predates `session_label` — nothing pins the replay"

    # A DEAD CELL IS THE ONE DATA POINT THIS INSTRUMENT MUST NOT SEE, and the
    # reason is specific to it rather than inherited from `drop_invalid`: an arm
    # that never ran contributes an empty transcript, which is simultaneously the
    # shortest possible and the worst possible: one point at the far end of both
    # axes, manufacturing exactly the slope this file is trying to measure.
    # Keyed loosely (arm, tier, replicate) like `drop_invalid`, since a run
    # invalid in one branch is invalid for every comparison of that cell.
    try:
        bad = {key[:3] for key in invalid_cells(
            [RunRecord.model_validate(r) for r in runs]
        )}
    except Exception as exc:  # a stem too old to parse is not readable here
        return [], f"run records do not validate ({type(exc).__name__})"

    rows: list[dict] = []
    for comparison, (record, mine, theirs) in zip(comparisons, replay):
        # Every coordinate the comparison DID record must agree with the replay.
        for field in ("tier", "scenario_key", "replicate"):
            if comparison.get(field) != record.get(field):
                return [], f"{field} disagrees at replay position {len(rows)}"
        if comparison.get("session_label", "") != mine["label"]:
            return [], f"session_label disagrees at replay position {len(rows)}"
        # And the half of the rows that name their own branch must agree too,
        # which is what pins the `decide` rows between them.
        label = mine["label"]
        branch = record.get("branch")
        if label.startswith("wobble") and label != branch:
            return [], f"branch {branch!r} does not match session {label!r}"
        if comparison.get("error") or not comparison.get("scores"):
            continue
        if (
            (pair[0], record["tier"], record["replicate"]) in bad
            or (pair[1], record["tier"], record["replicate"]) in bad
        ):
            continue
        deltas = [
            a - b
            for dimension, (a, b) in comparison["scores"].items()
            if dimension not in NON_INFERIORITY_DIMENSIONS
        ]
        if not deltas:
            continue
        rows.append(
            {
                "replicate": record["replicate"],
                "branch": branch,
                "session": label,
                "words_hi": assistant_words(mine),
                "words_lo": assistant_words(theirs),
                "gap": assistant_words(mine) - assistant_words(theirs),
                "delta": st.fmean(deltas),
            }
        )
    return rows, ""


def _regress(rows: list[dict]) -> dict | None:
    """OLS of the structural composite on the word gap, with SEs. None if the
    gap does not vary enough to fit anything."""
    xs = [r["gap"] for r in rows]
    ys = [r["delta"] for r in rows]
    if len(rows) < 4 or len(set(xs)) < 3:
        return None
    mx, my = st.fmean(xs), st.fmean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    syy = sum((y - my) ** 2 for y in ys)
    slope = sxy / sxx
    intercept = my - slope * mx
    residuals = [y - (intercept + slope * x) for x, y in zip(xs, ys)]
    s2 = sum(r * r for r in residuals) / (len(rows) - 2)
    return {
        "n": len(rows),
        "slope": slope,
        "se_slope": math.sqrt(s2 / sxx),
        "intercept": intercept,
        "se_intercept": math.sqrt(s2 * (1 / len(rows) + mx * mx / sxx)),
        "r": sxy / math.sqrt(sxx * syy) if syy else float("nan"),
        "mean_gap": mx,
        "mean_delta": my,
        "residuals": residuals,
        "df": len(rows) - 2,
    }


def _adjusted(rows: list[dict], slope: float) -> tuple[float, tuple[float, float], tuple[float, float] | None, float]:
    """Composite with `slope` x gap subtracted from every pair: mean, flat CI,
    deff-corrected CI (None when the residual ICC does not call for one), ICC.

    Subtracting a FIXED slope rather than fitting one is what lets the set be read
    against the archive's slope, and it keeps the replicate clustering visible:
    `read_pooled.py`'s rule applies to this column exactly as it does to the raw
    one, and the ICC of the adjusted values is itself informative — if length was
    what made pairs within a replicate alike, adjusting for it takes the
    correlation away.
    """
    values = [r["delta"] - slope * r["gap"] for r in rows]
    clusters: dict[object, list[float]] = defaultdict(list)
    for row, value in zip(rows, values):
        clusters[(row["replicate"], row.get("stem"))].append(value)
    icc = _icc(clusters)
    flat = _ci(values) or (float("nan"), float("nan"))
    corrected = None
    if icc and icc[1] > 1:
        corrected = _deff_ci(values, icc[1])
    return st.fmean(values), flat, corrected, (icc[0] if icc else float("nan"))


def _pairs(n: int) -> str:
    """"1 pair" / "4 pairs" — the singular is reachable in both refusal messages
    below, so this branches rather than hedging with "(s)"."""
    return f"{n} pair" if n == 1 else f"{n} pairs"


def _sign_test(positive: int, total: int) -> float:
    """Two-sided exact binomial at p=0.5. Hand-rolled: scipy is not installed."""
    probabilities = [math.comb(total, i) * 0.5 ** total for i in range(total + 1)]
    observed = probabilities[positive]
    return sum(p for p in probabilities if p <= observed + 1e-15)


def _sets(pair: tuple[str, str] | None = None):
    """Every (stem, arm pair) in `results/` whose judging order replays cleanly."""
    for path in sorted(glob.glob(str(RESULTS / "*.json"))):
        if path.endswith("-runs.json"):
            continue
        try:
            payload = load_records(Path(path))
        except Exception:
            continue
        pairs = sorted(
            {(c["arm_a"], c["arm_b"]) for c in payload.get("comparisons") or []}
        )
        for candidate in pairs:
            if pair and candidate != pair:
                continue
            rows, reason = _align(payload, candidate)
            stem = Path(path).stem
            for row in rows:
                row["stem"] = stem
            yield stem, candidate, rows, reason


def read(stems: list[str], pair: tuple[str, str]) -> int:
    print("=" * 78)
    print(f"LENGTH CONFOUND — {' + '.join(stems)} — {pair[0]} vs {pair[1]}")
    print("=" * 78)

    rows: list[dict] = []
    for stem in stems:
        path = RESULTS / f"{stem}.json"
        if not path.exists():
            print(f"NO SUCH STEM: {path}")
            return 1
        stem_rows, reason = _align(load_records(path), pair)
        if reason:
            print(f"  REFUSED {stem}: {reason}")
            print("  The branch of a `decide` comparison is recovered from judging")
            print("  order, so a stem whose order does not replay is not readable")
            print("  here at all. Do not fall back on a pattern.")
            return 2
        for row in stem_rows:
            row["stem"] = stem
        rows.extend(stem_rows)
        print(f"  {stem:34} {len(stem_rows)} pairs, branch recovered and confirmed")

    print()
    print(f"  {'stem':22} {'rep':>3} {'branch':9} {'session':9} "
          f"{pair[0]:>7} {pair[1]:>7} {'gap':>6} {'delta':>7}")
    for row in rows:
        print(
            f"  {row['stem'][:22]:22} {row['replicate']:3d} "
            f"{(row['branch'] or '-'):9} {row['session']:9} "
            f"{row['words_hi']:7d} {row['words_lo']:7d} "
            f"{row['gap']:+6d} {row['delta']:+7.3f}"
        )

    fit = _regress(rows)
    if fit is None:
        print("\n  NOT FITTABLE: the word gap barely varies over these pairs.")
        return 0

    t = _t95(fit["df"])
    print()
    print(f"  pairs {fit['n']}   mean gap {fit['mean_gap']:+.1f} words   "
          f"raw endpoint {fit['mean_delta']:+.3f}")
    print(
        f"  SLOPE {fit['slope'] * 1000:+.3f} per 1,000 words   "
        f"CI [{(fit['slope'] - t * fit['se_slope']) * 1000:+.3f},"
        f"{(fit['slope'] + t * fit['se_slope']) * 1000:+.3f}]   "
        f"t={fit['slope'] / fit['se_slope']:+.2f}   "
        f"r={fit['r']:+.2f}   r2={fit['r'] ** 2:.2f}"
    )
    print(f"  archive-wide slope for comparison: "
          f"{ARCHIVE_SLOPE_PER_WORD * 1000:+.3f} per 1,000 words (--sweep)")

    print()
    print("  LENGTH-MATCHED READS — each subtracts a slope, none is the endpoint")
    for name, slope in (
        ("this set's own slope", fit["slope"]),
        ("archive-wide slope", ARCHIVE_SLOPE_PER_WORD),
    ):
        mean, flat, corrected, icc = _adjusted(rows, slope)
        line = (f"    {name:22} {mean:+.3f}  flat [{flat[0]:+.3f},{flat[1]:+.3f}]"
                f"  residual ICC {icc:+.2f}")
        if corrected:
            line += f"  deff-corrected [{corrected[0]:+.3f},{corrected[1]:+.3f}]"
        else:
            line += "  (deff<=1, flat stands)"
        print(line)
    print("    A range, not a correction: the own-slope figure is fitted on these")
    print("    pairs and free to be steep by luck; the archive one is borrowed from")
    print("    sets with different arms. Quote the WIDTH of the range.")

    # The two splits are the part a reader can check by eye against the table.
    median_gap = st.median(r["gap"] for r in rows)
    below = [r["delta"] for r in rows if r["gap"] <= median_gap]
    above = [r["delta"] for r in rows if r["gap"] > median_gap]
    shorter = [r["delta"] for r in rows if r["gap"] < 0]
    longer = [r["delta"] for r in rows if r["gap"] >= 0]
    print()
    print(f"  median-gap split ({median_gap:+.0f} words): "
          f"below n={len(below)} mean {st.fmean(below):+.3f}   "
          f"above n={len(above)} mean {st.fmean(above):+.3f}")
    if shorter and longer:
        print(f"  {pair[1]} was the longer transcript in {len(shorter)} pairs, "
              f"mean {st.fmean(shorter):+.3f}   "
              f"{pair[0]} longer in {len(longer)}, mean {st.fmean(longer):+.3f}")

    print()
    print("  DO NOT ADOPT THE ADJUSTED FIGURE. Whether the judge PAYS for words")
    print("  (a confound) or the arm SAYS more because it has more to say (a")
    print("  mediator) is not visible in any cross-arm slope — and")
    print("  `probe_same_arm_placebo.py` settled it on 32 same-arm pairs, where the")
    print("  manipulation is absent and only length moves: slope -0.13 per 1,000")
    print("  words, CI [-0.57, +0.30], excluding both the +1.14 pooled here and the")
    print("  +3.27 marquee slope. Words buy nothing once the arm is held, so the")
    print("  RAW delta is the estimate and adjusting would delete real effect.")
    return 0


def _print_refusals(refused: list[tuple[str, tuple[str, str], str]]) -> None:
    if not refused:
        return
    print()
    print("  not readable here (order does not replay, or too few pairs):")
    for stem, pair, reason in refused:
        print(f"    {stem[:32]:32} {pair[0] + ' v ' + pair[1]:13} {reason}")


def sweep() -> int:
    print("=" * 78)
    print("LENGTH SLOPE ACROSS THE WHOLE ARCHIVE — is it the judge or the arm?")
    print("=" * 78)
    print(f"  {'stem':32} {'pair':13} {'n':>3} {'per 1kw':>8} {'t':>6} "
          f"{'raw':>7} {'adj@0':>7} {'gap':>7} {'r':>6}")
    fits: list[tuple[str, tuple[str, str], dict]] = []
    refused: list[tuple[str, tuple[str, str], str]] = []
    pooled: list[tuple[float, float]] = []
    for stem, pair, rows, reason in _sets():
        if reason:
            refused.append((stem, pair, reason))
            continue
        fit = _regress(rows)
        if fit is None:
            refused.append((stem, pair, f"{_pairs(len(rows))}, or a gap that barely varies"))
            continue
        if fit["n"] < 6:
            refused.append((stem, pair, f"only {_pairs(fit['n'])} scorable"))
            continue
        fits.append((stem, pair, fit))
        print(
            f"  {stem[:32]:32} {pair[0] + ' v ' + pair[1]:13} {fit['n']:3d} "
            f"{fit['slope'] * 1000:+8.3f} {fit['slope'] / fit['se_slope']:+6.2f} "
            f"{fit['mean_delta']:+7.3f} {fit['intercept']:+7.3f} "
            f"{fit['mean_gap']:+7.1f} {fit['r']:+6.2f}"
        )
        # Within-set centering is the whole design: it asks whether the LONGER
        # transcript of a pair scored better, with each set's own mean removed,
        # so a set where one arm is both better and longer contributes nothing on
        # that account.
        for row in rows:
            pooled.append((row["gap"] - fit["mean_gap"],
                           row["delta"] - fit["mean_delta"]))

    if not fits:
        # Reachable, and not only in a test: every stem older than
        # `session_label` refuses, so a `results/` holding only those has nothing
        # to pool. Say so rather than raising out of `statistics.median`.
        print()
        print("  NO SET IN THIS ARCHIVE REPLAYS — nothing to pool.")
        _print_refusals(refused)
        return 0

    positive = sum(1 for _, _, f in fits if f["slope"] > 0)
    significant = sum(1 for _, _, f in fits if abs(f["slope"] / f["se_slope"]) > 2)
    print()
    print(f"  sets {len(fits)}   positive slope {positive}   |t|>2 {significant}   "
          f"sign test p={_sign_test(positive, len(fits)):.4f}")
    print(f"  median slope {st.median(f['slope'] for _, _, f in fits) * 1000:+.3f} "
          f"per 1,000 words")

    sxx = sum(x * x for x, _ in pooled)
    sxy = sum(x * y for x, y in pooled)
    slope = sxy / sxx
    residual = sum((y - slope * x) ** 2 for x, y in pooled)
    df = len(pooled) - len(fits) - 1
    se = math.sqrt(residual / df / sxx)
    t = _t95(df)
    print(f"  POOLED WITHIN-SET  {len(pooled)} pairs in {len(fits)} sets: "
          f"{slope * 1000:+.3f} per 1,000 words   "
          f"CI [{(slope - t * se) * 1000:+.3f},{(slope + t * se) * 1000:+.3f}]   "
          f"t={slope / se:+.2f}")
    print(f"  module constant ARCHIVE_SLOPE_PER_WORD is "
          f"{ARCHIVE_SLOPE_PER_WORD * 1000:+.3f} — update it if this has moved.")

    _print_refusals(refused)
    print()
    print("  The `adj@0` column is NOT a re-headline of any of these rounds, and")
    print("  after the placebo it is not a bound on bias either: 32 same-arm pairs")
    print("  put the manipulation-free slope at -0.13 [-0.57,+0.30] per 1,000 words")
    print("  (`probe_same_arm_placebo.py`), so this slope travels with the ARM and")
    print("  subtracting it deletes real effect. It is still printed because the")
    print("  direction is informative: A2 is the SHORTER arm in every marquee set,")
    print("  so adjustment moves its numbers UP, and a tool that hid that would be")
    print("  hiding the flattering direction.")
    return 0


def main(argv: list[str]) -> int:
    if "--sweep" in argv:
        return sweep()
    if len(argv) < 3:
        print(__doc__)
        return 1
    return read(argv[:-2], (argv[-2], argv[-1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
