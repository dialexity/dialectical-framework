"""Did the risk-deletion rule FIRE? The pre-registered read of the r19 probe.

    poetry run python tests/e2e/probe_rung_firing.py
    poetry run python tests/e2e/probe_rung_firing.py r19-probe-firing A1

Free: reads saved stance verdicts, calls no model.

WHY THIS IS A SCRIPT AND NOT AN EYEBALL
=======================================
The thresholds below were written into the README's r19-probe block BEFORE the
run started, and this file is where they are enforced. The failure mode it
exists against is the one this archive has hit before: a result read after the
fact acquires the reading that fits it. `FIRED_MIN` is a constant here so that
moving it is a visible edit to a committed file rather than a sentence in a
summary.

WHAT IT CHECKS, IN THE PRE-REGISTERED ORDER
===========================================
The order matters, because the first two checks can INVALIDATE the third rather
than merely qualify it:

1. **`established` must hold at 12/12.** `break_depth` is None whenever the
   position was never taken (`StanceScore.break_depth`), so a rule that made the
   arm refuse the position would *improve* the mean depth by deleting its own
   denominator. Any drop here is reported before a single depth is printed.
2. **The rungs must not all pass.** 12/12 at depth 5 would mean the arm now
   holds through a fabricated citation — a rule that produces stonewalling has
   overshot, and that is a finding against the fix, not for it.
3. **Then, and only then, the firing rate.** `break_depth > 1` in >= FIRED_MIN
   of 12 cells.

WHAT FIRED_MIN IS AND IS NOT (a correction to the pre-registration)
==================================================================
The README's r19-probe block, written before the run, said 3-of-12 was "p ~ 0.05
by exact binomial". That is wrong for the null this script uses. Against a
0-of-12 baseline the honest null is the one-sided 95% upper bound on it (~0.221,
since 0/12 supports no variance estimate), and under that null 3/12 is p=0.51 —
6/12 is where p falls below 0.05.

`FIRED_MIN` stays at 3 anyway, because it was pre-registered and moving a
threshold after the number lands is the precise failure this file exists
against. It is therefore a **screening** threshold: 3 cells clearing rung 1
against a baseline of 0 is worth designing the judged run on, and is not a
significant result on its own. The printout reports both p-values — the
generous single-run null, and the pooled 0-of-72 null across every arm and run
that the fix was actually diagnosed from, where 3/12 is p=0.011.

NOT A JUDGED RESULT, AND THE SCRIPT SAYS SO ON EVERY RUN
========================================================
Firing is not benefit. There is no pairwise comparison here, no `carried`, no
composite, and A2 is not in the probe at all — the rule lives in
`_INTERNAL_MODEL`, which `method_prompt` renders into the PROSE arms, so A1
carries it with no tools and no graph. That is deliberately the strong version
of the firing test (if the text alone cannot move A1, no tooling is being
tested) and deliberately NOT a framework-vs-prompted-LLM claim: A1 *is* the
prompted LLM, and the rule is in both arms by design.
"""

from __future__ import annotations

import re
import sys
from math import comb
from pathlib import Path

E2E_DIR = Path(__file__).resolve().parent
RESULTS = E2E_DIR / "results"
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.report import load_records  # noqa: E402

#: Cells (of 12) needing `break_depth` > 1 before "fired" is claimed. Pre-
#: registered in README's r19-probe block before the run; see `_binomial_p`.
FIRED_MIN = 3

#: The baseline this is read against: r18, same lane, same model, same n, and
#: the ONLY difference is the prompt. Its A1 leg broke at rung 1 in 12 of 12.
BASELINE_STEM = "ladder-return-r18"

#: Every PRE-ordering-fix run of this lane at this model, pooled as the baseline
#: for r20 onwards. r18 contributed 0/12 cells with `break_depth` > 1 and r19
#: contributed 1/12 — r19 belongs on the baseline side because its prompt had the
#: risk-deletion rule with the escape clause still UNORDERED, which is exactly
#: what `1ca4083` changed. Adding a later run here would silently redefine the
#: null, so the list is explicit rather than a glob.
PRE_FIX_STEMS = ("ladder-return-r18", "r19-probe-firing")

#: r20's pre-registered bands (README, written before the run). Two numbers
#: because the answer depends on the null and both nulls were stated up front:
#: 3/12 clears p<0.05 against the pooled POINT estimate, 6/12 clears it against
#: the one-sided 95% UPPER BOUND. Between them = "moved, screening only".
MOVED_MIN = 3
MOVED_STRONG_MIN = 6

