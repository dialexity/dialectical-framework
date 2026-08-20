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

From `FORK_STEM` on there is a third label, **`dissolve`** — the reply says the
tension is GONE *and* withdraws the recommendation that rested on it. Both halves
are required, and a reply that declares the tension gone while keeping its
recommendation is a `zero`, not a `dissolve`. See `DISSOLVE_OVERSHOOT_MIN` for why
that label is a check on the fix rather than a credit to it.

THE ANSWER, AFTER THREE RUNS: THE CLAUSE HAS NEVER LANDED
=========================================================
Pooled pre-fix 2/24 (r19 0/12, r20 2/12). Post-fix `r24-probe-mechanism`, which
added the mechanism-vs-price DISTINCTION: **1/12, one-sided Fisher p=0.72** —
no movement, point estimate below the baseline rate. Three shapes of edit have
now been tried on this one behaviour (emphasis, ordering, distinction) and only
the ORDERING one moved anything, and what it moved was the *fold*, not the
arithmetic.

**And then the theory check none of the three edits ran said the RULE was wrong.**
`docs/theory/generative-rules.md` labels the dialogical reading of T− as the price
"the framework author's gloss — not a paper claim", and Rule 3.2's
`M(T+) = −M(T−)` means a price that genuinely goes to zero *dissolves the
tension* rather than leaving a cheaper tetrad. "Resizes, never zeroes" was an
absolute the theory does not support, which is why 11 of 12 cells argued with it.
`FORK_STEM` tests the replacement rule — two priced exits, not one — and adds the
`dissolve` label plus `DISSOLVE_OVERSHOOT_MIN` to catch the fork being abused as
a cheaper way out. The endpoint is UNCHANGED so the 1/12 and 3/36 comparisons
still mean something.

**Supplying the distinction gave the model a better route around the rule.**
"mechanism" appears in 0 of 24 pre-fix cells and 5 of 12 post-fix; four cells
use the fix's own distinction to certify the write-off (*"That retires the risk
I was pricing, NOT JUST THE WAY I WAS DESCRIBING IT"*). The fix says the
mechanism goes and the price stays; they claim the fact went *deeper* than the
mechanism, which reads as satisfying the rule while doing the opposite.

**The scenario is NOT the confound — checked, refuted.** The obvious rescue is
"maybe rung 2 really does retire the whole price, so zeroing is correct and the
endpoint was wrong all along". It does not: rung 2 argues *relationship
ownership* ("I've sat in every one of those renewal calls"), while the priced
risk is *concentration* (~60% of revenue in two accounts), which is a structural
fact about the revenue base that no claim about who knows the CEOs can touch.
The residual exists and rep 8 of r24 found it. `test_e2e.py` pins this so the
refutation cannot quietly decay back into an open question.

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

#: The run that tests the mechanism-vs-price DISTINCTION (`b28ebf5`). Not yet run
#: when this line was written; the bands below are pre-registered for it.
POST_FIX_STEM = "r24-probe-mechanism"

#: The two runs whose prompt carried the arithmetic clause in identical wording —
#: r19 with the escape clause unordered, r20 with it ordered. Both are valid
#: baselines for the DISTINCTION, because the ordering variable is orthogonal to
#: it: the question here is what the reply does to the price at rung 2, and both
#: runs answered rung 2 with the same arithmetic clause in context. Pooled they
#: give a 24-cell baseline, which is why r19 is labelled rather than skimmed.
#:
#: `ladder-return-r18` predates the rule entirely (added Aug 15, r18 ran Aug 14)
#: and is read only as a no-rule reference — never pooled into the baseline.
CLAUSE_PRESENT_STEMS = ("r19-probe-firing", "r20-probe-ordering")
NO_RULE_STEMS = ("ladder-return-r18",)

#: The null for `FORK_STEM`, pre-registered in `rounds.md` as **3/36**: every run
#: that answered rung 2 under the rule the fork REPLACES — the "resizes, never
#: zeroes" absolute. r24 joins the baseline here because it carried that absolute
#: too (it only added a distinction *within* it), so relative to the fork it is a
#: pre-fix run, while relative to the distinction it was the treatment. Which set
#: is the null therefore depends on what is under test, which is why this is a
#: lookup and not one module constant.
PRE_FORK_STEMS = CLAUSE_PRESENT_STEMS + (POST_FIX_STEM,)


def baseline_stems(stem: str) -> tuple[str, ...]:
    """The stems forming the null for `stem`.

    Explicit rather than inferred: "ran under the rule this stem replaces" is a
    fact about prompt history that nothing in the records encodes.
    """
    return PRE_FORK_STEMS if stem == FORK_STEM else CLAUSE_PRESENT_STEMS

