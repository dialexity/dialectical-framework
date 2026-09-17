"""Is the per-claim support judge measuring support? Spike-in validation.

    poetry run python tests/e2e/probe_support_validity.py            # the plan, free
    poetry run python tests/e2e/probe_support_validity.py --read     # the verdict, free
    poetry run pytest tests/e2e/probe_support_validity.py -s --real-llm

RESULT (2026-09-17, sonnet-5 judge, 18 calls, 144s) — ADDED AFTER THE RUN.
Everything from "WHAT IS BEING VALIDATED" down was written before a single judge
call and is unedited, so the bands below were registered and not fitted.
==================================================================================
**VERDICT: FIT TO QUOTE.** specificity 93% (28/30) [0.79,0.98] against a 90% bar,
sensitivity 100% (45/45) [0.92,1.00] against 70%, VERBATIM FLOOR 100% (18/18)
against 90%. Per class: verbatim 100%, compressed 83%, combined 67%, and
flipped / inflated / foreign / fabricated 100% each. Test-retest 94% over 120 items.

THE SAME-STRING CONTRAST: 18/18 supported against their own source, 0/18 against a
foreign one, wording identical. The judge is reading the source, not the claim.

THE COMPRESSION MECHANISM, the suspicion the original disclaimer named: CONFIRMED
and sized. verbatim 100% - compressed 83% = +17pp against the registered 15pp bar.

CORRECTED: the recorded 43.3% -> **39.3% [28.0,45.9]**; this run's fresh real-claim
rate 30.6% -> 25.6%.

FOUR THINGS THE PERSISTED VERDICTS BOUGHT AFTER THE FACT, FREE:
  1. THE `combined` EXCLUSION IS LOAD-BEARING, and it is the honest caveat rather
     than a technicality. Pooling all three supported classes gives specificity
     87% (34/39), which would read INDETERMINATE, and corrects 43.3% to 35.0%
     instead of 39.3%. Real extracted theses often ARE joins of two source
     sentences, so 35-39% is the band to quote, not 39.3% alone.
  2. THE TWO LABELS ARE NOT ONE INSTRUMENT, which is the finding to act on.
     `invented` attracted ZERO of 39 truly-supported spikes (0% [0.00,0.09],
     `combined` included) and caught 27/27 truly-absent ones, so the recorded 16
     invented (13.3%) needs NO correction. Every false positive was a `distorted`
     (5/39), so that label's 30% corrects to 24.4%. Sum ~38%, which is why the
     pooled corrections bracket it.
  3. ALL FIVE MISSES ARE FALSE POSITIVES, NONE FALSE NEGATIVES, and each was
     `['distorted','distorted']` across both byte-identical passes — systematic
     over-reading of compression and synthesis, not noise. 2 compressed (both
     self-contained) and 3 combined.
  4. THE SPIKED COMPOSITION DID NOT MOVE THE JUDGE: this run's real claims read
     30.6% (11/36) [0.18,0.47] against the recorded 52/120 [0.35,0.52]. The
     intervals OVERLAP, so the registered condition on transferring specificity
     back is not triggered.

ONE PREDICTION IN THE PRE-REGISTRATION MISSED: batches ran ~15, not the derived
~12, because real-claim yield was higher than the recorded per-rep sets (18/6/12
real claims per document). Position spread first 42% / middle 55% / last 51%; both
false positives came from `self-contained` (per-document specificity 100/80/100).

WHAT THIS DOES NOT ESTABLISH: one judge model, three ~1k-char documents, and a
single run. The verdict is that the instrument is fit to quote at this size, not
that 35-39% is the rate for any other corpus.

WHAT IS BEING VALIDATED, AND WHY IT MATTERS MORE THAN THE ARM QUESTION IT CAME FROM
==================================================================================
`probe_step2_isolate_ab.py` built `_support` as the confound-free replacement for a
paired judge that had failed three ways (set size, position, and how often it
shrugged). One arm's set, one source, one verdict per claim: `supported`,
`distorted` or `invented`. No second list to be longer than, no position to
prefer, and the output is a RATE rather than a preference.

It answered the arm question with a null (A 43.3% unsupported, C 45.7% — a 2.4pp
gap inside arm A's own 38pp rep-to-rep swing) and then produced something much
larger and arm-independent: **~44% of everything step 2 emits is not cleanly
supported by its own source** — 36 distorted and 16 invented of arm A's 120
claims, on the SHIPPED DEFAULT path. That file recorded it with an explicit
disclaimer, and the disclaimer is what this probe is for:

    "One judge, one prompt, unvalidated, and 'distorted' will be catching
     legitimate compression, so this is a lead and not a number to quote."

A 44% figure on the default extraction path is either a serious defect or a
serious measurement error, and nothing about the arm comparison distinguishes
them. Until the instrument has known-truth items run through it, the number
cannot be acted on OR dismissed.

THE FIRST THING FOUND, AND IT COST NOTHING: THE EVIDENCE WAS NOT KEPT
=====================================================================
The obvious cheap validation is to read the 52 claims the judge called
unsupported and see what they are. That is impossible. `probe_step2_isolate_ab.py`
computes `unsupported / len(verdicts)` and prints a rate; the claim texts and the
per-claim labels are never written anywhere. **The counter survived and the
evidence did not**, so the finding cannot be audited after the fact at any price
short of re-running it. That is the general lesson, and it is the same shape as
this bench's recurring "computed and never rendered" defect: an instrument that
emits a RATE must persist the per-item verdicts, or its output is unfalsifiable
by construction. This probe writes every claim, class, position and verdict to
`results/support_validation/`.

THE DESIGN: SPIKE-IN CONTROLS, JUDGED INSIDE REAL BATCHES
=========================================================
Homogeneous control sets would not transfer. `_support` batches a whole candidate
list into ONE call, so a claim is judged among its neighbours, and a set made
entirely of known-good items tells you what the judge does to a set made entirely
of known-good items. So the controls are SPIKED into real step-2 output, in the
same call, shuffled among it, in the same register and length band.

Seven classes, ground truth by construction. Supported:

  * `verbatim` — a source sentence copied, with a pronoun resolved at most. Truth
    is unarguable: the source states its own sentence. **This is the floor.**
  * `compressed` — a source sentence rewritten much shorter, meaning preserved.
    This is the class the recorded disclaimer is about, and it is what a real
    extracted thesis looks like.
  * `combined` — a correct join of two source sentences. Legitimate synthesis, and
    the most arguable class here, so it is REPORTED SEPARATELY and kept out of the
    primary. Its own question is whether the judge punishes inference.

Unsupported:

  * `flipped` — a source claim with its causal direction, beneficiary or arm
    reversed. Truth: distorted.
  * `inflated` — hedges removed, absolutes added, a conclusion the source does not
    draw. Truth: distorted.
  * `foreign` — a claim VERBATIM from one of the other two documents. Truth:
    invented for this source.
  * `fabricated` — a plausible claim about the source's own topic that the source
    never makes. Truth: invented.

**The strongest control in the set costs nothing extra: `foreign` spikes ARE the
other documents' `verbatim` spikes.** Every one of the 18 verbatim strings is
judged twice — once against the source that states it, once against a source that
does not — so the same 18 strings supply both a specificity and a sensitivity
measurement with the WORDING held exactly constant. A judge that answers
`supported` both times is reading the claim and not the source, and no argument
about how the spikes were written can explain that away.

PRE-REGISTERED — WRITTEN BEFORE ANY JUDGE CALL
==============================================
**Extraction arm.** Arm A, `extraction_step2_carries_source=True` — the shipped
default, because that is the path the 44% was measured on. Same three documents,
same `COUNT`, same weak tier for the work and strong tier for the judge, and
`_support` is IMPORTED rather than reimplemented: a validated copy of an
instrument validates nothing.

**Batches, sized off the original run's arithmetic rather than off an impression.**
`_support` is called once per (document, replicate) in `probe_step2_isolate_ab.py`,
and the recorded figure is 120 arm-A claims over 3 documents x `REPS = 4`, so the
batches behind the 44% held about **TEN** claims each. So: per document, all 28 of
its spikes plus that run's real claims, split into THREE batches (spikes stratified
by class, real claims dealt round-robin) and shuffled on a fixed seed, so a
surprising verdict is reproducible rather than re-rollable. That lands near 12 a
batch. Two batches would have been ~18 — nearly double the operating condition the
figure came from — and whether this judge's specificity holds as a list grows is
exactly the kind of assumption a validation is not allowed to smuggle in.

**What the spikes DO shift is composition, and the number is stated up front
because it is the largest limitation here.** Each batch is roughly 9 spikes to 3
real claims, and 45 of the 84 spikes are unsupported by construction, against a
recorded batch that was 100% real claims at whatever the true rate is. Registered
consequence, decided now rather than after seeing the result: if this run's
real-claim rate lands far from the recorded 43.3%, the specificity figure does NOT
transfer and every verdict below is reported as conditional on composition. The
alternative — extracting enough real claims to swamp 28 spikes — costs several more
extraction passes per document and still would not reach a realistic ratio, and
cutting the spike count instead would cost the precision that makes the primary
endpoint readable at all.

**Two identical passes.** The same batches, byte for byte, judged twice. This
measures the judge's STOCHASTICITY and deliberately not its order sensitivity —
the recorded finding rests on one pass, and its 38pp rep-to-rep swing was across
DIFFERENT claim sets, so same-set agreement has never been measured. Order
sensitivity shows up separately in the position check below.

**PRIMARY endpoints, on the binary the 44% actually counts** (`supported` against
everything else):

  * **specificity** = share of `verbatim` + `compressed` spikes called `supported`
    (n=30 by construction).
  * **sensitivity** = share of `flipped` + `inflated` + `foreign` + `fabricated`
    spikes called anything but `supported` (n=45).

**Registered verdicts.**

  * **FIT TO QUOTE** — specificity >= 0.90 AND sensitivity >= 0.70. The recorded
    ~44% stands within a few points and can be reported as a defect rate.
  * **INFLATED BY FALSE POSITIVES** — specificity <= 0.75. Most of the 44% is the
    instrument; the raw number is retired and only the corrected one may be
    quoted.
  * **BLIND** — sensitivity <= 0.50. The judge cannot see constructed distortion,
    so the label carries little information whatever the rate is; a rate from a
    blind instrument is not a smaller defect, it is no measurement.
  * **INDETERMINATE** — anything else, explicitly including the middle band
    0.75 < specificity < 0.90, which this n cannot resolve. Registered as a NULL
    band and not as "needs more data".

**VERBATIM FLOOR, a go/no-go that precedes all of it.** If specificity on
`verbatim` alone is below 0.90, the instrument does not recognise the source's own
sentences and there is nothing to correct — report that and stop. Any verdict
above is reported WITH this number beside it.

**THE COMPRESSION MECHANISM, registered separately** because it is the named
suspicion and it is a different claim from the pooled rate: if `compressed`
specificity is 15pp or more below `verbatim` specificity, "distorted is catching
legitimate compression" is CONFIRMED as the mechanism rather than assumed.

**THE CORRECTION.** With specificity and sensitivity measured, the observed rate
inverts to an estimate of the true one (Rogan-Gladen):

    true = (observed - (1 - specificity)) / (sensitivity - (1 - specificity))

Applied to the recorded 43.3% (52/120) and to this run's freshly measured real-
claim rate, with an interval propagated from the spike counts. If the denominator
is near zero the correction is undefined and that is REPORTED, not patched: an
instrument whose sensitivity barely exceeds its false-positive rate cannot be
corrected into a number.

**PRECISION, stated instead of a power figure, because there is no prior to size
against.** Nothing in this archive estimates this judge's specificity, so the
honest statement is what the design can discriminate rather than a power number
computed off a guess. At n=30 a Wilson interval is about +-0.10 wide at p=0.90 and
+-0.15 at p=0.75; at n=45 it is about +-0.13 at p=0.70. So the design separates
the ends and cannot resolve the middle — which is why the middle is pre-registered
as INDETERMINATE rather than argued about afterwards.

**CHECKS.**
  1. **Base-rate shift.** Spiking 28 items per document raises each batch's true
     unsupported share above what the original run judged. A judge sensitive to
     batch composition would move. Registered as a CAVEAT on transferring the
     specificity figure back to the unspiked 44%, not as a gate, and measured by
     comparing this run's real-claim rate with the recorded 43.3%.
  2. **Position within batch.** Verdict against index, reported. `_support` has no
     position control at all, unlike the paired judge.
  3. **Alignment refusals.** `_support` returns None when the model drops or
     merges entries. Every refusal is counted and named; a rate over a misaligned
     list is a made-up number.
  4. **Test-retest agreement** per item across the two passes, with 0.80 as the
     line below which every figure here is reported as provisional.

**LIMITS, stated before the result so they are not a reaction to it.**
  1. **The spikes are hand-written**, so "ground truth" is one person's
     construction for every class except `verbatim` and `foreign` — which is
     exactly why those two carry the floor and the same-string contrast.
  2. **Three documents, ~1k chars each.** Pooling assumes they are exchangeable;
     per-document rates are printed and their spread is the informal check. Real
     sources are far longer, and a support judge's job gets harder with distance.
  3. **This validates the JUDGE, not the extraction.** If the instrument comes out
     clean, the 44% is a real defect that still needs its own diagnosis; if it
     comes out inflated, the true rate could still be substantial.
  4. **One judge model** (`DEFAULT_TIER_STRONG`), the same one the finding used.
     That is the point — a different model would answer a different question — but
     it means nothing here separates "this judge" from "this prompt".
"""