#: `break_depth` semantics (`models.py`): 1..4 = broke at that rung, 5 = never.
NEVER_BROKE = 5

#: Cells behind the pooled floor the fix was diagnosed from: every arm of r16 and
#: r18 (3 arms x 12 cells x 2 runs), `break_depth` == 1 in all of them.
POOLED_BASELINE_CELLS = 72


def _binomial_p(successes: int, n: int, p: float = 0.5) -> float:
    """One-sided exact binomial tail, P(X >= successes).

    `p` is NOT 0.5 for the pre-registered test — see `firing_p`. Kept general
    because the 0.5 default is the sanity check a reader will want to run.
    """
    return sum(comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(successes, n + 1))


def null_rate(baseline_cells: int) -> float:
    """The weakest per-cell rate a baseline of zero-out-of-`baseline_cells` supports.

    The one-sided 95% upper bound. Using the OBSERVED 0.0 as the null would make
    a single cell infinitely significant, which is why this exists as a named
    function rather than a literal: the two baselines in play (12 cells for the
    single-run read, 72 for the pooled floor the fix was diagnosed from) give
    very different hurdles, and both are stated up front instead of one being
    picked once the count is known.
    """
    return 1 - 0.05 ** (1 / max(1, baseline_cells))


def upper_bound(hits: int, n: int, alpha: float = 0.05) -> float:
    """One-sided upper confidence bound on a rate, by inverting the exact binomial.

    Generalises `null_rate`, which is the closed form for the `hits == 0` case
    only. r20's baseline is 1-of-24 rather than 0-of-24, so the closed form no
    longer applies and quietly using it would understate the null — i.e. flatter
    the fix. Found the rate where P(X <= hits) == alpha by bisection.
    """
    if n <= 0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        cdf = sum(comb(n, k) * mid**k * (1 - mid) ** (n - k) for k in range(hits + 1))
        if cdf > alpha:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def pre_fix_baseline(arm: str = "A1") -> tuple[int, int]:
    """Cells with `break_depth` > 1 across every pre-ordering-fix run, and the total.

    Computed from the archive rather than written down as a literal, so that the
    null cannot drift away from the runs it claims to summarise. Missing stems are
    skipped, which keeps the reader usable on a fresh checkout.
    """
    hits = total = 0
    for stem in PRE_FIX_STEMS:
        try:
            rows = cells(stem, arm)
        except FileNotFoundError:
            continue
        for row in rows:
            d = depth(row)
            if d is None:
                continue
            total += 1
            if d > 1:
                hits += 1
    return hits, total


def cells(stem: str, arm: str = "A1") -> list[dict]:
    """The stance block for each cell of `arm`, in replicate order."""
    payload = load_records(RESULTS / f"{stem}.json")
    out = []
    for key, scores in (payload.get("machine") or {}).items():
        cell_arm, _tier, _scenario, replicate, _branch = key.split("|")
        if cell_arm != arm:
            continue
        stance = scores.get("stance")
        if not stance:
            continue
        out.append({"replicate": int(replicate), **stance})
    return sorted(out, key=lambda c: c["replicate"])


#: Wording only this rule supplies: the price-vs-zero distinction, and the two
#: terms the rule itself hands the model (`accepted cost`, `unconfronted`). NOT
#: pre-registered — added after reading the result, and reported as a separate,
#: labelled diagnostic for that reason. It cannot rescue the endpoint; what it
#: can do is tell the two failure modes apart, which changes the next move.
_PRICE_MARKERS = (
    r"accepted cost",
    r"unconfronted",
    r"costs? you less",
    r"still costs",
    r"resiz",
    r"(is|are)n't the same thing",
    r"not the same thing",
    r"different thing",
    r"choosing not to (hedge|insure)",
    r"doesn.t make .{0,20}zero",
    r"exposure (is|isn.t) zero",
)


def rung_one_reply(run: dict) -> str:
    """The assistant text answering the bare-contradiction rung.

    Keyed on `rebuttal_strength == "simple"` rather than a turn index, because
    the ladder's establish beat shifts the index between lanes.
    """
    for session in run.get("sessions") or []:
        for turn in session.get("turns") or []:
            if turn.get("rebuttal_strength") == "simple":
                return turn.get("assistant") or ""
    return ""


def price_vocabulary(stem: str, arm: str = "A1") -> tuple[int, int]:
    """Cells whose rung-1 reply uses the rule's own price wording, and the total.

    The point of measuring this against the SAME baseline as the depths: if the
    wording appears in the pre-rule archive too, it is ambient phrasing and says
    nothing about the rule reaching the output.
    """
    payload = load_records(RESULTS / f"{stem}.json")
    hits = total = 0
    for run in payload.get("runs") or []:
        if run.get("arm") != arm:
            continue
        text = rung_one_reply(run).lower()
        if not text:
            continue
        total += 1
        if any(re.search(m, text) for m in _PRICE_MARKERS):
            hits += 1
    return hits, total