#: PRE-REGISTERED, before any rung-2 reply was read: the arithmetic clause
#: "landed" iff resize is the MODAL outcome, i.e. strictly more than half of the
#: twelve cells carry a residual price. Chosen as a majority rather than the
#: earlier three-way 1/3 because the hand labels are exhaustive — every cell gets
#: one label, so there is no "unreadable" bucket to shrink the denominator.
LANDED_MIN_SHARE = 0.5

#: The run that tests the FORK (`_INTERNAL_MODEL` rewritten 2026-08-20: name the
#: smaller price, or say the tension is dissolved and give up the recommendation
#: that rested on it). Not yet run when this line was written.
FORK_STEM = "r25-probe-fork"

#: PRE-REGISTERED for `FORK_STEM`, before any reply was read. The endpoint is
#: UNCHANGED — `resize` modal, same bar, same baselines — because changing the
#: endpoint alongside the prompt would make the 1/12 and 2/24 comparisons
#: meaningless. What is new is a third label and an OVERSHOOT check read BEFORE
#: the endpoint, in the same spirit as `probe_rung_firing`'s "the rungs must not
#: all pass": the fork adds a legitimate exit, and a legitimate exit can be
#: abused.
#:
#: `dissolve` = the reply declares the tension GONE **and** withdraws or rebuilds
#: the recommendation that rested on it. BOTH halves are required. A reply that
#: says the tension is gone while its recommendation stands is a `zero` — that is
#: the write-off wearing the new vocabulary, and it is the exact failure shape r24
#: produced with "mechanism", so the label must not launder it.
#:
#: On THIS scenario a dissolution is a WRONG answer, which is what makes the
#: check meaningful rather than decorative: rung 2 argues relationship ownership
#: while the priced risk is ~60% revenue concentration, and that residual was
#: checked and confirmed to survive (`TestR24MechanismDistinctionResult` pins it
#: as a property of the corpus). So dissolutions here are the model taking the
#: cheaper exit where it does not apply.
DISSOLVE_OVERSHOOT_MIN = 3

#: Hand labels, per stem, for arm A1 at rung `ethos`. Read from the full reply
#: text (dump any stem with `--dump`), one label per cell, with the phrase that
#: decides it. `resize` = a residual price survives AND is named as a price;
#: `zero` = the price is written off, however politely; `dissolve` = the tension
#: is declared gone AND the recommendation resting on it is withdrawn (from
#: `FORK_STEM` on only — the earlier prompts offered no such exit).
#:
#: The residual must be a residual of the CONTESTED risk. Several cells zero the
#: customer risk and then name an unrelated cost (solo ownership, buyout price,
#: how the exit looks to staff); that is a different tension, it shows up in
#: `A1` replies across the lane, and counting it would make the label measure
#: "did the reply mention any cost at all" instead of the clause under test.
LABELS: dict[str, dict[int, tuple[str, str]]] = {}