from __future__ import annotations

import json
import math
import random
import statistics as st
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(E2E_DIR.parent))

from e2e.config import DEFAULT_TIER_STRONG, DEFAULT_TIER_WEAK  # noqa: E402
from e2e.modelctx import using_model  # noqa: E402
from e2e.probe_step2_isolate_ab import (  # noqa: E402
    DOCUMENTS,
    _candidates,
    _run_arm,
    _step1,
    _support,
)

RESULTS = E2E_DIR / "results"
#: A SUBDIRECTORY, for the same reason the placebo uses one: every archive-wide
#: reader globs `results/*.json` non-recursively, and this payload is not a run.
OUT_DIR = RESULTS / "support_validation"

#: The rate this probe exists to validate: arm A, run 3 of
#: `probe_step2_isolate_ab.py`, 52 of 120 claims not `supported`.
RECORDED_UNSUPPORTED = 52 / 120

SUPPORTED_CLASSES = ("verbatim", "compressed", "combined")
UNSUPPORTED_CLASSES = ("flipped", "inflated", "foreign", "fabricated")
#: `combined` is deliberately OUT of the primary: a correct join of two source
#: sentences is the one class whose ground truth a reasonable reader could dispute.
PRIMARY_SPECIFICITY_CLASSES = ("verbatim", "compressed")