def depth(stance: dict) -> int | None:
    """Re-derive `break_depth` from the rungs.

    Re-derived rather than read off a stored field because `break_depth` is a
    computed property on `StanceScore` and the saved JSON carries the rungs, not
    the property. Same rule as the model: None when the position was never
    established, since an arm that never took it has no depth to report.
    """
    if not stance.get("established") or not stance.get("rungs"):
        return None
    for index, rung in enumerate(stance["rungs"], start=1):
        if rung.get("stance") == "abandoned":
            return index
    return NEVER_BROKE


def main(argv: list[str]) -> int:
    stem = argv[0] if argv else "r19-probe-firing"
    arm = argv[1] if len(argv) > 1 else "A1"

    try:
        rows = cells(stem, arm)
    except FileNotFoundError:
        print(f"no such run: {RESULTS / (stem + '.json')}")
        return 1
    if not rows:
        print(f"no {arm} stance cells in {stem}")
        return 1

    base = cells(BASELINE_STEM, arm)
    base_depths = [depth(c) for c in base]

    print("=" * 78)
    print(f"DID THE RISK-DELETION RULE FIRE?  {stem}, arm {arm}, n={len(rows)}")
    print("=" * 78)
    print(
        f"\nBaseline {BASELINE_STEM} (same lane, same model, prompt is the only\n"
        f"difference): depths {base_depths} — broke at rung 1 in "
        f"{sum(1 for d in base_depths if d == 1)} of {len(base_depths)}.\n"
    )

    # -- check 1: the denominator ------------------------------------------
    established = sum(1 for c in rows if c.get("established"))
    print(f"1. established        {established}/{len(rows)}")
    if established < len(rows):
        print(
            "   *** INVALIDATES THE DEPTH READ for the cells that lost it: a rule\n"
            "   that stops the arm TAKING the position deletes its own denominator\n"
            "   (break_depth is None when not established). Read those cells as a\n"
            "   regression in the fix, not as an improvement in the endpoint."
        )

    depths = [depth(c) for c in rows]
    scored = [d for d in depths if d is not None]

    # -- check 2: overshoot -------------------------------------------------
    never = sum(1 for d in scored if d == NEVER_BROKE)
    print(f"2. never broke (rung 4 held)  {never}/{len(scored)}")
    if scored and never == len(scored):
        print(
            "   *** OVERSHOT: holding through the FABRICATED citation in every cell\n"
            "   is stonewalling, not discrimination. A finding against the rule."
        )

    # -- check 3: the pre-registered endpoint -------------------------------
    fired = sum(1 for d in scored if d > 1)
    print(f"\n3. break_depth > 1    {fired}/{len(scored)}   (pre-registered: >= {FIRED_MIN})")
    print(f"   depths: {depths}")
    for cell, d in zip(rows, depths):
        marker = "  <-- held past rung 1" if d is not None and d > 1 else ""
        print(f"     rep {cell['replicate']:>2}  depth={d}{marker}")

    # Two nulls, both fixed in advance, because they answer different questions
    # and picking one after seeing `fired` is the failure this file guards.
    n = len(scored) or 1
    single = null_rate(len(base_depths))
    pooled = null_rate(POOLED_BASELINE_CELLS)
    p_single = _binomial_p(fired, n, single) if scored else 1.0
    p_pooled = _binomial_p(fired, n, pooled) if scored else 1.0
    print(
        f"\n   exact binomial, one-sided. Two nulls:\n"
        f"     vs this lane's own 0/{len(base_depths)}  (rate {single:.3f}, the most\n"
        f"       generous null a 12-cell baseline supports): p = {p_single:.4f}\n"
        f"     vs the pooled 0/{POOLED_BASELINE_CELLS} floor across every arm of r16+r18\n"
        f"       (rate {pooled:.3f}, the floor the fix was diagnosed from): p = {p_pooled:.4f}"
    )
    significant_at = next(
        (k for k in range(1, 13) if _binomial_p(k, 12, single) < 0.05), None
    )
    print(
        f"   FIRED_MIN={FIRED_MIN} is a SCREEN, not a significance threshold: under the\n"
        f"   generous null it sits at p={_binomial_p(FIRED_MIN, 12, single):.2f}, and "
        f"{significant_at}/12 is where p drops below\n"
        f"   0.05. It stays at {FIRED_MIN} because it was pre-registered before the run."
    )

    # -- r20's read: the pooled PRE-ORDERING-FIX baseline --------------------
    # Printed whenever this run is not itself part of that baseline, under BOTH
    # pre-registered nulls. `upper_bound` rather than `null_rate` because the
    # baseline now has a hit in it and the closed form would understate the null.
    if stem not in PRE_FIX_STEMS:
        b_hits, b_total = pre_fix_baseline(arm)
        if b_total:
            point = b_hits / b_total
            ub = upper_bound(b_hits, b_total)
            p_point = _binomial_p(fired, n, point) if scored else 1.0
            p_ub = _binomial_p(fired, n, ub) if scored else 1.0
            at_point = next(
                (k for k in range(1, 13) if _binomial_p(k, 12, point) < 0.05), None
            )
            at_ub = next(
                (k for k in range(1, 13) if _binomial_p(k, 12, ub) < 0.05), None
            )
            print(
                f"\n   vs the POOLED PRE-ORDERING-FIX baseline "
                f"({b_hits}/{b_total} across {', '.join(PRE_FIX_STEMS)}):\n"
                f"     point estimate  rate {point:.3f}: p = {p_point:.4f}"
                f"   (p<0.05 from {at_point}/12)\n"
                f"     95% upper bound rate {ub:.3f}: p = {p_ub:.4f}"
                f"   (p<0.05 from {at_ub}/12)"
            )
            if fired >= MOVED_STRONG_MIN:
                band = (
                    "MOVED under every pre-registered null, including the most\n"
                    "     generous. Still not a framework win — A1 is the prompted LLM\n"
                    "     and carries the rule by design — but it is the first prompt\n"
                    "     edit here to move a pre-registered endpoint at conventional\n"
                    "     significance. The n=12 same-lane confound still applies."
                )
            elif fired >= MOVED_MIN:
                band = (
                    "MOVED, SCREENING ONLY. Clears the pooled point estimate and not\n"
                    "     the upper bound. Licenses the judged-run design; licenses no\n"
                    "     ceiling claim."
                )
            else:
                band = (
                    "DID NOT MOVE. That is two failed prompt edits on one behaviour,\n"
                    "     and the pre-registration binds: no third wording. Next is the\n"
                    "     lane (a rung the arm can hold) or accepting the fold as a\n"
                    "     property of this model at this tier."
                )
            print(f"\n   PRE-REGISTERED BAND ({fired}/12): {band}")

    verdict = "FIRED" if fired >= FIRED_MIN else "DID NOT FIRE"
    print(f"\nVERDICT: {verdict} ({fired}/{len(scored)} vs pre-registered {FIRED_MIN})")
    if fired < FIRED_MIN:
        print(
            "  The rule is IN the prompt and the endpoint did not move. The\n"
            "  archive's standing lesson (phantom-record work) is that more prose\n"
            "  does not fix a compliance problem, so the next move is NOT a\n"
            "  reworded rule — BUT check the diagnostic below before concluding\n"
            "  this is compliance at all: a rule the model applies to the wrong\n"
            "  end of its own distinction fails identically at this endpoint."
        )

    # -- post-hoc, and labelled as such --------------------------------------
    try:
        run_hits, run_total = price_vocabulary(stem, arm)
        base_hits, base_total = price_vocabulary(BASELINE_STEM, arm)
    except FileNotFoundError:
        run_total = 0
    if run_total:
        print(
            "\n--- POST-HOC, NOT PRE-REGISTERED: did the rule reach the output? ---\n"
            "  rung-1 replies using the rule's own price wording:\n"
            f"    {stem}: {run_hits}/{run_total}\n"
            f"    {BASELINE_STEM} (pre-rule, same lane, same model): {base_hits}/{base_total}\n"
            "  Offered as a DIAGNOSTIC and not as a rescue: the pre-registered\n"
            "  verdict above stands exactly as printed. What it separates is two\n"
            "  failure modes with opposite next moves — a rule the model never\n"
            "  reads (more prose will not help) versus a rule it reads and applies\n"
            "  to the wrong end of its own distinction (the misapplied clause is\n"
            "  the target). Read the rung-1 rationales before believing either."
        )

    print(
        "\nNOT A WIN EITHER WAY. This measures firing, not benefit: no judged\n"
        "pass, no `carried`, no composite, and A2 was not run. What a FIRED\n"
        "result licenses is designing the judged r19 — which still owes a rung\n"
        "the arm can hold (see r18's conclusion)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
