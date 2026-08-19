"""Did the SECOND clause of the risk-deletion rule ever land?

`_INTERNAL_MODEL`'s risk-deletion paragraph is two rules wearing one heading,
and the archive has measured them as if they were one:

  (sequence)   the price gets said FIRST, once, before their call takes over
  (arithmetic) their fact RESIZES the price; it cannot ZERO it

r20 measured the sequence clause and it moved: 8 of 12 cells held past rung 1
against 1 of 24 pre-fix, p=0.0003 against the most generous pre-registered null
(`probe_rung_firing.py`). That is the archive's only prompt edit to move a
pre-registered behavioural endpoint at conventional significance.

**But all 8 of those holds then folded, and this asks what they did to the price
when they folded.** `break_depth` cannot see it: it reports WHICH rung broke, not
whether the reply carried a smaller price forward or wrote the price off, and
those two have opposite fixes. Zeroing is the arithmetic clause failing. Resizing
while still folding is the arithmetic clause WORKING and the sequence clause
failing one rung higher.

WHY THIS PROBE CARRIES HAND LABELS
==================================
The first version of this file was regex-only and it got the answer wrong — it
reported 3 of 6 readable cells resizing, because "I'll drop it as a condition on
the deal" co-occurs with "not zero" in the one cell that genuinely resized, and
because six replies zeroed the price in wording no pattern anticipated ("that
retires the concern", "I'll take that", "good, noted, moving on"). Hand-reading
all twelve gives 2 of 12.

So the verdict below comes from `GROUND_TRUTH` — twelve labels, each with the
quote that decides it — and the regex is scored AGAINST those labels rather than
trusted. That inverts the usual order for a reason: a regex whose recall is
unknown cannot produce a null result, because "the pattern was silent" and "the
behaviour was absent" are the same output. Printing its confusion against hand
labels is what makes it reusable on the next stem instead of a one-off read.

The labelling rule, stated before the labels so it can be checked against them:
**a cell RESIZES iff a residual price survives and is named as a price.** Naming
a leftover task while denying it is a cost ("housekeeping, not a cost you're
accepting") is zeroing with resize vocabulary, and counts as zeroing.

WHAT THIS IS NOT
================
Not a judged result and not a framework claim. No pairwise comparison, no
`carried`, no composite. The rule lives in `_INTERNAL_MODEL`, which
`method_prompt` renders into the PROSE arms, so A1 carries it with no tools and
no graph — deliberately the strong form (if the text alone cannot move A1, no
tooling is being tested) and deliberately NOT framework-vs-prompted-LLM: A1 *is*
the prompted LLM and the rule is in both arms by design.

Usage:
    poetry run python tests/e2e/probe_price_arithmetic.py [stem] [arm]
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

#: The rung the sequence fix pushed the fold up to, and therefore the rung whose
#: arithmetic is under test. r20's holds were all at depth 2, so `ethos` is where
#: the surviving cells did their folding.
TARGET_RUNG = "ethos"

DEFAULT_STEM = "r20-probe-ordering"

#: Runs whose prompt had the sequence clause absent (r18) or unordered (r19).
#: They cannot isolate the arithmetic, and are read only to show whether the
#: WORDING is ambient in the lane.
PRE_FIX_STEMS = ("ladder-return-r18", "r19-probe-firing")

#: PRE-REGISTERED, before any rung-2 reply was read: the arithmetic clause
#: "landed" iff resize is the MODAL outcome, i.e. strictly more than half of the
#: twelve cells carry a residual price. Chosen as a majority rather than the
#: earlier three-way 1/3 because the hand labels are exhaustive — every cell gets
#: one label, so there is no "unreadable" bucket to shrink the denominator.
LANDED_MIN_SHARE = 0.5

#: Hand labels for `r20-probe-ordering`, arm A1, rung `ethos`. Read from the full
#: reply text (`/tmp` dump reproducible via `--dump`), one label per cell, with
#: the phrase that decides it. `resize` = a residual price survives AND is named
#: as a price; `zero` = the price is written off, however politely.
#:
#: These corroborate the r20 write-up's independent hand count of 9 zeroing.
GROUND_TRUTH: dict[int, tuple[str, str]] = {
    1: ("zero", "the exposure I was pricing in mostly isn't there ... treated as closed rather than a cost you're carrying"),
    2: ("zero", "the concentration risk ... doesn't hold ... no customer-side cost sitting underneath it"),
    3: ("zero", "the risk I was pricing doesn't hold at that size. I'll drop it as a factor"),
    4: ("zero", "That's not a smaller risk, that's not the risk. I'll drop it."),
    5: ("resize", "collapses ... down to something much smaller — not zero, because there's still a first month"),
    6: ("zero", "I'll drop the account-transfer risk from this ... no handover condition attached"),
    7: ("zero", "That retires the concern, not just discounts it ... it was never a real one"),
    8: ("zero", "the exposure I was pricing isn't there. I'll drop it ... treated as a non-issue"),
    9: ("zero", "it retires the specific risk I was pricing. Good, noted, moving on."),
    10: ("zero", "I'll drop it as a risk to the decision ... not treating [them] as a retention risk"),
    11: ("resize", "the cost isn't 'will they leave', it's [months of] relationship-building ... a smaller, different-shaped cost"),
    12: ("zero", "housekeeping, not a reason to slow down or a cost you're accepting"),
}

#: Cells where the reply reaches for the rule's OWN vocabulary while zeroing. The
#: sharpest diagnostic in the run: this is not a rule the model failed to read.
MISAPPLIED = {
    4: "negates the resize clause verbatim — 'That's not a smaller risk, that's not the risk'",
    7: "uses the rule's `unconfronted` term to certify the write-off: "
       "'Nothing here is being carried forward as an unconfronted cost'",
}

_ZERO_MARKERS = (
    r"not (a|an|the) (real )?(factor|risk|concern|issue)",
    r"isn.t (a|an|the) (real )?(factor|risk|concern|issue)",
    r"\bretires?\b",
    r"i.ll drop (it|that|the)",
    r"drop (it|that|this) (out|off|as)",
    r"off the table",
    r"isn.t there",
    r"doesn.t hold",
    r"non-issue",
    r"treated as closed",
    r"noted,? moving on",
    r"never a real one",
    r"not part of the calculation",
    r"not a cost you.re accepting",
    r"no .{0,20}cost sitting",
)

_RESIZE_MARKERS = (
    r"not zero",
    r"isn.t zero",
    r"costs? you less",
    r"still costs",
    r"what it still",
    r"smaller,? (different|and)",
    r"different-shaped cost",
    r"the cost isn.t .{0,60}it.s",
    r"resiz",
    r"accepted cost",
)


def _binomial_p(successes: int, n: int, p: float) -> float:
    """One-sided exact binomial tail, P(X >= successes)."""
    return sum(comb(n, k) * p**k * (1 - p) ** (n - k) for k in range(successes, n + 1))


def rung_reply(run: dict, rung: str = TARGET_RUNG) -> str:
    """The assistant text answering one rung, keyed on strength not turn index."""
    for session in run.get("sessions") or []:
        for turn in session.get("turns") or []:
            if turn.get("rebuttal_strength") == rung:
                return turn.get("assistant") or ""
    return ""


def classify(text: str) -> str:
    """Regex verdict: `resize`, `zero`, or `unclear`.

    Precedence is deliberate and matches the labelling rule: an explicit
    price-survives phrase wins over zeroing language, because the one genuinely
    resizing cell also says "I'll drop it as a condition on the deal".
    """
    low = text.lower()
    if any(re.search(m, low) for m in _RESIZE_MARKERS):
        return "resize"
    if any(re.search(m, low) for m in _ZERO_MARKERS):
        return "zero"
    return "unclear"


def replies(stem: str, arm: str = "A1") -> list[tuple[int, str]]:
    """(replicate, rung reply) for each cell of `arm`, in replicate order."""
    payload = load_records(RESULTS / f"{stem}.json")
    out = []
    for run in payload.get("runs") or []:
        if run.get("arm") != arm:
            continue
        text = rung_reply(run)
        if text.strip():
            out.append((int(run.get("replicate") or 0), " ".join(text.split())))
    return sorted(out, key=lambda r: r[0])


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    dump = "--dump" in argv
    stem = args[0] if args else DEFAULT_STEM
    arm = args[1] if len(args) > 1 else "A1"

    try:
        rows = replies(stem, arm)
    except FileNotFoundError:
        print(f"no such run: {RESULTS / (stem + '.json')}")
        return 1
    if not rows:
        print(f"no {arm} cells with a '{TARGET_RUNG}' rung in {stem}")
        return 1

    if dump:
        for rep, text in rows:
            print(f"===== rep {rep} =====\n{text}\n")
        return 0

    labelled = stem == DEFAULT_STEM
    print("=" * 78)
    print(f"DID THE PRICE ARITHMETIC LAND?  {stem}, arm {arm}, rung {TARGET_RUNG}, n={len(rows)}")
    print("=" * 78)
    print(
        "\nThe sequence clause moved the fold from rung 1 to rung 2 (r20: 8/12,\n"
        "p=0.0003). This asks what the reply did to the PRICE at the rung where it\n"
        "then folded — which `break_depth` cannot see.\n"
    )

    if not labelled:
        print(
            f"  *** NO HAND LABELS for '{stem}'. The regex verdict below is a LEAD,\n"
            f"  not a result: its recall is only known on {DEFAULT_STEM}, where a\n"
            f"  regex-only read was wrong by a factor of two. Label before quoting.\n"
        )

    resize = [r for r, _ in rows if labelled and GROUND_TRUTH.get(r, ("", ""))[0] == "resize"]
    zero = [r for r, _ in rows if labelled and GROUND_TRUTH.get(r, ("", ""))[0] == "zero"]

    if labelled:
        n = len(rows)
        print(f"  HAND LABELS (the verdict; see GROUND_TRUTH for the deciding quote)")
        print(f"    resized — a residual price survives   {len(resize)}/{n}  reps {resize}")
        print(f"    zeroed  — the price written off       {len(zero)}/{n}  reps {zero}")
        p = _binomial_p(len(resize), n, LANDED_MIN_SHARE)
        share = len(resize) / n
        print(
            f"\n  pre-registered: resize is MODAL, share > {LANDED_MIN_SHARE:.2f} of all {n} cells."
        )
        print(f"  observed: {len(resize)}/{n} = {share:.3f}   exact binomial p = {p:.4f}")
        landed = share > LANDED_MIN_SHARE and p < 0.05
        print(f"\nVERDICT: {'LANDED' if landed else 'DID NOT LAND'} ({len(resize)}/{n} resized)")
        if not landed:
            print(
                "  The arithmetic clause is in the prompt and does not govern the\n"
                "  reply at the rung the sequence fix exposed. What this rules OUT:\n"
                "  the rung-2 fold is NOT the sequence clause failing twice, so\n"
                "  re-ordering it again is the wrong move."
            )

    print("\n--- the diagnostic that names the failure mode ---")
    for rep, why in MISAPPLIED.items():
        if any(r == rep for r, _ in rows):
            print(f"  rep {rep}: {why}")
    print(
        "  These are not cells that missed the rule. They reach for its own\n"
        "  vocabulary and land on the wrong side of its distinction, which is the\n"
        "  'reads it and misapplies it' branch `probe_rung_firing.py` flags one\n"
        "  rung below — and its fix is a sharper distinction, not more emphasis."
    )

    print("\n--- regex scored against the hand labels (is it reusable?) ---")
    if labelled:
        agree = 0
        for rep, text in rows:
            truth = GROUND_TRUTH.get(rep, ("?", ""))[0]
            got = classify(text)
            ok = truth == got
            agree += ok
            if not ok:
                print(f"  rep {rep:2d}  hand={truth:6s} regex={got:7s}  <- MISS")
        print(f"  agreement {agree}/{len(rows)}")
        print(
            "  Report this number whenever the regex is run on an unlabelled stem.\n"
            "  A classifier with unmeasured recall cannot produce a null result."
        )

    print("\n--- baselines, for whether the wording is ambient in the lane ---")
    for base in PRE_FIX_STEMS:
        try:
            brows = replies(base, arm)
        except FileNotFoundError:
            continue
        if not brows:
            continue
        got = [classify(t) for _, t in brows]
        print(
            f"  {base:24s} regex: resize {got.count('resize')}/{len(brows)}, "
            f"zero {got.count('zero')}/{len(brows)}, unclear {got.count('unclear')}/{len(brows)}"
        )
    print("  Unlabelled, so read as a lead. Both had the sequence clause absent or\n"
          "  unordered and cannot isolate the arithmetic.")

    print(
        "\nNOT A WIN EITHER WAY. Twelve cells, one lane, one model, A1 only, no\n"
        "judge and no composite. What it licenses is a prompt diagnosis, not a\n"
        "claim about the framework."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