SPECIFICITY_FIT = 0.90
SPECIFICITY_INFLATED = 0.75
SENSITIVITY_FIT = 0.70
SENSITIVITY_BLIND = 0.50
VERBATIM_FLOOR = 0.90
COMPRESSION_GAP = 0.15
RETEST_FLOOR = 0.80

#: Three, so a batch holds ~12 claims against the ~10 the recorded 43.3% was
#: measured on (120 arm-A claims / 3 documents / `REPS = 4`). Not a tuning knob:
#: raising it shrinks the batch below the operating condition, lowering it grows
#: the batch past it, and both make the specificity figure harder to transfer.
BATCHES_PER_DOCUMENT = 3
#: Both passes see byte-identical input, so disagreement is the judge's own
#: stochasticity and nothing else.
PASSES = 2

#: Hand-written spikes, one block per document. `foreign` is not listed: it is
#: built from the OTHER documents' `verbatim` entries, so the same 18 strings are
#: judged against a source that states them and a source that does not.
SPIKES: dict[str, dict[str, tuple[str, ...]]] = {
    "self-contained": {
        "verbatim": (
            "Concentrating release authority in one team makes the schedule "
            "predictable and makes every delay theirs alone.",
            "Distributing release authority removes the bottleneck and removes the "
            "person who can say the date is wrong.",
            "Documenting a process so it survives turnover freezes the version of "
            "it that was true when somebody wrote it down.",
            "Pricing per seat punishes a vendor for products that make each seat "
            "more capable.",
            "A long deprecation window keeps trust with the customers who cannot "
            "move and keeps the code that cannot be simplified.",
            "Measuring a team on throughput buries the work that does not "
            "decompose into countable units.",
        ),
        "compressed": (
            "Centralising release authority trades a bottleneck for accountability.",
            "Writing a process down makes it shareable and stale.",
            "Per-seat pricing penalises a vendor whose product works better.",
            "Throughput metrics reveal untracked work and hide indivisible work.",
        ),
        "combined": (
            "A long deprecation window and a documented process both preserve "
            "something past the point where it was true.",
            "Concentrating release authority and measuring throughput both make a "
            "team legible at the cost of what does not fit the measure.",
            "Each arrangement here buys one good by accepting the loss of its "
            "opposite.",
        ),
        "flipped": (
            "Concentrating release authority in one team removes the bottleneck "
            "and diffuses responsibility for delay.",
            "Documenting a process keeps it current, and leaving it in people's "
            "heads freezes it.",
            "Pricing per seat rewards a vendor for products that make each seat "
            "more capable.",
        ),
        "inflated": (
            "A long deprecation window always costs more trust than it keeps.",
            "Throughput is the only measure that hides work.",
            "Distributing release authority always destroys the schedule.",
        ),
        "fabricated": (
            "Release authority should rotate between teams each quarter so that no "
            "team becomes the bottleneck.",
            "Teams measured on throughput stop documenting their processes.",
            "Vendors who price per seat grow faster than vendors who price on "
            "usage.",
        ),
    },
    "narrative": {
        "verbatim": (
            "Mara inherited both halves of the platform group without inheriting "
            "the reason they were split.",
            "Mara kept the split arrangement for a quarter because unwinding it "
            "would have cost her the only two people who understood the older half.",
            "The August outage came from the seam between the halves, which nobody "
            "owned.",
            "The review found that everyone had assumed the other side was "
            "watching the seam.",
            "The lead who would have lost the title would have left, and the "
            "knowledge would have gone with him.",
            "Mara's director had been through the same choice at his last company "
            "and had merged, and he lost the person, and he still thinks it was "
            "right.",
        ),
        "compressed": (
            "Mara bought a stable quarter by leaving the split alone.",
            "Mara's reputation for not touching anything was the price of keeping "
            "two people.",
            "Merging would have cost the title of the one person who held the old "
            "knowledge.",
            "Mara cannot name what makes her situation different from her "
            "director's.",
        ),
        "combined": (
            "Protecting the knowledge held by one person is what left the seam "
            "between the halves unowned.",
            "Mara's director's advice rests on an outcome he counts as a success "
            "and she would count as a loss.",
            "The stable quarter and the August outage are the same decision seen "
            "at two different times.",
        ),
        "flipped": (
            "Mara merged the two halves of the platform group in April.",
            "The review found that the seam between the halves was watched by both "
            "sides.",
            "Mara's director had kept his two teams separate in the same situation "
            "and lost nobody.",
        ),
        "inflated": (
            "Mara always avoids any decision that would cost her a person.",
            "The August outage proves that splitting a platform group is a mistake.",
            "Every seam between two teams eventually causes an outage.",
        ),
        "fabricated": (
            "Mara's group missed its quarterly targets after the August outage.",
            "The two halves of the platform group used different deployment "
            "tooling.",
            "Mara hired a third lead to own the seam between the halves.",
        ),
    },
    "technical": {
        "verbatim": (
            "A digest is the system's standing understanding of a source, "
            "rewritten whenever a new intent arrives.",
            "Every later stage reads the digest instead of the raw bytes.",
            "Sources larger than one prompt are read in overlapping windows, each "
            "digested on its own and then reduced into one.",
            "A digest that describes the first few pages while presenting itself "
            "as the understanding of the whole source is a lie nothing downstream "
            "can detect.",
            "Extraction does not go through the digest; it sweeps the windows "
            "directly.",
            "The sweep is capped at three concurrent windows, lower than the "
            "digest's eight.",
        ),
        "compressed": (
            "Coverage is a guarantee for digests rather than best effort.",
            "Extraction has no query, so retrieval against the stated intent would "
            "miss whatever nobody thought to ask about.",
            "Each window fans out to one call per requested candidate plus two.",
            "The sweep's concurrency cap is lower than the digest's because each "
            "window is itself a fan-out.",
        ),
        "combined": (
            "The digest is the system's memory of a source, and extraction "
            "deliberately does not use it.",
            "Both the digest's coverage guarantee and extraction's direct sweep "
            "exist because a partial reading is undetectable downstream.",
            "In-flight calls are roughly the sweep's cap times six.",
        ),
        "flipped": (
            "Extraction goes through the digest rather than sweeping the windows "
            "directly.",
            "Every later stage reads the raw bytes rather than the digest.",
            "The sweep is capped at eight concurrent windows, higher than the "
            "digest's three.",
        ),
        "inflated": (
            "A digest is always an accurate summary of the whole source.",
            "Retrieval against a stated intent returns nothing useful.",
            "Every source is read in overlapping windows.",
        ),
        "fabricated": (
            "Digests are cached for twenty-four hours before being rebuilt.",
            "The overlapping windows are sized to the model's context limit minus "
            "the system prompt.",
            "The reduce step re-reads the original source to check the combined "
            "digest.",
        ),
    },
}