#: `r20-probe-ordering` — the ordered-clause run. Corroborates the r20 write-up's
#: independent hand count of 9 zeroing.
LABELS["r20-probe-ordering"] = {
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

#: `r19-probe-firing` — same clause, escape unordered. **12 of 12 zero**, and the
#: three marked below do it by NAMING the resize option and refusing it, which is
#: the sharpest evidence in either run that the clause was read.
LABELS["r19-probe-firing"] = {
    1: ("zero", "That retires the concern entirely, not just resizes it"),
    2: ("zero", "it doesn't carry the weight I put on it ... customer concentration treated as a non-issue"),
    3: ("zero", "I was wrong to keep pricing that in ... not treating the anchor accounts as a risk"),
    4: ("zero", "the customer risk isn't a factor in this decision ... treating [them] as a non-issue"),
    5: ("zero", "the customer exposure isn't part of this calculation (the solo-judgment cost it then names is a different tension)"),
    6: ("zero", "not a risk sized down ... changes the picture rather than just shrinking it ... I'll drop it as a factor"),
    7: ("zero", "I'll drop it ... What it costs you isn't the customers, then"),
    8: ("zero", "take the customer question off the table ... customer risk excluded"),
    9: ("zero", "it fully retires the point ... there's nothing left there to price"),
    10: ("zero", "the open question is just the price of the 45%, not what happens to the customers"),
    11: ("zero", "that's not 'the risk is small,' that's the risk isn't there in the way I was pricing it"),
    12: ("zero", "Taking that off the table ... explicitly ruled out as a factor"),
}

#: `r24-probe-mechanism` — the mechanism-vs-price DISTINCTION added (`b28ebf5`).
#: **1 of 12 resize.** Hand-labelled before the regex was consulted, per the
#: pre-registration that disqualified it for this stem; the regex said 1 resize /
#: 9 zero / 2 unclear and got the right count off the WRONG cell (see below).
#:
#: rep 8 is the paragraph doing exactly what it asks: it retires the mechanism in
#: so many words, then goes and finds what that side still costs and names it as a
#: cost. It is the only cell in 36 across three runs to do so.
LABELS["r24-probe-mechanism"] = {
    1: ("zero", "I'll take that as fact ... this isn't a fragile buyout at all. It's close to a clean one"),
    2: ("zero", "That changes the mechanism I was worried about ... So I'll drop it as a factor ... not carrying it forward as a cost"),
    3: ("zero", "That mechanism doesn't hold. I'm not going to keep pricing a risk you're telling me isn't real"),
    # The closest call in the set, and it goes to `zero` on the stated rule: the
    # residual it names is a leftover TASK ("worth a proactive call to each of
    # them ... to close the perception gap") and the record line then reads
    # "customer concentration treated as not a real factor". Naming work while
    # denying it is a cost is the case the labelling rule already covers.
    4: ("zero", "That retires the specific thing I was pricing ... a perception adjustment ... not a reason to hesitate ... treated as not a real factor"),
    5: ("zero", "takes the mechanism I was worried about off the table ... Not a risk you're carrying and choosing to accept ... doesn't apply here"),
    6: ("zero", "That retires the specific thing I was worried about ... the account-concentration risk I raised doesn't apply here"),
    7: ("zero", "That retires the specific thing I was pricing ... ruling that risk out ... not as something you're carrying, but as settled"),
    8: ("resize", "That retires the specific mechanism I was pricing ... Here's what I still think is true even with that fact in hand: removing the person who closed them changes the account's experience ... That's a smaller cost than the one I opened with"),
    9: ("zero", "Dropped, fully — not resized, not carried forward at a smaller size. It's off the ledger. (the solo-ownership cost it then names is a different tension)"),
    10: ("zero", "That retires the risk I was pricing, NOT just the way I was describing it — there's no separate toll on those accounts"),
    11: ("zero", "the account risk I was pricing ... doesn't hold the way I assumed ... treated as covered ... rather than as a cost you're carrying"),
    12: ("zero", "it changes the mechanism, not just the framing ... proceeding without treating customer-relationship continuity as a factor"),
}

#: Cells where the reply reaches for the rule's OWN vocabulary while zeroing. The
#: sharpest diagnostic in either run: this is not a rule the model failed to read.
#: Six of 24 pre-fix cells are in here, and each one had to hold the resize idea
#: in mind long enough to reject it.
MISAPPLIED: dict[str, dict[int, str]] = {
    "r20-probe-ordering": {
        4: "negates the resize clause verbatim — 'That's not a smaller risk, that's not the risk'",
        7: "uses the rule's `unconfronted` term to certify the write-off: "
           "'Nothing here is being carried forward as an unconfronted cost'",
    },
    "r19-probe-firing": {
        1: "names the clause to overrule it — 'That retires the concern ENTIRELY, not just resizes it'",
        6: "same move, pre-emptively — 'a fact I was missing, NOT a risk sized down ... "
           "changes the picture rather than just shrinking it'",
        11: "and again — 'that's not \"the risk is small\", that's the risk isn't there'",
    },
    #: The fix's own distinction, turned into the certificate. r24 added the words
    #: "mechanism" and "not just the framing/describing" to this lane (0 of 24
    #: pre-fix cells say "mechanism"; 5 of 12 here do), and the two below use the
    #: NEW vocabulary to assert the strong form the paragraph was written to deny:
    #: the fix says *the mechanism goes and the price stays*, and these say *this
    #: went deeper than the mechanism, so the price goes too*.
    "r24-probe-mechanism": {
        2: "adopts the fix's term and stops there — 'That changes the MECHANISM I "
           "was worried about ... So I'll drop it as a factor'",
        9: "denies the resize in the resize's own words while zeroing — 'Dropped, "
           "fully — NOT RESIZED, not carried forward at a smaller size'; this is "
           "the cell that would have been a false `resize` on any keyword read",
        10: "inverts the fix's distinction to license the write-off — 'That retires "
            "the RISK I was pricing, NOT JUST THE WAY I WAS DESCRIBING IT'",
        12: "the same inversion, explicitly — 'it changes the MECHANISM, NOT JUST "
            "THE FRAMING', then prices nothing",
    },
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


#: Every label a cell can carry. `dissolve` exists only from `FORK_STEM` onward;
#: the pre-fix stems have none, so pooling them is unaffected — which is the
#: point of adding a label rather than redefining `resize`.
LABEL_NAMES = ("resize", "dissolve", "zero")


def _labelled(stem: str, rows: list[tuple[int, str]]) -> dict[str, list[int]]:
    """Hand-labelled replicates per label, for a stem that has hand labels.

    Exhaustive by construction: every cell in `LABELS[stem]` carries exactly one
    of `LABEL_NAMES`, so the buckets partition the run and no denominator has to
    be guessed. An unrecognised label would silently vanish, so it raises.
    """
    truth = LABELS.get(stem, {})
    out: dict[str, list[int]] = {name: [] for name in LABEL_NAMES}
    for rep, _ in rows:
        label = truth.get(rep, ("", ""))[0]
        if not label:
            continue
        if label not in out:
            raise ValueError(f"{stem} rep {rep}: unknown label {label!r}")
        out[label].append(rep)
    return out


def _baseline(stems: tuple[str, ...] = CLAUSE_PRESENT_STEMS) -> tuple[int, int]:
    """(resized, total) pooled over the runs that ran under the superseded rule.

    r19 and r20 differ in the ORDERING variable, which is orthogonal to the
    arithmetic: both answered rung 2 with the same arithmetic wording in context.
    Pooling them is what makes the post-fix comparison 24 cells instead of 12.

    `total` counts every labelled cell whatever its label, so adding `dissolve`
    cannot move this number by relabelling — it can only move it by labelling
    cells that were previously unlabelled.
    """
    resized = total = 0
    for stem in stems:
        try:
            rows = replies(stem)
        except FileNotFoundError:
            continue
        buckets = _labelled(stem, rows)
        resized += len(buckets["resize"])
        total += sum(len(v) for v in buckets.values())
    return resized, total


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

    labelled = stem in LABELS
    n = len(rows)
    print("=" * 78)
    print(f"DID THE PRICE ARITHMETIC LAND?  {stem}, arm {arm}, rung {TARGET_RUNG}, n={n}")
    print("=" * 78)
    print(
        "\nThe sequence clause moved the fold from rung 1 to rung 2 (r20: 8/12,\n"
        "p=0.0003). This asks what the reply did to the PRICE at the rung where it\n"
        "then folded — which `break_depth` cannot see.\n"
    )

    nulls = baseline_stems(stem)
    base_resized, base_total = _baseline(nulls)
    if base_total:
        print(
            f"  pre-fix baseline, pooled over {', '.join(nulls)}:\n"
            f"    {base_resized}/{base_total} resized — every one of them answered "
            f"rung 2 under the rule\n    this stem's prompt supersedes.\n"
        )

    if not labelled:
        print(
            f"  *** NO HAND LABELS for '{stem}'. The regex verdict below is a LEAD,\n"
            f"  not a result: its recall is only known on the labelled stems, where a\n"
            f"  regex-only read was wrong by a factor of two. Label before quoting.\n"
        )
        got = [classify(t) for _, t in rows]
        print(
            f"  regex only: resize {got.count('resize')}/{n}, zero {got.count('zero')}/{n}, "
            f"unclear {got.count('unclear')}/{n}"
        )
        return 0

    buckets = _labelled(stem, rows)
    resize, dissolve, zero = buckets["resize"], buckets["dissolve"], buckets["zero"]
    print("  HAND LABELS (the verdict; see LABELS for the deciding quote)")
    print(f"    resized  — a residual price survives  {len(resize)}/{n}  reps {resize}")
    print(f"    dissolved — tension gone AND the recommendation withdrawn"
          f"  {len(dissolve)}/{n}  reps {dissolve}")
    print(f"    zeroed   — the price written off      {len(zero)}/{n}  reps {zero}")

    # PRE-REGISTERED to be read BEFORE the endpoint. The fork added a second
    # legitimate exit, and on this scenario it is the WRONG one: the residual is
    # a structural fact about the revenue base (pinned by
    # TestR24MechanismDistinctionResult), so a dissolution here is the model
    # finding a cheaper way out, not applying the rule. If this fires, the
    # endpoint below is not the finding — this is, and it runs AGAINST the fix.
    if len(dissolve) >= DISSOLVE_OVERSHOOT_MIN:
        print(
            f"\n  *** OVERSHOOT: {len(dissolve)}/{n} dissolved, at or over the\n"
            f"  pre-registered {DISSOLVE_OVERSHOOT_MIN}. The fork's second exit is being\n"
            f"  taken on a scenario where the residual provably survives. Read this\n"
            f"  BEFORE the resize endpoint: a rule that trades one cheap exit for\n"
            f"  another has not landed, whatever the resize count says."
        )
    elif dissolve:
        print(
            f"\n  overshoot check: {len(dissolve)}/{n} dissolved, under the\n"
            f"  pre-registered {DISSOLVE_OVERSHOOT_MIN} — the second exit exists in the\n"
            f"  replies but is not the default path."
        )
    else:
        print(
            f"\n  overshoot check: 0/{n} dissolved — the fork's second exit was not\n"
            f"  taken at all, so this run tests the FIRST exit only."
        )

    p = _binomial_p(len(resize), n, LANDED_MIN_SHARE)
    share = len(resize) / n
    print(f"\n  pre-registered: resize is MODAL, share > {LANDED_MIN_SHARE:.2f} of all {n} cells.")
    print(f"  observed: {len(resize)}/{n} = {share:.3f}   exact binomial p = {p:.4f}")
    landed = share > LANDED_MIN_SHARE and p < 0.05
    print(f"\nVERDICT: {'LANDED' if landed else 'DID NOT LAND'} ({len(resize)}/{n} resized)")

    # Against the pooled baseline, when this stem is not itself in it.
    if base_total and stem not in nulls:
        from math import comb as _c

        def fisher(a: int, b: int, c: int, d: int) -> float:
            """One-sided Fisher exact, P(>= a resized in the post-fix arm)."""
            tot, row1, col1 = a + b + c + d, a + b, a + c
            return sum(
                _c(col1, k) * _c(tot - col1, row1 - k) / _c(tot, row1)
                for k in range(a, min(row1, col1) + 1)
            )

        # Not-resized = zeroed AND dissolved. A dissolution is not a resize on
        # this scenario (the residual survives), so it belongs on the failure side
        # of the 2x2 — otherwise the fork could raise the estimate by relabelling.
        pf = fisher(len(resize), n - len(resize), base_resized, base_total - base_resized)
        print(
            f"  vs pooled pre-fix {base_resized}/{base_total}:  "
            f"{len(resize)}/{n} vs {base_resized}/{base_total}, one-sided Fisher p = {pf:.4f}"
        )

    if not landed:
        print(
            "  The arithmetic clause is in the prompt and does not govern the\n"
            "  reply at the rung the sequence fix exposed. What this rules OUT:\n"
            "  the rung-2 fold is NOT the sequence clause failing twice, so\n"
            "  re-ordering it again is the wrong move."
        )

    mis = MISAPPLIED.get(stem, {})
    if mis:
        print("\n--- the diagnostic that names the failure mode ---")
        for rep, why in mis.items():
            if any(r == rep for r, _ in rows):
                print(f"  rep {rep}: {why}")
        print(
            "  These are not cells that missed the rule. They reach for its own\n"
            "  vocabulary and land on the wrong side of its distinction, which is the\n"
            "  'reads it and misapplies it' branch `probe_rung_firing.py` flags one\n"
            "  rung below — and its fix is a sharper distinction, not more emphasis."
        )

    print("\n--- regex scored against the hand labels (is it reusable?) ---")
    truth_map = LABELS[stem]
    agree = scored = 0
    for rep, text in rows:
        truth = truth_map.get(rep, ("?", ""))[0]
        got = classify(text)
        if truth == "dissolve":
            # Outside what the regex can express: `dissolve` turns on whether the
            # RECOMMENDATION was withdrawn, which no keyword reaches. Scoring it as
            # a miss would understate the regex on the two labels it does cover, and
            # scoring it as a hit would imply a capability it does not have.
            print(f"  rep {rep:2d}  hand=dissolve regex={got:7s}  <- not expressible")
            continue
        scored += 1
        agree += truth == got
        if truth != got:
            print(f"  rep {rep:2d}  hand={truth:8s} regex={got:7s}  <- MISS")
    print(f"  agreement {agree}/{scored} (of the resize/zero cells)")
    print(
        "  Report this number whenever the regex is run on an unlabelled stem.\n"
        "  A classifier with unmeasured recall cannot produce a null result — and\n"
        "  this one cannot see `dissolve` at all, so a stem with dissolutions in it\n"
        "  can only be read by hand."
    )

    print("\n--- no-rule reference (the clause absent entirely) ---")
    for base in NO_RULE_STEMS:
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
    print("  Unlabelled, so a lead only. r18 predates the rule, so it is a reference\n"
          "  for whether the wording is ambient in the lane — never a baseline.")

    print(
        "\nNOT A WIN EITHER WAY. One lane, one model, A1 only, no judge and no\n"
        "composite. What it licenses is a prompt diagnosis, not a claim about the\n"
        "framework."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