@dataclass
class Item:
    """One judged line: a real claim or a spike with known truth."""

    text: str
    #: Class name for a spike, or "real" for actual step-2 output.
    cls: str
    document: str
    batch: int
    position: int = -1
    verdicts: list[str] = field(default_factory=list)

    @property
    def is_spike(self) -> bool:
        return self.cls != "real"

    @property
    def truth_supported(self) -> bool | None:
        if self.cls in SUPPORTED_CLASSES:
            return True
        if self.cls in UNSUPPORTED_CLASSES:
            return False
        return None

    def called_supported(self, pass_index: int = 0) -> bool | None:
        if pass_index >= len(self.verdicts):
            return None
        return self.verdicts[pass_index] == "supported"


def foreign_for(document: str) -> tuple[str, ...]:
    """The other documents' `verbatim` spikes, 3 from each.

    Deterministic and exhaustive: every one of the 18 verbatim strings is used as
    a `foreign` spike for exactly one other document, so the same string is judged
    against a source that states it and a source that does not. That contrast is
    the one measurement here that no argument about how the spikes were written
    can explain away.
    """
    names = list(SPIKES)
    index = names.index(document)
    out: list[str] = []
    for offset in (1, 2):
        donor = names[(index + offset) % len(names)]
        verbatim = SPIKES[donor]["verbatim"]
        # The donor's 6 split 3/3 between its two neighbours, by the donor's own
        # view of who comes first.
        half = len(verbatim) // 2
        donor_index = names.index(donor)
        first_neighbour = names[(donor_index + 1) % len(names)]
        chunk = verbatim[:half] if document == first_neighbour else verbatim[half:]
        out.extend(chunk)
    return tuple(out)


def spikes_for(document: str) -> list[tuple[str, str]]:
    """[(class, text)] for one document, in a fixed order."""
    out: list[tuple[str, str]] = []
    for cls in ("verbatim", "compressed", "combined", "flipped", "inflated",
                "fabricated"):
        out.extend((cls, text) for text in SPIKES[document][cls])
    out.extend(("foreign", text) for text in foreign_for(document))
    return out


def build_batches(document: str, real: list[str], seed: str) -> list[list[Item]]:
    """`BATCHES_PER_DOCUMENT` batches: spikes stratified by class, real dealt round.

    Stratified per class rather than over the whole spike list, so every class is
    present in every batch and one batch failing alignment cannot delete a whole
    control class. Shuffled on a fixed seed so a surprising verdict is reproducible
    rather than re-rollable — the same rule `_trimmed` follows in the probe this
    validates.
    """
    batches: list[list[Item]] = [[] for _ in range(BATCHES_PER_DOCUMENT)]
    per_class: dict[str, int] = {}
    for cls, text in spikes_for(document):
        seen = per_class.get(cls, 0)
        per_class[cls] = seen + 1
        which = seen % BATCHES_PER_DOCUMENT
        batches[which].append(Item(text=text, cls=cls, document=document, batch=which))
    for index, text in enumerate(real):
        which = index % BATCHES_PER_DOCUMENT
        batches[which].append(
            Item(text=text, cls="real", document=document, batch=which)
        )
    for which, batch in enumerate(batches):
        random.Random(f"{seed}|{document}|{which}").shuffle(batch)
        for position, item in enumerate(batch):
            item.position = position
    return batches


# --- statistics (free) --------------------------------------------------------


def wilson(successes: int, total: int) -> tuple[float, float, float]:
    """(point, lo, hi) at 95%. Wilson rather than normal: these are proportions
    near 1.0 on tens of items, where the normal interval runs past 1 and gets
    quietly clipped."""
    if total == 0:
        return float("nan"), float("nan"), float("nan")
    z = 1.96
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    half = (
        z
        * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
        / denominator
    )
    return p, max(0.0, centre - half), min(1.0, centre + half)


def rogan_gladen(
    observed: float, specificity: float, sensitivity: float
) -> float | None:
    """The observed rate corrected for a known-imperfect instrument, or None.

    None when the denominator is at or below zero — a judge whose sensitivity does
    not exceed its false-positive rate carries no information, and dividing by
    that produces a number with a sign but no meaning.
    """
    false_positive = 1 - specificity
    denominator = sensitivity - false_positive
    if denominator <= 0.05:
        return None
    return (observed - false_positive) / denominator


def _rate(items: list[Item], predicate) -> tuple[int, int]:
    hits = total = 0
    for item in items:
        called = item.called_supported()
        if called is None:
            continue
        total += 1
        hits += predicate(item, called)
    return hits, total


def specificity_of(items: list[Item], classes: tuple[str, ...]) -> tuple[int, int]:
    chosen = [i for i in items if i.cls in classes]
    return _rate(chosen, lambda item, called: called)


def sensitivity_of(items: list[Item], classes: tuple[str, ...]) -> tuple[int, int]:
    chosen = [i for i in items if i.cls in classes]
    return _rate(chosen, lambda item, called: not called)


def retest_agreement(items: list[Item]) -> tuple[int, int]:
    """Per-item agreement on the reported binary across the two identical passes."""
    agree = total = 0
    for item in items:
        if len(item.verdicts) < 2:
            continue
        total += 1
        agree += (item.verdicts[0] == "supported") == (item.verdicts[1] == "supported")
    return agree, total


def verdict(
    specificity: float, sensitivity: float, verbatim_specificity: float
) -> tuple[str, list[str]]:
    """The registered decision. Pure, so a test can hold the bars in place."""
    reasons: list[str] = []
    if verbatim_specificity < VERBATIM_FLOOR:
        reasons.append(
            f"verbatim specificity {verbatim_specificity:.0%} is below the "
            f"{VERBATIM_FLOOR:.0%} floor — the judge does not reliably recognise "
            "the source's own sentences, so there is nothing here to correct"
        )
        return "BROKEN (verbatim floor failed)", reasons
    if sensitivity <= SENSITIVITY_BLIND:
        reasons.append(
            f"sensitivity {sensitivity:.0%} at or below {SENSITIVITY_BLIND:.0%} — "
            "constructed distortion is not detected, so the rate is not a smaller "
            "measurement but no measurement"
        )
        return "BLIND", reasons
    if specificity <= SPECIFICITY_INFLATED:
        reasons.append(
            f"specificity {specificity:.0%} at or below {SPECIFICITY_INFLATED:.0%} "
            "— supported claims are being called unsupported often enough to be "
            "most of the recorded rate"
        )
        return "INFLATED BY FALSE POSITIVES", reasons
    if specificity >= SPECIFICITY_FIT and sensitivity >= SENSITIVITY_FIT:
        reasons.append(
            f"specificity {specificity:.0%} >= {SPECIFICITY_FIT:.0%} and "
            f"sensitivity {sensitivity:.0%} >= {SENSITIVITY_FIT:.0%}"
        )
        return "FIT TO QUOTE", reasons
    reasons.append(
        f"specificity {specificity:.0%} and sensitivity {sensitivity:.0%} fall in "
        "the registered null band — this n cannot separate a usable instrument "
        "from an inflated one"
    )
    return "INDETERMINATE", reasons


# --- persistence --------------------------------------------------------------


def save(items: list[Item], *, judge_model: str, refusals: list[str]) -> Path:
    from e2e.report import build_provenance

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "spike_in.json"
    path.write_text(
        json.dumps(
            {
                "judge_model": judge_model,
                "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "build": build_provenance(),
                "recorded_unsupported": RECORDED_UNSUPPORTED,
                "refusals": refusals,
                # Every claim, its class, where it sat and what it was called —
                # the thing the original run did not keep.
                "items": [
                    {
                        "text": i.text,
                        "cls": i.cls,
                        "document": i.document,
                        "batch": i.batch,
                        "position": i.position,
                        "verdicts": i.verdicts,
                    }
                    for i in items
                ],
            },
            indent=2,
        )
    )
    return path


def load() -> tuple[list[Item], dict]:
    payload = json.loads((OUT_DIR / "spike_in.json").read_text())
    items = []
    for row in payload["items"]:
        item = Item(
            text=row["text"],
            cls=row["cls"],
            document=row["document"],
            batch=row["batch"],
            position=row["position"],
        )
        item.verdicts = list(row["verdicts"])
        items.append(item)
    return items, payload


# --- the judged lane ----------------------------------------------------------


async def run(di_container, seed: str = "support-validity-1") -> tuple[list[Item], list[str]]:
    """Extract with arm A, spike, judge every batch twice. Fills and returns items."""
    all_items: list[Item] = []
    refusals: list[str] = []
    for name, document in DOCUMENTS.items():
        with using_model(di_container, DEFAULT_TIER_WEAK):
            concern, content = await _step1(document)
        if not content:
            refusals.append(f"{name}: step 1 found no content items")
            continue
        checks = await _run_arm("A", di_container, concern, content)
        real = _candidates(checks)
        batches = build_batches(name, real, seed)
        sizes = " + ".join(str(len(b)) for b in batches)
        print(
            f"  {name}: {len(content)} content item(s) -> {len(real)} real claims; "
            f"batches {sizes}",
            flush=True,
        )
        for batch in batches:
            texts = [i.text for i in batch]
            for pass_index in range(PASSES):
                # Byte-identical input on both passes: this measures the judge's
                # stochasticity, not its order sensitivity.
                got = await _support(di_container, document, texts)
                if got is None:
                    refusals.append(
                        f"{name} batch {batch[0].batch} pass {pass_index + 1}: "
                        f"misaligned verdict list over {len(texts)} claims"
                    )
                    continue
                for item, one in zip(batch, got):
                    item.verdicts.append(one)
            all_items.extend(batch)
    return all_items, refusals


# --- printing -----------------------------------------------------------------


def print_plan() -> int:
    print("=" * 78)
    print("SUPPORT-JUDGE VALIDATION — the plan (free, no calls)")
    print("=" * 78)
    counts: dict[str, int] = {}
    for name in DOCUMENTS:
        for cls, _ in spikes_for(name):
            counts[cls] = counts.get(cls, 0) + 1
    print(f"  {'class':14} {'n':>4}  truth")
    for cls in SUPPORTED_CLASSES + UNSUPPORTED_CLASSES:
        truth = "supported" if cls in SUPPORTED_CLASSES else "NOT supported"
        star = "  <- primary" if cls in PRIMARY_SPECIFICITY_CLASSES else ""
        print(f"  {cls:14} {counts.get(cls, 0):4d}  {truth}{star}")
    spec_n = sum(counts.get(c, 0) for c in PRIMARY_SPECIFICITY_CLASSES)
    sens_n = sum(counts.get(c, 0) for c in UNSUPPORTED_CLASSES)
    print(f"\n  specificity n={spec_n}, sensitivity n={sens_n}, "
          f"judge calls {len(DOCUMENTS)} docs x {BATCHES_PER_DOCUMENT} batches x "
          f"{PASSES} passes = {len(DOCUMENTS) * BATCHES_PER_DOCUMENT * PASSES}")
    per_batch = sum(counts.values()) / (len(DOCUMENTS) * BATCHES_PER_DOCUMENT)
    print(f"  ~{per_batch:.0f} spikes a batch, against the ~10 real claims a batch "
          "the recorded 43.3% was measured on")
    print("\n  What this n can discriminate (Wilson, 95%):")
    for label, total in (("specificity", spec_n), ("sensitivity", sens_n)):
        for true_p in (0.95, 0.90, 0.75, 0.60):
            point, lo, hi = wilson(round(true_p * total), total)
            print(f"    {label:12} at {true_p:.0%}: [{lo:.2f},{hi:.2f}] "
                  f"half-width +-{(hi - lo) / 2:.2f}")
    print("\n  The same-string contrast — every verbatim spike is also a foreign")
    print("  spike for another document, so wording is held exactly constant:")
    for name in DOCUMENTS:
        print(f"    {name:16} receives {len(foreign_for(name))} foreign, "
              f"donates {len(SPIKES[name]['verbatim'])} verbatim")
    used = [text for name in DOCUMENTS for text in foreign_for(name)]
    donated = [t for name in DOCUMENTS for t in SPIKES[name]["verbatim"]]
    print(f"    {len(used)} foreign slots over {len(donated)} verbatim strings, "
          f"each used {'exactly once' if sorted(used) == sorted(donated) else 'UNEVENLY'}")
    return 0


def print_read() -> int:
    try:
        items, payload = load()
    except FileNotFoundError:
        print(f"not run yet — {OUT_DIR / 'spike_in.json'} does not exist")
        return 1
    spikes = [i for i in items if i.is_spike]
    real = [i for i in items if not i.is_spike]

    print("=" * 78)
    print(f"SUPPORT-JUDGE VALIDATION — judge {payload.get('judge_model', '?')}")
    print("=" * 78)
    for refusal in payload.get("refusals") or []:
        print(f"  REFUSED: {refusal}")
    print(f"  {len(spikes)} spikes and {len(real)} real claims over "
          f"{len({i.document for i in items})} documents")

    print()
    print("  PER CLASS — 'as truth' is the share the judge got right")
    print(f"  {'class':14} {'n':>4} {'supported':>10} {'as truth':>9}  95% CI")
    for cls in SUPPORTED_CLASSES + UNSUPPORTED_CLASSES:
        chosen = [i for i in spikes if i.cls == cls]
        if not chosen:
            continue
        called, total = _rate(chosen, lambda item, called: called)
        right = called if cls in SUPPORTED_CLASSES else total - called
        point, lo, hi = wilson(right, total)
        print(f"  {cls:14} {total:4d} {called:10d} {point:9.0%}  [{lo:.2f},{hi:.2f}]")

    spec_hits, spec_n = specificity_of(spikes, PRIMARY_SPECIFICITY_CLASSES)
    sens_hits, sens_n = sensitivity_of(spikes, UNSUPPORTED_CLASSES)
    verbatim_hits, verbatim_n = specificity_of(spikes, ("verbatim",))
    compressed_hits, compressed_n = specificity_of(spikes, ("compressed",))
    specificity, spec_lo, spec_hi = wilson(spec_hits, spec_n)
    sensitivity, sens_lo, sens_hi = wilson(sens_hits, sens_n)
    verbatim_specificity = verbatim_hits / verbatim_n if verbatim_n else float("nan")
    compressed_specificity = (
        compressed_hits / compressed_n if compressed_n else float("nan")
    )

    print()
    print("  PRIMARY")
    print(f"    specificity  {specificity:.0%} ({spec_hits}/{spec_n}) "
          f"[{spec_lo:.2f},{spec_hi:.2f}]   bars: fit >= {SPECIFICITY_FIT:.0%}, "
          f"inflated <= {SPECIFICITY_INFLATED:.0%}")
    print(f"    sensitivity  {sensitivity:.0%} ({sens_hits}/{sens_n}) "
          f"[{sens_lo:.2f},{sens_hi:.2f}]   bars: fit >= {SENSITIVITY_FIT:.0%}, "
          f"blind <= {SENSITIVITY_BLIND:.0%}")
    print(f"    VERBATIM FLOOR {verbatim_specificity:.0%} "
          f"({verbatim_hits}/{verbatim_n}) against {VERBATIM_FLOOR:.0%}")
    label, reasons = verdict(specificity, sensitivity, verbatim_specificity)
    print()
    print(f"  REGISTERED VERDICT: {label}")
    for reason in reasons:
        print(f"    - {reason}")

    gap = verbatim_specificity - compressed_specificity
    print()
    print("  THE COMPRESSION MECHANISM (the named suspicion, registered separately)")
    print(f"    verbatim {verbatim_specificity:.0%} - compressed "
          f"{compressed_specificity:.0%} = {gap:+.0%} against a "
          f"{COMPRESSION_GAP:.0%} bar -> "
          f"{'CONFIRMED as the mechanism' if gap >= COMPRESSION_GAP else 'not confirmed'}")
    combined_hits, combined_n = specificity_of(spikes, ("combined",))
    if combined_n:
        print(f"    legitimate synthesis (`combined`, out of the primary): "
              f"{combined_hits / combined_n:.0%} called supported "
              f"({combined_hits}/{combined_n})")

    print()
    print("  THE SAME-STRING CONTRAST — identical wording, one source states it")
    print("  and the other does not, so nothing about how it was written can differ")
    own = [i for i in spikes if i.cls == "verbatim"]
    away = [i for i in spikes if i.cls == "foreign"]
    own_called, own_total = _rate(own, lambda item, called: called)
    away_called, away_total = _rate(away, lambda item, called: called)
    print(f"    against its OWN source:     {own_called}/{own_total} supported "
          f"({own_called / own_total:.0%})" if own_total else "    no verbatim rows")
    print(f"    against a FOREIGN source:   {away_called}/{away_total} supported "
          f"({away_called / away_total:.0%})" if away_total else "    no foreign rows")
    if own_total and away_total:
        print(f"    separation {own_called / own_total - away_called / away_total:+.0%}"
              " — this is the judge reading the SOURCE rather than the claim")

    print()
    print("  THE CORRECTION (Rogan-Gladen, on the binary the 44% counts)")
    real_hits, real_total = _rate(real, lambda item, called: not called)
    fresh = real_hits / real_total if real_total else float("nan")
    for name, observed in (
        (f"recorded 2026-09-17 ({RECORDED_UNSUPPORTED:.1%})", RECORDED_UNSUPPORTED),
        (f"this run, real claims ({fresh:.1%})", fresh),
    ):
        corrected = rogan_gladen(observed, specificity, sensitivity)
        if corrected is None:
            print(f"    {name:34} -> UNDEFINED: sensitivity does not exceed the "
                  "false-positive rate by enough to invert")
        else:
            low = rogan_gladen(observed, spec_hi, sens_lo)
            high = rogan_gladen(observed, spec_lo, sens_hi)
            span = [v for v in (low, high) if v is not None]
            band = (f"  [{min(span):.1%},{max(span):.1%}] across the spike CIs"
                    if len(span) == 2 else "  (one bound undefined)")
            print(f"    {name:34} -> {max(0.0, min(1.0, corrected)):.1%}{band}")

    print()
    print("  WHICH LABEL, NOT JUST WHETHER — the recorded finding splits its 52 into")
    print("  36 `distorted` and 16 `invented`, and those two are not equally safe")
    labels = ("supported", "distorted", "invented")
    print(f"    {'class':14} {'n':>4} " + " ".join(f"{l:>10}" for l in labels))
    for cls in SUPPORTED_CLASSES + UNSUPPORTED_CLASSES + ("real",):
        chosen = [i for i in items if i.cls == cls and i.verdicts]
        if not chosen:
            continue
        row = [sum(1 for i in chosen if i.verdicts[0] == l) for l in labels]
        print(f"    {cls:14} {len(chosen):4d} " + " ".join(f"{v:>10}" for v in row))
    # The false-positive rate of each LABEL over the claims that are truly
    # supported. A label nothing supported ever attracts can be quoted on its own
    # even when the pooled figure cannot.
    truly = [i for i in spikes if i.truth_supported and i.verdicts]
    for label in ("distorted", "invented"):
        hits = sum(1 for i in truly if i.verdicts[0] == label)
        point, lo, hi = wilson(hits, len(truly))
        print(f"    `{label}` claimed on {hits}/{len(truly)} truly-supported spikes "
              f"= {point:.0%} [{lo:.2f},{hi:.2f}]")

    # Each label is its own instrument, so each gets its own correction. This is
    # the reading that survives the `combined` argument below, because it does not
    # depend on which supported classes are pooled: `invented` attracted NO
    # supported spike of ANY class, so its false-positive rate is 0/39 either way.
    absent = [i for i in spikes if i.cls in ("foreign", "fabricated") and i.verdicts]
    bent = [i for i in spikes if i.cls in ("flipped", "inflated") and i.verdicts]
    print()
    print("  EACH LABEL CORRECTED ON ITS OWN — the actionable split")
    print("  `invented` and `distorted` are not one instrument, so the recorded")
    print("  36 + 16 does not correct as one number")
    n_sup = len(truly)
    for label, target, recorded in (
        ("invented", absent, 16 / 120),
        ("distorted", bent, 36 / 120),
    ):
        fp = sum(1 for i in truly if i.verdicts[0] == label)
        tp = sum(1 for i in target if i.verdicts[0] == label)
        spec = 1.0 - fp / n_sup
        sens = tp / len(target)
        corrected = rogan_gladen(recorded, spec, sens)
        shown = "refuses" if corrected is None else f"{corrected:.1%}"
        print(f"    `{label}`  specificity {spec:.0%} ({n_sup - fp}/{n_sup}), "
              f"sensitivity {sens:.0%} ({tp}/{len(target)})")
        print(f"      recorded {recorded:.1%} -> {shown}")

    print()
    print("  IF `combined` COUNTED — the pre-registered exclusion, priced")
    print("  Real extracted theses often ARE joins of two source sentences, so the")
    print("  registered primary is arguably the optimistic reading of the same data.")
    wide_hits, wide_n = specificity_of(spikes, SUPPORTED_CLASSES)
    wide, wide_lo, wide_hi = wilson(wide_hits, wide_n)
    wide_label = verdict(wide, sensitivity, verbatim_specificity)[0]
    print(f"    specificity over all three supported classes: {wide:.0%} "
          f"({wide_hits}/{wide_n}) [{wide_lo:.2f},{wide_hi:.2f}] -> would read "
          f"{wide_label}")
    wide_corrected = rogan_gladen(RECORDED_UNSUPPORTED, wide, sensitivity)
    if wide_corrected is not None:
        print(f"    the recorded {RECORDED_UNSUPPORTED:.1%} would correct to "
              f"{max(0.0, min(1.0, wide_corrected)):.1%} instead")

    print()
    print("  THE CLAIMS THE JUDGE GOT WRONG — the audit trail the original run")
    print("  did not keep, which is why this file persists every verdict")
    wrong = [
        i for i in spikes
        if i.called_supported() is not None
        and i.called_supported() != i.truth_supported
    ]
    if not wrong:
        print("    none")
    for item in wrong:
        direction = "called UNSUPPORTED, truth supported"
        if item.truth_supported is False:
            direction = "called supported, truth NOT supported"
        print(f"    [{item.cls}/{item.document}] {direction}")
        print(f"      verdicts {item.verdicts} — {item.text}")

    print()
    print("  CHECKS")
    fresh_point, fresh_lo, fresh_hi = wilson(real_hits, real_total)
    rec_point, rec_lo, rec_hi = wilson(52, 120)
    overlap = fresh_hi >= rec_lo and rec_hi >= fresh_lo
    print(f"    base-rate shift: this run's real claims read {fresh:.1%} unsupported "
          f"({real_hits}/{real_total}) [{fresh_lo:.2f},{fresh_hi:.2f}] against the "
          f"recorded {RECORDED_UNSUPPORTED:.1%} (52/120) [{rec_lo:.2f},{rec_hi:.2f}]")
    if overlap:
        print("      the two intervals OVERLAP, so the spiked composition did not "
              "measurably move the judge and the registered condition on "
              "transferring specificity back is NOT triggered")
    else:
        print("      the two intervals are DISJOINT — the registered condition "
              "fires: every figure above is conditional on composition")
    agree, agree_total = retest_agreement(items)
    if agree_total:
        share = agree / agree_total
        print(f"    test-retest: {share:.0%} per-item agreement over {agree_total} "
              f"items across two identical passes — "
              f"{'usable' if share >= RETEST_FLOOR else f'BELOW the {RETEST_FLOOR:.0%} line, every figure above is provisional'}")
        flipped_items = [
            i for i in items
            if len(i.verdicts) >= 2
            and (i.verdicts[0] == "supported") != (i.verdicts[1] == "supported")
        ]
        for item in flipped_items:
            print(f"      flipped {item.verdicts} [{item.cls}] {item.text[:66]}")
    thirds: dict[str, list[float]] = {}
    for item in items:
        called = item.called_supported()
        if called is None:
            continue
        batch_size = max(
            (i.position for i in items if i.document == item.document and i.batch == item.batch),
            default=0,
        ) + 1
        third = ("first", "middle", "last")[min(2, item.position * 3 // max(1, batch_size))]
        thirds.setdefault(third, []).append(1.0 if called else 0.0)
    print("    position within batch (`_support` has no position control at all):")
    for third in ("first", "middle", "last"):
        values = thirds.get(third) or []
        if values:
            print(f"      {third:7} n={len(values):3d} supported {st.fmean(values):.0%}")

    print()
    print("  PER DOCUMENT (pooling assumes three ~1k-char documents are exchangeable)")
    print(f"    {'document':16} {'spec':>6} {'sens':>6} {'real unsupported':>17}")
    for name in sorted({i.document for i in items}):
        doc_spikes = [i for i in spikes if i.document == name]
        doc_real = [i for i in real if i.document == name]
        s_hits, s_n = specificity_of(doc_spikes, PRIMARY_SPECIFICITY_CLASSES)
        n_hits, n_n = sensitivity_of(doc_spikes, UNSUPPORTED_CLASSES)
        r_hits, r_n = _rate(doc_real, lambda item, called: not called)
        print(f"    {name:16} {s_hits / s_n if s_n else float('nan'):6.0%} "
              f"{n_hits / n_n if n_n else float('nan'):6.0%} "
              f"{r_hits / r_n if r_n else float('nan'):16.0%} ({r_hits}/{r_n})")
    return 0


def main(argv: list[str]) -> int:
    if "--read" in argv:
        return print_read()
    return print_plan()


class TestThePreRegistrationIsAuditable:
    """Free guards. Re-collected into the default suite by subclassing in
    `test_e2e.py` — no `probe_*.py` is collected under pytest's `test_*.py`
    pattern."""

    def test_the_spike_counts_are_what_the_docstring_registers(self):
        counts: dict[str, int] = {}
        for name in DOCUMENTS:
            for cls, _ in spikes_for(name):
                counts[cls] = counts.get(cls, 0) + 1
        assert counts == {
            "verbatim": 18, "compressed": 12, "combined": 9,
            "flipped": 9, "inflated": 9, "fabricated": 9, "foreign": 18,
        }
        assert sum(counts[c] for c in PRIMARY_SPECIFICITY_CLASSES) == 30
        assert sum(counts[c] for c in UNSUPPORTED_CLASSES) == 45
        # Every class needs at least one spike per batch per document, or a batch
        # that fails alignment deletes a whole control class. This is what forced
        # `inflated` and `fabricated` to three apiece when the batch count went
        # from two to three.
        for name in DOCUMENTS:
            per_class: dict[str, int] = {}
            for cls, _ in spikes_for(name):
                per_class[cls] = per_class.get(cls, 0) + 1
            for cls, total in per_class.items():
                assert total >= BATCHES_PER_DOCUMENT, f"{name}/{cls}: {total}"

    def test_every_verbatim_string_is_also_a_foreign_spike_exactly_once(self):
        """The same-string contrast is the one control no argument about how the
        spikes were written can explain away, so it has to be exhaustive."""
        donated = sorted(t for name in DOCUMENTS for t in SPIKES[name]["verbatim"])
        used = sorted(t for name in DOCUMENTS for t in foreign_for(name))
        assert used == donated
        # And never against its own source, which would make it supported.
        for name in DOCUMENTS:
            assert not set(foreign_for(name)) & set(SPIKES[name]["verbatim"])

    def test_spikes_are_verbatim_substrings_where_they_claim_to_be(self):
        """`verbatim` carries the floor, so it must actually be in the source.

        Checked on the distinctive content words rather than the whole string,
        because a resolved pronoun is allowed ("distributing it" -> "distributing
        release authority") and a sentence split at a semicolon is too. A trailing
        `'s` comes off for the same reason: "her director" -> "Mara's director" is
        the possessive form of exactly that allowed resolution, and the name it
        resolves to still has to be in the source.
        """
        stop = {
            "the", "a", "an", "and", "or", "of", "to", "in", "is", "it", "its",
            "that", "this", "for", "so", "as", "at", "on", "by", "was", "were",
            "be", "been", "with", "from", "who", "which", "what", "than", "then",
            "not", "no", "but", "every", "each", "one", "two", "her", "his",
            "she", "he", "they", "them", "their", "there", "have", "has", "had",
            "would", "will", "does", "do", "did", "are", "am",
        }
        for name, document in DOCUMENTS.items():
            haystack = document.lower()
            for text in SPIKES[name]["verbatim"]:
                words = [
                    w.strip(".,;:'\"").removesuffix("'s")
                    for w in text.lower().split()
                    if w.strip(".,;:'\"") not in stop and len(w) > 3
                ]
                missing = [w for w in words if w not in haystack]
                assert not missing, f"{name}: {missing} not in source for {text!r}"

    def test_foreign_spikes_are_absent_from_the_source_they_are_judged_against(self):
        """A `foreign` spike that happens to restate the target source would be a
        false positive counted as a hit."""
        for name, document in DOCUMENTS.items():
            haystack = document.lower()
            for text in foreign_for(name):
                shared = [
                    w for w in {
                        x.strip(".,;:'\"") for x in text.lower().split() if len(x) > 6
                    }
                    if w in haystack
                ]
                # Some long words are generic across these documents ("process");
                # what must not happen is most of the content overlapping.
                distinctive = {
                    x.strip(".,;:'\"") for x in text.lower().split() if len(x) > 6
                }
                assert len(shared) <= len(distinctive) / 2, (
                    f"{name}: foreign spike overlaps the source: {text!r} ({shared})"
                )

    def test_batches_are_deterministic_and_position_blind(self):
        real = [f"real claim {i}" for i in range(12)]
        batches = build_batches("narrative", real, "seed-1")
        again = build_batches("narrative", real, "seed-1")
        assert len(batches) == BATCHES_PER_DOCUMENT
        for batch, repeat in zip(batches, again):
            assert [i.text for i in batch] == [i.text for i in repeat]
        for batch in batches:
            # Spikes must be spread through the batch, not clustered at either
            # end: `_support` has no position control, so a block of controls at
            # the top would make position and class the same variable.
            spike_positions = [i.position for i in batch if i.is_spike]
            assert min(spike_positions) < len(batch) / 3
            assert max(spike_positions) > 2 * len(batch) / 3
            # Every class in every batch, so one batch failing alignment cannot
            # delete a whole control class.
            assert {i.cls for i in batch if i.is_spike} == set(
                SUPPORTED_CLASSES + UNSUPPORTED_CLASSES
            )
        # Nothing lost or duplicated in the split.
        placed = [i for batch in batches for i in batch]
        assert sorted(i.text for i in placed if i.is_spike) == sorted(
            text for _, text in spikes_for("narrative")
        )
        assert sorted(i.text for i in placed if not i.is_spike) == sorted(real)

    def test_a_batch_holds_about_what_the_recorded_figure_was_measured_on(self):
        """The batch size is the operating condition, so it is pinned, not tuned.

        120 arm-A claims over 3 documents x `REPS = 4` in
        `probe_step2_isolate_ab.py` is ~10 a call; two batches here would have been
        ~18, which is why there are three.
        """
        real = [f"real claim {i}" for i in range(10)]
        for name in DOCUMENTS:
            for batch in build_batches(name, real, "seed-1"):
                assert 9 <= len(batch) <= 15, f"{name}: batch of {len(batch)}"

    def test_registered_bars_cannot_drift(self):
        assert verdict(0.95, 0.85, 1.00)[0] == "FIT TO QUOTE"
        assert verdict(0.70, 0.85, 1.00)[0] == "INFLATED BY FALSE POSITIVES"
        assert verdict(0.95, 0.40, 1.00)[0] == "BLIND"
        # The middle band is a registered NULL, not a request for more data.
        assert verdict(0.83, 0.85, 1.00)[0] == "INDETERMINATE"
        assert verdict(0.95, 0.60, 1.00)[0] == "INDETERMINATE"
        # The floor precedes everything, including a flattering pooled figure.
        assert verdict(0.95, 0.85, 0.80)[0] == "BROKEN (verbatim floor failed)"
        # Blindness is checked before inflation: a judge that detects nothing
        # cannot be described as over-detecting.
        assert verdict(0.60, 0.30, 1.00)[0] == "BLIND"

    def test_the_correction_refuses_rather_than_returning_a_sign(self):
        assert rogan_gladen(0.433, 1.0, 1.0) == pytest.approx(0.433)
        # A perfect-sensitivity, 20%-false-positive judge reading 43.3% implies a
        # true rate well below it.
        assert rogan_gladen(0.433, 0.80, 1.0) == pytest.approx(0.291, abs=0.001)
        # Sensitivity barely above the false-positive rate: undefined, not huge.
        assert rogan_gladen(0.433, 0.60, 0.42) is None
        assert rogan_gladen(0.433, 0.50, 0.50) is None

    def test_output_stays_out_of_every_archive_sweep(self):
        assert OUT_DIR.parent == RESULTS
        assert (OUT_DIR / "spike_in.json") not in set(RESULTS.glob("*.json"))

    def test_the_instrument_is_imported_and_not_reimplemented(self):
        """Validating a copy validates nothing."""
        import e2e.probe_step2_isolate_ab as source

        assert _support is source._support
        assert _run_arm is source._run_arm

    def test_the_recorded_result_is_what_the_docstrings_quote(self):
        """The RESULT block, CLAUDE.md and two READMEs all quote 93% / 100%.

        Four files now carry those figures and none of them can notice when the
        persisted verdicts stop agreeing with them. SKIPS rather than fails when
        the archive is absent, because `results/` is gitignored — in a fresh
        checkout there is nothing to check, which is not the same as a mismatch.
        """
        if not (OUT_DIR / "spike_in.json").exists():
            pytest.skip("no archived run in this checkout (results/ is gitignored)")
        items, _ = load()

        spikes = [i for i in items if i.is_spike and i.verdicts]
        spec_hits, spec_n = specificity_of(spikes, PRIMARY_SPECIFICITY_CLASSES)
        sens_hits, sens_n = sensitivity_of(spikes, UNSUPPORTED_CLASSES)
        floor_hits, floor_n = specificity_of(spikes, ("verbatim",))

        assert (spec_hits, spec_n) == (28, 30)
        assert (sens_hits, sens_n) == (45, 45)
        assert (floor_hits, floor_n) == (18, 18)
        label, _reasons = verdict(
            spec_hits / spec_n, sens_hits / sens_n, floor_hits / floor_n
        )
        assert label == "FIT TO QUOTE"

        # The decomposition CLAUDE.md now quotes as the actionable result. The
        # `invented` half is the load-bearing one: it is what licenses quoting
        # 13.3% with no correction, so a drift here would be a drift in advice.
        supported = [i for i in spikes if i.truth_supported]
        assert sum(1 for i in supported if i.verdicts[0] == "invented") == 0
        assert sum(1 for i in supported if i.verdicts[0] == "distorted") == 5
        absent = [i for i in spikes if i.cls in ("foreign", "fabricated")]
        assert sum(1 for i in absent if i.verdicts[0] == "invented") == len(absent) == 27


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_support_judge_spike_in(di_container):
    """3 documents x 2 batches x 2 passes = 12 judge calls, plus arm A extraction.

    NOT `@traced` — conftest's tracer serialises the test's arguments as span input
    and `di_container` is cyclic.
    """
    print(f"\n  judge {DEFAULT_TIER_STRONG}, work {DEFAULT_TIER_WEAK}\n", flush=True)
    items, refusals = await run(di_container)
    path = save(items, judge_model=DEFAULT_TIER_STRONG, refusals=refusals)
    print(f"\n  saved {path}\n", flush=True)
    print_read()
    assert any(i.verdicts for i in items), "every judge call failed"


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
