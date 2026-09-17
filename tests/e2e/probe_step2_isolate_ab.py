"""
Does step 2 of thesis extraction need the source text in its history?

WHAT IS BEING DECIDED
=====================
`ThesisExtraction._step2_identify_candidates` fans out over step 1's content
items, one gate call per item, and each of those calls inherits step 1's history
— which holds step 1's prompt, and step 1's prompt holds the whole
`<source_text>`. So a window sends its source once for step 1 and then again for
every one of its `count + 2` gate calls.

`probe_ingest_cost.py` priced that: **step 2 is 207,047 tokens, 75% of
everything the document's SIZE costs**, plus a cache-write surcharge nobody
reads. Cutting ~7 full-text sends per extraction to 1 is the single biggest token
win left on the ingestion path.

It was never taken, on purpose, because it is a REASONING change: step 2 decides
whether an item is assertable/substantive/atomic and decomposes compound items,
and today it can look at the source to do that. Nobody knew whether it USES it.
This probe answers that and nothing else.

THE DESIGN, AND WHY IT IS PAIRED
================================
Step 1 runs ONCE per document, and every arm then judges the SAME content items:

    arm A (today)      step 1's whole history — system prompt + step 1's prompt
                       (the whole source) + step 1's answer, per call
    arm B (rejected)   a fresh conversation with the SAME system prompt and NO
                       history — the item and nothing else
    arm C (candidate)  arm A's exact three messages with the source window
                       replaced by a sentinel saying it was elided: system
                       prompt + step 1's request without its source + step 1's
                       ANSWER

Pairing matters more than sample size here. Step 1 is itself stochastic, and if
each arm ran its own step 1 the arms would be judging different items and any
difference would be unattributable. This way the ONLY variable is what step 2
can see.

**The gate is stochastic, so a raw cross-arm disagreement rate means nothing on
its own.** Every arm therefore runs `REPS` times and the report prints a
self-consistency floor per arm alongside the two cross-arm rates. An arm effect
exists only if the cross rate clears both of the floors it sits between. This is
the whole reason the probe repeats rather than running once per arm.

WHY ARM B IS STILL RUN AFTER BEING REJECTED
===========================================
It is the positive control, and it is the reason a null on arm C can be believed.
The 2026-09-11 run found a specific, directional effect in arm B — `is_substantive`
flipping A-false-to-B-true, 5 times, 0 the other way — so if THIS run does not
reproduce it, the instrument is not sensitive today and "arm C looks fine" is not
a finding. Arm B gets no judge calls; the decision is A against C, and B is here
to show the gate can be moved at all.

WHAT IS MEASURED
================
- **prefill tokens per arm** (`call_census`) — the thing being bought.
- **gate decisions per item** — `(is_assertable, is_substantive, is_atomic)`,
  compared within and across arms as above.
- **candidate yield** — how many atomic theses survive, per arm.
- **self-containment**, two ways: a mechanical leading-deixis count (a candidate
  starting "This/It/They..." has lost its referent) and a blinded judge. Both were
  expected to carry the signal for arm B and NEITHER DID — see RESULTS. They stay
  as regression guards; that finding came from the gate fields.
- The judge is **blinded and its labels alternate by rep**, and its raw
  first-vs-second split is reported, because alternating alone would convert a
  positional preference into a fake 50/50 between the arms instead of exposing it.
  It turned out to be biased, which is why that control is not optional.
- **Whether the judge is rating faithfulness or LENGTH** (added 2026-09-17, after
  the faithfulness endpoint failed in a run where arm A also happened to yield 6%
  more candidates — a lean toward the fuller set would look exactly like a lean
  toward arm A). Two extra comparisons per rep, through the same judge:
  a **length control**, one arm's set against a randomly trimmed copy of ITSELF,
  where provenance is identical on both sides and only the count differs, so
  "tie" is the clean result and any lean to the fuller side is the judge rating
  size; and a **length-matched re-judge**, A against C with the counts equalised.
  The control is the cleaner instrument of the two — trimming for the matched
  comparison discards real claims and which ones is luck, so a lean that
  disappears under it has been perturbed, not refuted. The trim is random rather
  than positional (a tail trim would drop whatever the document says last and get
  read as unfaithfulness) and seeded on document+rep so a surprising result
  reproduces instead of re-rolling. `self_contained` is expected to favour the
  fuller set there and is not evidence: the judge is asked for it as a COUNT
  first, and a trimmed set has a smaller one by construction — that lean is a
  sign the judge is reading the question, and faithfulness is the line that
  matters because nothing about it scales with size. Both are DIAGNOSTIC and
  neither is an endpoint: an instrument built after seeing a result cannot retire
  the endpoint it was built to question, only say whether that endpoint deserves
  a rerun under a corrected design.
- **Per-claim support, UNPAIRED** (added 2026-09-17 after the paired judge
  returned both verdicts on two runs of the same code and model). One arm's set,
  the source, and one verdict per claim — supported / distorted / invented. No
  second set to be longer than, no position to prefer, no tie to hide in, and the
  output is a RATE over hundreds of claims rather than a preference over twelve
  comparisons. Read against one arm's own rep-to-rep swing, because a gap between
  arms smaller than how much a single arm moves by itself is not a difference.
  A verdict list that does not line up with the set is DISCARDED rather than
  truncated, and the count of discards is printed: a rate computed over a
  misaligned list is a made-up number.

The gate metric is read over `is_assertable` and `is_substantive` ONLY, because
those two are what `_step2_identify_candidates` branches on. `is_atomic` is on the
DTO and read by no code, so it is reported separately; mixing it in materially
changed the verdict on the first pass.

**But "read by no code" is not "harmless", and that distinction was missed until
2026-09-17.** The FIELD is unread; the DECOMPOSITION it describes is the output —
the same call returns `atomic_theses`, and `candidates.extend(result.atomic_theses)`
is the whole of what step 2 produces. A call that says `is_atomic=false` has split
the item, so an `is_atomic` disagreement is a report that the two arms cut the item
differently. The instrument that catches that is CANDIDATE YIELD, not the gate
rate, and the two must be read together: arm B's 22 one-directional `is_atomic`
flips in this run came with 180 candidates against arm A's 153 while its deciding
rate was 0.0%. So a run in which only `is_atomic` moves is a run in which the
preregistered endpoint is blind and the yield line is the finding.

The documents are chosen for this question rather than for size: one whose
sentences are self-contained (the control — if a stripped arm is fine anywhere it
is here), one narrative with referents spread across sentences, one technical with
terms defined once and used later. If dropping the source hurts, it should hurt
those two and not the first.

THE COST FIGURE IS PROJECTED, AND HAS TO BE
===========================================
The documents above are ~1k chars, because the reasoning question needs referents
that fit in one readable page. At that size the source is a SMALL part of a step-2
prompt (system prompt + item + instructions dominate), so the measured saving is
around 1.4x and says nothing about production. The saving is size-dependent by
construction: arms B and C send a FIXED prefill per call, while arm A's carries
the source.

So the probe measures the per-call decomposition and projects it to one real
window (`CHUNK_SIZE`, 40,000 chars) by replacing each document's own source term
with a full window's worth. The projection is labelled an ESTIMATE and assumes
~4 chars/token; it is there to check the recorded ~7x is the right order, not to
replace `probe_ingest_cost`'s direct measurement of it.

PREREGISTERED READING (for arm C; arm B was decided on 2026-09-11)
==================================================================
TAKE arm C if (a) its PROJECTED prefill at window size is under 40% of arm A's,
and (b) no reasoning regression: cross-arm gate flips against A do not clear the
noise floors, C's leading-deixis count is no worse than A's, and the judge does
not prefer A on faithfulness in a majority of comparisons. Anything else: DON'T
TAKE, and the print says which endpoint failed.

**And one endpoint that only a three-arm run can have: arm B must reproduce its
known effect.** If A-vs-B does not clear the floors in this run, the report says
so and no conclusion about arm C is drawn either way — a null from a blunt
instrument is not a null.

Every arm here is a real code path, not a reimplementation: all three go through
`ThesisExtraction._step2_conversation`, arms A and C by flipping
`settings.extraction_step2_carries_source` around the call.
`_the_arms_are_the_shipped_code_paths` asserts that the real fan-out still goes
through that seam and that its default is arm A — because the day step 2 stops
calling it, this file measures nothing.

Run: `poetry run pytest tests/e2e/probe_step2_isolate_ab.py -s --real-llm`
Env:  DIALEXITY_PROBE_S2_REPS (default 4)

RESULTS (2026-09-11, REPS=5, haiku-4-5 work / sonnet-5 judge, 3 documents)
=========================================================================
This run had arms A and B only.

**VERDICT: DON'T TAKE arm B as a straight swap.** The saving is real and large;
the gate's keep/drop decision moves, deterministically and in ONE direction.

COST — endpoint PASSES.
    per call:  A ~1,860 prefill tokens   B ~1,358   (B is size-independent)
    projected at CHUNK_SIZE: B is 11.7% of A, **8.5x**, identical across all three
    documents — which confirms `probe_ingest_cost`'s recorded ~7x is the right
    order. Measured at these document sizes it is only 1.4x; that figure is an
    artefact of the documents and must not be quoted.

REASONING — endpoint FAILS, on the deciding fields:
    A-vs-A  0.0% (0/180)      <- arm A is perfectly self-consistent
    B-vs-B  0.0% (0/180)      <- so is arm B
    A-vs-B  5.6% (5/90)
Both floors are ZERO, so those 5 are not sampling noise: they are a systematic
arm effect. Every one of them is the same field moving the same way —
**`is_substantive`, A says false and B says true, 5 times, 0 the other way.**
Without the source, step 2 admits items that with the source it rejects.

That is a coherent mechanism rather than a curiosity. "Substantive" is not a
property of a sentence in isolation: an item that merely restates something the
document established earlier is not substantive, and NOTHING IN THE ITEM ITSELF
SAYS SO. Arm B cannot see the earlier text, so it admits it. Candidate yield shows
the same thing from the other end: on the technical document — the one that defines
terms once and then references them — A kept 8-11 and B kept 13-16.

**CORRECTION, 2026-09-17.** This paragraph used to support that mechanism with
"per-document cross-arm flips were technical 43.3%, self-contained 16.7%,
narrative 0.0%", presented as the concentration of the deciding-field effect. Those
were the ALL-THREE-FIELDS rates, so they are dominated by `is_atomic` and they
cannot be the five deciding flips: 43.3% of that document's 30 comparisons is 13,
more than the whole run's deciding disagreement. The claim that the effect
concentrates on the technical document rests on the candidate-yield sentence above
and on nothing else, and the report now prints both metrics per document, labelled,
so the substitution cannot be made again. The verdict on arm B is unaffected — it
was read from the aggregate 5.6% against two 0.0% floors, and both directions of
the five flips are recorded above.

TWO OF THIS PROBE'S OWN INSTRUMENTS CARRIED NO SIGNAL, which is worth more than
the trouble they saved:
- **The leading-deixis check found 0 in both arms, twice.** It was pointed at the
  wrong risk. Step 2 receives the item's full text, so pronouns resolve from the
  item; what is lost with the source is not the referent, it is whether the claim
  ADDS anything. Kept as a regression guard, not as evidence.
- **The judge is weakly positionally biased** — 62% of its decided calls went to
  whichever set was shown first — and once the labels were alternated it split
  faithfulness 5-5. Do not lean on it here. The first run (REPS=2) appeared to
  show a 7-2 faithfulness lean toward A; that did not survive either the extra
  reps or the positional control, and it is a good example of why the control is
  in the file.

A PRIOR READ OF THIS PROBE WAS WRONG and the correction is the point: before
`is_atomic` was separated out, B looked UNSTABLE (B-vs-B 6.7% against A's 0.0%)
and the arms looked further apart (12.2%). All of that lived in `is_atomic` — a
field this DTO returns and no code reads. Mixing it into the decision metric
invented an instability that cannot reach a candidate list.

That run left one thing open, and arm C is it: the gate needs SOME sense of what
the document already established, but there is no reason it needs the whole source
to get it. Step 1's ANSWER is that sense — the other content items, which are what
the document established, at a fixed and tiny price.

RESULTS (2026-09-17, REPS=4, haiku-4-5 work / sonnet-5 judge, 3 documents)
=========================================================================
Three arms, 72 gate calls each, 131.5s. **VERDICT: DON'T TAKE arm C.** One
endpoint failed, and it is the judge on faithfulness. The default stays `True`.

COST — endpoint PASSES, and it is the smallest of the three savings.
    per call:  A ~1,846-1,877   B ~1,352-1,366   C ~1,610-1,706
    projected at CHUNK_SIZE: C is 13.9-14.6% of A, **6.8-7.2x**; B is 11.7%, 8.5x
    on all three documents, reproducing 2026-09-11 to the tenth of a percent.
    Measured at these document sizes C is only 1.1x. Do not quote that.
    72/72 calls reported usage in every arm; cache writes were 0 everywhere, which
    is expected — a step-2 prompt is ~1.9k tokens and the minimum cacheable prefix
    on haiku-4.5 is 4,096.

REASONING — the deciding fields moved NOWHERE, including the control:
    A-vs-A 0.0% (0/108)   B-vs-B 0.0% (0/108)   C-vs-C 0.0% (0/108)
    A-vs-B 0.0% (0/72)   <- positive control, DID NOT REPRODUCE
    A-vs-C 0.0% (0/72)
So the gate's keep/drop decision is not what moved this time, and per the
preregistered rule the A-vs-C 0.0% is NOT evidence for arm C: the instrument that
found arm B's `is_substantive` effect on 2026-09-11 found nothing today, on the
same three documents with one fewer rep. Two candidate reasons, neither tested:
five reps against four, and the effect was five items out of ninety to begin with.

WHAT DID MOVE IS THE DECOMPOSITION, and this is the run that made the point above
about `is_atomic` being unread but not harmless:
    A-vs-B  30.6% (22/72), every one `is_atomic` A_true_other_false
    A-vs-C   8.3% (6/72), `is_atomic` 3 each way — symmetric, so not directional
    candidates  A 153   B 180 (+18%)   C 144 (-6%)
Arm B, with no history at all, calls items non-atomic and splits them, and yields
18% more candidates than A while agreeing with A on every keep/drop. That is a
second, independent reason to leave arm B rejected, and it is one the deciding-field
metric could not see. Arm C's own 6 flips go both ways and its yield is 6% below A.

JUDGE — the failing endpoint, and this time the control is clean.
    faithful   A 9   C 2   tie 1     <- FAILS (A in 9 of 12; 9 of 11 decided, 82%)
    atomic     A 6   C 2   tie 4
    self_contained  A 0   C 0   tie 12
    positional control: first set shown 9, second 10, tie 17 — **47%, unbiased**
The 2026-09-11 run could dismiss a judge lean as position (62% to whatever was
shown first). This one cannot: the labels alternated AND the raw split is even, so
the 9-2 is about the sets. Read it with two cautions. The notes are mixed rather
than consistent — the judge accuses BOTH arms of inventing claims in different
reps ("Set X invents an unstated claim", "Set Y contains a fabricated/inverted
claim") — and `self_contained` was a 12-way tie, so the criterion the whole
elision was expected to threaten found nothing at all.

DEIXIS — 0 of 153, 0 of 180, 0 of 144. Third consecutive null for that instrument
across three runs and two arms. It is a regression guard and nothing more; do not
add reps hoping to move it.

That run left the faithfulness result open: whether the 9-2 was arm C being less
faithful, or the judge preferring the longer of two sets (A yielded 6% more
candidates, and the judge saw both sets whole). Two more runs and two new
instruments answered that, and the answer is that the PAIRED JUDGE cannot settle
it.

RESULTS (runs 2 and 3, same day, same code, same models, REPS=4)
===============================================================
Run 2 added the length controls; run 3 added the per-claim support check. Both
re-ran every endpoint unchanged. **The protocol returned a different verdict each
time: DON'T TAKE, then TAKE, then NO CALL.** That is the headline, and it is a
finding about the instrument rather than about arm C.

WHAT IS STABLE ACROSS ALL THREE RUNS — and it is most of what matters:
    cost         C projects to 13.9-15.0% of A at `CHUNK_SIZE`, **6.7-7.2x**, on
                 every document in every run. B is 11.7%, 8.5x, every time.
    keep/drop    A-vs-C **0.0% in all three runs (0/72, 0/72, 0/72)** against
                 within-arm floors that were 0.0% every time. 216 paired gate
                 comparisons and not one disagreement on what step 2 keeps.
    deixis       0 candidates in every arm in every run. Fourth null.
    yield        NOT stable, and the run-1 claim that A yields 6% more than C does
                 not hold up: A/C were 153/144, then 163/165, then 120/116. The
                 totals themselves swing 35% run to run. So the length asymmetry
                 that motivated the confound worry is itself noise.

WHAT IS NOT STABLE is the paired judge, in three separate ways:
    faithful     run 1  A 9  C 2  tie  1   -> endpoint FAILS
                 run 2  A 5  C 1  tie  6   -> endpoint passes
                 run 3  A 5  C 3  tie  4   -> endpoint passes
                 pooled A 19 C 6 tie 11 -> the endpoint FAILS pooled (19*2 > 36),
                 and excluding ties the lean is 76% (82%, 83%, 62% per run).
    ties         1, then 6, then 4 out of 12. The endpoint counts ties against
                 detection, so its pass/fail is decided by how often the judge
                 shrugs — which is the least stable thing it does.
    position     its raw first-vs-second split was 62%, then 47%, then **73%**.
                 Alternating the labels neutralises that on AVERAGE (six
                 comparisons each way), so it inflates variance rather than
                 favouring an arm — but a judge whose position preference swings
                 that far is not measuring a 5-3 difference.
    control      arm B's known `is_substantive` effect reproduced in run 2 only
                 (5.6%, 4/72, all four the same direction as 2026-09-11). Runs 1
                 and 3 got 0.0%. The effect is five-items-in-ninety small, so this
                 instrument is at the edge of its resolution on 4 reps.

THE TWO CONFOUND-FREE INSTRUMENTS BOTH FIND NOTHING:
    counts equalised (A vs C, trimmed to the same size): run 2 A 3 / C 4 / tie 5,
        run 3 A 4 / C 4 / tie 4.
    length control (one arm against a trimmed copy of ITSELF): the judge preferred
        the fuller set on faithfulness 2 of 8 comparisons then 1 of 6 — 3 decided
        calls in 14, so a sign of a size preference and nowhere near a measurement
        of one. `self_contained` stayed a total tie there, which is the sanity
        check: it is asked as a count, so a length-rating judge should have leaned
        fuller, and it did not.
    per-claim support (run 3, unpaired, the one instrument with a denominator in
        the hundreds): **A 43.3% unsupported (52/120), C 45.7% (53/116)** — a
        2.4pp gap inside arm A's own 38pp rep-to-rep swing, and not close to
        significant on those counts. Same direction as the paired judge, far too
        small to be what the paired judge was reporting.

A SEPARATE FINDING, ARM-INDEPENDENT AND BIGGER THAN THE ARM QUESTION: that
per-claim check says **~44% of everything step 2 emits is not cleanly supported by
its own source** — 36 distorted and 16 invented of arm A's 120 claims, and the
same shape for arm C. One judge, one prompt, unvalidated, and "distorted" will be
catching legitimate compression, so this is a lead and not a number to quote. But
it is measured on the shipped default path and it dwarfs anything the arms differ
by. It is recorded in CLAUDE.md as an open question about extraction, not about
this setting.

WHAT THIS SETTLES. Arm C stays a knob and NOT a default, and the reason is now
different from run 1's: not that arm C is less faithful, but that three runs of a
preregistered protocol produced three verdicts, so there is no stable positive
result to move a reasoning default on. The conservative reading also happens to be
the cheap one to hold: every stable measurement is either neutral (keep/drop,
deixis, both confound-free faithfulness instruments) or in arm A's favour by a
small amount (the paired judge's 76% of decided comparisons). Nobody should flip
this default on a run that says TAKE; pool it against these three first.

WHAT WOULD SETTLE IT, and none of it is built: more reps (the arm-B control needs
enough resolution to reproduce reliably before any null here is readable), more
runs of the per-claim check, which has exactly one behind it, and a
`CHUNK_SIZE`-sized document so the cost figure stops being a projection. Nothing
here supports a third variant on top of arm C.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import random
import time
from contextlib import contextmanager
from typing import Iterator, Literal, Optional

import pytest
from pydantic import BaseModel, Field

from e2e.config import DEFAULT_TIER_STRONG, DEFAULT_TIER_WEAK
from e2e.modelctx import using_model

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.concerns import thesis_extraction as te
from dialectical_framework.concerns.thesis_extraction import (
    CandidateCheckDto, ContentItemDto, ThesisExtraction)
from dialectical_framework.utils.call_census import call_census
from dialectical_framework.utils.chunking import CHUNK_SIZE

#: 2 gives a noise floor at all; 4+ gives one worth reading against. The gate is
#: stochastic and the whole reasoning verdict is a comparison of rates, so a floor
#: built from one pair of reps can be 0/18 by luck and make any cross-arm
#: difference look like an effect.
REPS = int(os.getenv("DIALEXITY_PROBE_S2_REPS", "4"))

#: Step 1 asks for `count + 2` items, so this sets the fan-out width too.
COUNT = 4

INTENT = "What tensions does this material hold?"

#: Arm order is the report order and the comparison order: A is the incumbent,
#: every cross-arm rate is measured against it.
ARMS = ("A", "B", "C")

#: The pairs actually compared. B is here as the positive control (its effect is
#: known), C is the decision.
PAIRS = ("A-vs-B", "A-vs-C")

# --- The documents, chosen for the failure mode under test ---------------------

#: Control. Every sentence stands alone, so step 2 has no reason to want the
#: source. If a stripped arm degrades HERE, the gate is using the source for
#: something other than resolving referents.
_SELF_CONTAINED = """\
Concentrating release authority in one team makes the schedule predictable and
makes every delay theirs alone; distributing it removes the bottleneck and removes
the person who can say the date is wrong.

Documenting a process so it survives turnover freezes the version of it that was
true when somebody wrote it down; leaving it in people's heads keeps it current
and unshareable.

Pricing per seat rewards a vendor for accounts that grow and punishes a vendor for
products that make each seat more capable, since the better they work the fewer
are needed.

A long deprecation window keeps trust with the customers who cannot move and keeps
the code that cannot be simplified, so the cost of the promise lands on everyone
who kept up.

Measuring a team on throughput surfaces the work nobody was tracking and buries
the work that does not decompose into countable units.
"""

#: Referents spread across sentences — "it", "that", "the second one", people
#: named once and then referred to. This is the case that should break if
#: anything does.
_NARRATIVE = """\
Mara took over the platform group in March. The group had been split in two the
year before, and she inherited both halves without inheriting the reason they were
split. She kept the arrangement for a quarter because unwinding it would have cost
her the only two people who understood the older half.

That decision bought her a stable quarter and a reputation for not touching
anything. When the outage came in August it came from the seam between the halves,
which nobody owned, and the review found that everyone had assumed the other side
was watching it.

She could have merged them in April. Doing that would have meant one of the two
leads reporting to the other, and the one who would have lost the title was the
one who knew the old system. He would have left, and the knowledge would have gone
with him, which is the thing she had been protecting all along.

Her director wanted a decision by the end of the month. He had been through the
same choice at his last company and had merged, and he lost the person, and he
still thinks it was right. Mara does not think their situations are the same,
though she cannot say exactly what differs.
"""

#: Terms defined once, then used bare. Different mechanism from the narrative:
#: the missing context is a definition rather than a pronoun's antecedent.
_TECHNICAL = """\
The ingest path builds a digest for every source. A digest is the system's
standing understanding of that source, rewritten whenever a new intent arrives,
and it is what every later stage reads instead of the raw bytes.

Sources larger than one prompt are read in overlapping windows. Each window is
digested on its own and the readings are then reduced into one. Coverage is the
guarantee here rather than best effort: a digest that describes the first few
pages while presenting itself as the understanding of the whole source is a lie
nothing downstream can detect.

Extraction does not go through the digest. It sweeps the windows directly,
because extraction has no query — the theses are what is being looked for — so
retrieval against the stated intent returns what the intent already anticipated
and misses whatever nobody thought to ask about.

The sweep is capped at three concurrent windows, lower than the digest's eight,
because each window is itself a fan-out of one call per requested candidate plus
two. In-flight calls are therefore roughly the cap times six.
"""

DOCUMENTS: dict[str, str] = {
    "self-contained": _SELF_CONTAINED,
    "narrative": _NARRATIVE,
    "technical": _TECHNICAL,
}

# --- Mechanical self-containment ----------------------------------------------

#: A candidate opening with one of these has lost whatever it pointed at. Not a
#: general deixis detector and not meant to be: it targets the one failure the
#: change under test could cause, and it is deterministic, which the judge is not.
_LEADING_DEIXIS = {
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    "he", "his", "she", "her", "such", "the former", "the latter", "both",
    "there", "then", "doing", "the group", "the arrangement", "the decision",
}


def _opens_with_deixis(candidate: str) -> bool:
    """True when the first word cannot be resolved without the source."""
    stripped = candidate.strip().strip("\"'").lower()
    if not stripped:
        return False
    for phrase in ("the former", "the latter", "the group", "the arrangement",
                   "the decision"):
        if stripped.startswith(phrase):
            return True
    first = stripped.split()[0].strip(",.;:")
    return first in _LEADING_DEIXIS


# --- The judge ----------------------------------------------------------------

_JUDGE_SYSTEM = """\
You are judging two sets of candidate theses that two different pipelines
extracted from the same source document. Judge only what is asked. Prefer "tie"
whenever the sets are comparable — a forced preference between equivalent sets is
worse than no preference, because it will be read as an effect.
"""


class JudgeDto(BaseModel):
    """Blinded comparison of two candidate sets over one document."""

    self_contained_x: int = Field(
        description="How many of set X's theses are interpretable on their own, "
        "by a reader who cannot see the source"
    )
    self_contained_y: int = Field(
        description="Same count for set Y"
    )
    self_contained_winner: Literal["tie", "x", "y"] = Field(
        description="Which set is more interpretable standalone"
    )
    faithful_winner: Literal["tie", "x", "y"] = Field(
        description="Which set states what the source actually says, without "
        "inventing or distorting claims"
    )
    atomic_winner: Literal["tie", "x", "y"] = Field(
        description="Which set is better decomposed: one claim per thesis, "
        "without splitting a single causal relationship into halves"
    )
    note: str = Field(description="One sentence naming the clearest difference")


def _judge_prompt(source: str, set_x: list[str], set_y: list[str]) -> str:
    listed_x = "\n".join(f"- {c}" for c in set_x) or "(none)"
    listed_y = "\n".join(f"- {c}" for c in set_y) or "(none)"
    return f"""<source>
{source}
</source>

<set_x>
{listed_x}
</set_x>

<set_y>
{listed_y}
</set_y>

Judge set X against set Y on three things:
1. Self-containment — would a reader who cannot see the source understand each
   thesis? Count them per set. A thesis opening with an unresolved "this", "it",
   "they" or a bare definite reference is NOT self-contained.
2. Faithfulness — does the set state what the source says, without invention?
3. Atomicity — one claim per thesis, but a single causal relationship
   ("X enables Y") counts as ONE claim and must not be split.

Answer "tie" on any criterion where the sets are comparable."""


async def _judge(
    container, document: str, set_x: list[str], set_y: list[str]
) -> JudgeDto:
    """One judge call. Every comparison in this probe goes through here.

    Shared rather than inlined per comparison because two of the three callers
    are CONTROLS on the third, and a control is only a control while it is the
    same instrument: a different system prompt, a different criteria list or a
    different model would make its "tie" unreadable against the other's lean.
    """
    with using_model(container, DEFAULT_TIER_STRONG):
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_JUDGE_SYSTEM)
        return await conversation.submit(
            response_model=JudgeDto,
            user_content=_judge_prompt(document, set_x, set_y),
        )


# --- Faithfulness without a comparison ----------------------------------------
# The paired judge above cannot settle faithfulness, and two runs of it proved
# that rather than argued it: 2026-09-17 run 1 said A 9 / C 2 / tie 1 and failed
# the endpoint, run 2 said A 5 / C 1 / tie 6 and passed it, on the same code and
# the same model. The DIRECTION held (82% and 83% of decided comparisons went to
# A) and the tie rate is what moved, so the endpoint's pass/fail was decided by
# how often the judge shrugged. A paired judge also has two nuisance variables
# built in — set size and set position — and the controls found both.
#
# So this instrument drops the pairing. One arm's set, one source, one verdict per
# claim: is this stated in the source or not. There is no other set to be longer
# than and no position to prefer, the output is a RATE rather than a preference,
# and ties are not expressible. Cost is the same order as the paired judge (one
# call per arm per rep) because the claims are batched into one call, not asked
# one at a time.

_SUPPORT_SYSTEM = """\
You are checking candidate theses against the source document they were extracted
from. Judge each thesis on its own and against the source only. You are not
comparing lists and there is no second list. Being incomplete is not a fault here:
a thesis that states less than the source does is still supported.
"""


class ClaimVerdictDto(BaseModel):
    """One thesis, checked against the source."""

    thesis: str = Field(description="The thesis being judged, copied verbatim")
    verdict: Literal["supported", "distorted", "invented"] = Field(
        description="supported = the source states this, in these or other words; "
        "distorted = the source says something related but this changes its "
        "meaning, direction or strength; invented = the source does not support it"
    )


class SupportDto(BaseModel):
    verdicts: list[ClaimVerdictDto] = Field(
        description="One entry per thesis, in the order given"
    )


def _support_prompt(source: str, candidates: list[str]) -> str:
    listed = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(candidates))
    return f"""<source>
{source}
</source>

<theses>
{listed}
</theses>

Return one verdict per thesis, in the order given, copying each thesis verbatim:
- supported — the source states this, in these words or others.
- distorted — the source says something related, but this changes its meaning,
  its causal direction, or its strength.
- invented — the source does not support this.

Judge only whether the source backs the thesis. Do not judge wording, overlap
with other theses, or whether anything is missing."""


async def _support(
    container, document: str, candidates: list[str]
) -> Optional[list[str]]:
    """Per-claim support verdicts for one set, or None if they cannot be aligned.

    A returned list shorter or longer than the set means the model dropped or
    merged entries, and a rate computed over a misaligned list is a made-up
    number — so the call is discarded and the report says how many were.
    """
    if not candidates:
        return []
    with using_model(container, DEFAULT_TIER_STRONG):
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(_SUPPORT_SYSTEM)
        result = await conversation.submit(
            response_model=SupportDto,
            user_content=_support_prompt(document, candidates),
        )
    if len(result.verdicts) != len(candidates):
        return None
    return [v.verdict for v in result.verdicts]


# --- Length as a confound ------------------------------------------------------


def _trimmed(candidates: list[str], keep: int, seed: str) -> list[str]:
    """A subset of `keep` candidates, chosen at random, in the original order.

    RANDOM and not positional: a set trimmed from the tail loses whatever the
    document said last, so a positional trim would test coverage of the ending
    and get read as length. Order is restored after sampling because the sets
    otherwise arrive in document order, and scrambling one side would introduce a
    second difference into a comparison whose whole point is having one.

    Seeded on the document and rep so a re-run trims identically: a surprising
    verdict has to be reproducible rather than re-rollable.
    """
    if keep >= len(candidates):
        return list(candidates)
    kept = sorted(random.Random(seed).sample(range(len(candidates)), keep))
    return [candidates[i] for i in kept]


# --- The arms -----------------------------------------------------------------


@contextmanager
def _carrying_source(container, carries: bool) -> Iterator[None]:
    """Point DI settings at one arm's value of the knob under test.

    Same shape as `using_model` and for the same reason: `settings` is a DI
    singleton read at call time, so the only honest way to run two arms in one
    process is to flip it around each call. `using_model` nests INSIDE this, and
    must — it copies whatever instance is current, so the inner override carries
    this flag along with the model.
    """
    previous = container.settings()
    container.settings.override(
        previous.model_copy(update={"extraction_step2_carries_source": carries})
    )
    try:
        yield
    finally:
        container.settings.reset_override()
        container.settings.override(previous)


async def _gate_calls(
    concern: ThesisExtraction, items: list[ContentItemDto]
) -> list[CandidateCheckDto]:
    """One gate call per item, through the concern's own seam.

    This is `_step2_identify_candidates`' fan-out with the collection step left
    off: the real function returns only the merged candidate list, and the whole
    analysis here is per-item gate decisions.
    """
    tasks = [
        concern._step2_conversation(items).submit(
            response_model=CandidateCheckDto,
            user_content=concern._step2_prompt(item.content, item.content_type),
        )
        for item in items
    ]
    return list(await asyncio.gather(*tasks))


async def _arm_fresh(
    concern: ThesisExtraction, items: list[ContentItemDto]
) -> list[CandidateCheckDto]:
    """Arm B — REJECTED on 2026-09-11, kept as the positive control.

    Unlike arms A and C this is not reachable through any setting, so it stays a
    local construction. The system prompt is KEPT; only step 1's history goes.
    Dropping the system prompt too would be a different and much larger change,
    and it is not the one that was priced.
    """

    def fresh() -> ConversationFacilitator:
        conversation = ConversationFacilitator()
        conversation.set_system_prompt(te.SYSTEM_PROMPT)
        return conversation

    tasks = [
        fresh().submit(
            response_model=CandidateCheckDto,
            user_content=concern._step2_prompt(item.content, item.content_type),
        )
        for item in items
    ]
    return list(await asyncio.gather(*tasks))


async def _run_arm(
    arm: str,
    container,
    concern: ThesisExtraction,
    items: list[ContentItemDto],
) -> list[CandidateCheckDto]:
    """Dispatch one arm, with the knob set to whatever that arm means."""
    if arm == "B":
        with using_model(container, DEFAULT_TIER_WEAK):
            return await _arm_fresh(concern, items)
    carries = arm == "A"
    with _carrying_source(container, carries):
        with using_model(container, DEFAULT_TIER_WEAK):
            return await _gate_calls(concern, items)


async def _step1(text: str) -> tuple[ThesisExtraction, list[ContentItemDto]]:
    """Run step 1 once, exactly as `extract_candidates` sets it up.

    The private fields are assigned here rather than calling
    `extract_candidates`, because that would run step 2 as well and this probe
    needs to run step 2 several times against ONE step-1 result. The assignments
    mirror `extract_candidates`' preamble; the prompts come from the concern's
    own builders, so nothing about the wording is reimplemented.
    """
    concern = ThesisExtraction()
    concern._text = text.strip()
    concern._count = min(COUNT, 4)
    concern._focus = ""
    concern._not_like_these = []
    concern._conversation.set_system_prompt(te.SYSTEM_PROMPT)
    items = await concern._step1_extract_content()
    return concern, items


def _candidates(checks: list[CandidateCheckDto]) -> list[str]:
    """The concern's own collection rule: gate, then dedup preserving order."""
    out: list[str] = []
    for check in checks:
        if check.is_assertable and check.is_substantive:
            out.extend(check.atomic_theses)
    return list(dict.fromkeys(out))


def _decisions(checks: list[CandidateCheckDto]) -> list[tuple[bool, ...]]:
    return [(c.is_assertable, c.is_substantive, c.is_atomic) for c in checks]


def _gate(checks: list[CandidateCheckDto]) -> list[tuple[bool, ...]]:
    """Only the fields that DECIDE anything.

    `_candidates` — and `_step2_identify_candidates`, which it mirrors — keeps an
    item on `is_assertable and is_substantive`. `is_atomic` is returned by the DTO
    and read by nobody, so a flip in it changes no downstream output. Counting it
    as a decision flip makes the reasoning metric fire on a difference that cannot
    reach a candidate list, which is why this is measured apart from `_decisions`.
    """
    return [(c.is_assertable, c.is_substantive) for c in checks]


def _flip_rate(
    left: list[tuple[bool, ...]], right: list[tuple[bool, ...]]
) -> tuple[int, int]:
    """Per-item decisions that differ, over items compared."""
    pairs = list(zip(left, right))
    return sum(1 for a, b in pairs if a != b), len(pairs)


def _the_arms_are_the_shipped_code_paths() -> None:
    """Arms A and C must be what ships, or this probe compares two inventions.

    Checked structurally rather than by calling `_step2_identify_candidates`,
    which returns only the merged candidate list and would hide the per-item gate
    decisions the whole analysis rests on. Three things have to hold: the real
    fan-out goes through the same seam these arms call, its prompt call has the
    shape they copy, and the knob's DEFAULT is arm A — otherwise "arm A" here is
    not the incumbent and every cross-arm rate below is measured against nothing.
    """
    source = inspect.getsource(te.ThesisExtraction._step2_identify_candidates)
    assert "self._step2_conversation(content_items)" in source, (
        "step 2 no longer fans out over `_step2_conversation`, so the arms below"
        " are not shipped behaviour and this probe measures nothing. Re-read the"
        " change before trusting any number here."
    )
    assert "self._step2_prompt(item.content, item.content_type)" in source, (
        "step 2's prompt call changed shape; the arms copy it verbatim and must be"
        " updated with it."
    )
    from dialectical_framework.settings import Settings

    default = Settings.model_fields["extraction_step2_carries_source"].default
    assert default is True, (
        "the knob's default has moved, so arm A is no longer the incumbent."
        " Re-label the arms before reading any comparison below."
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(3600)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_step2_isolate_ab(di_container):
    _the_arms_are_the_shipped_code_paths()

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    print(f"\nwork model:  {DEFAULT_TIER_WEAK}")
    print(f"judge model: {DEFAULT_TIER_STRONG}")
    print(f"documents:   {len(DOCUMENTS)}   reps per arm: {REPS}   count: {COUNT}")
    print(f"arms:        A carries the source, B carries nothing,"
          f" C carries step 1's answer only")
    if REPS < 2:
        print(
            "  NOTE: REPS < 2, so there is NO noise floor and a cross-arm"
            " difference cannot be attributed. Raise DIALEXITY_PROBE_S2_REPS."
        )

    # Accumulators, per arm.
    prefill: dict[str, int] = {arm: 0 for arm in ARMS}
    cache_writes: dict[str, int] = {arm: 0 for arm in ARMS}
    calls: dict[str, int] = {arm: 0 for arm in ARMS}
    measured: dict[str, int] = {arm: 0 for arm in ARMS}
    yielded: dict[str, list[int]] = {arm: [] for arm in ARMS}
    deixis: dict[str, int] = {arm: 0 for arm in ARMS}
    total_candidates: dict[str, int] = {arm: 0 for arm in ARMS}
    within: dict[str, list[int]] = {arm: [0, 0] for arm in ARMS}
    #: The same comparisons over the DECIDING fields only. `is_atomic` is returned
    #: and never read, so these are the rates the verdict is read from.
    within_gate: dict[str, list[int]] = {arm: [0, 0] for arm in ARMS}
    cross_flips: dict[str, list[int]] = {pair: [0, 0] for pair in PAIRS}
    cross_gate: dict[str, list[int]] = {pair: [0, 0] for pair in PAIRS}
    #: Which field moved and which way, so a flip can be attributed rather than
    #: just counted. Keyed pair -> field -> direction.
    directions: dict[str, dict[str, int]] = {pair: {} for pair in PAIRS}
    judge_wins = {"self_contained": [], "faithful": [], "atomic": []}
    #: The judge's RAW choices, before unblinding. A judge that mostly picks the
    #: first set shown has a positional bias, and alternating the labels by rep
    #: only converts that bias into a fake 50/50 split between the arms — it does
    #: not detect it. This is the control that detects it.
    judge_positional = {"x": 0, "y": 0, "tie": 0}
    judge_notes: list[str] = []
    #: The 2026-09-17 open question, instrumented. Arm A yielded 6% more
    #: candidates than arm C and the judge above saw both sets whole, so its
    #: faithfulness lean toward A could be a preference for the longer set. Two
    #: extra comparisons per rep separate the two:
    #:   `length_*`  — the SAME arm's set against a randomly trimmed copy of
    #:                 itself. Provenance is identical on both sides and only the
    #:                 count differs, so "tie" is the clean result and any lean to
    #:                 the fuller side is the judge rating length. This is the
    #:                 cleaner of the two instruments.
    #:   `matched_*` — A against C with the counts equalised. Closer to the real
    #:                 question but not clean: trimming removes real claims, and
    #:                 which ones it removes is luck.
    matched_wins = {"self_contained": [], "faithful": [], "atomic": []}
    matched_positional = {"x": 0, "y": 0, "tie": 0}
    length_wins = {"self_contained": [], "faithful": [], "atomic": []}
    length_positional = {"x": 0, "y": 0, "tie": 0}
    #: How often each arm was the longer one, and by how much. The direction
    #: matters: a length-preferring judge helps whichever arm happened to be
    #: fuller, so it only confounds the A lean while A is usually the fuller one.
    longer_arm_counts = {"A": 0, "C": 0, "equal": 0}
    trimmed_amounts: list[int] = []
    #: Per-claim support, unpaired: arm -> verdict -> count, plus the per-rep
    #: unsupported rate so the spread is visible and the arms' difference can be
    #: read against it. `dropped` counts calls whose verdict list did not line up
    #: with the set and were therefore discarded.
    support: dict[str, dict[str, int]] = {
        arm: {"supported": 0, "distorted": 0, "invented": 0} for arm in ("A", "C")
    }
    support_rates: dict[str, list[float]] = {"A": [], "C": []}
    support_dropped = 0
    #: Per-document, per-arm (prefill, calls). The projection needs the per-call
    #: figure against a KNOWN document size, which the aggregate cannot give.
    by_doc: dict[str, dict[str, list[int]]] = {}
    #: Cross-arm flips per document, printed separately because the prediction is
    #: about WHICH documents move: the self-contained control should not. BOTH
    #: metrics are kept per document, because the 2026-09-11 results section
    #: recorded the all-three-fields per-document rates in a paragraph explaining
    #: the DECIDING-field effect, and the two are nowhere near each other (43.3%
    #: against a total of five deciding flips in that whole run).
    flips_by_doc: dict[str, dict[str, list[int]]] = {}
    gate_flips_by_doc: dict[str, dict[str, list[int]]] = {}

    started = time.monotonic()

    for name, document in DOCUMENTS.items():
        print(f"\n--- {name} ({len(document):,} chars) " + "-" * 30)

        with using_model(di_container, DEFAULT_TIER_WEAK):
            concern, items = await _step1(document)
        print(f"  step 1 -> {len(items)} content item(s)")
        if not items:
            print("  NOTE: step 1 found nothing; this document contributes nothing.")
            continue

        per_rep: dict[str, list[list[CandidateCheckDto]]] = {arm: [] for arm in ARMS}
        per_rep_candidates: dict[str, list[list[str]]] = {arm: [] for arm in ARMS}
        by_doc[name] = {arm: [0, 0] for arm in ARMS}
        flips_by_doc[name] = {pair: [0, 0] for pair in PAIRS}
        gate_flips_by_doc[name] = {pair: [0, 0] for pair in PAIRS}

        for rep in range(REPS):
            for arm in ARMS:
                with call_census() as census:
                    checks = await _run_arm(arm, di_container, concern, items)
                # `CallRecord.prefill_tokens`' definition: everything the provider
                # processed, however it was billed. Cache writes are counted in —
                # the copied source is what pays that surcharge, so excluding them
                # would understate exactly what is under test.
                arm_prefill = (
                    census.uncached_input_tokens
                    + census.cache_read_tokens
                    + census.cache_write_tokens
                )
                prefill[arm] += arm_prefill
                by_doc[name][arm][0] += arm_prefill
                by_doc[name][arm][1] += census.count
                cache_writes[arm] += census.cache_write_tokens
                calls[arm] += census.count
                measured[arm] += census.calls_with_usage
                per_rep[arm].append(checks)

                found = _candidates(checks)
                per_rep_candidates[arm].append(found)
                yielded[arm].append(len(found))
                total_candidates[arm] += len(found)
                deixis[arm] += sum(1 for c in found if _opens_with_deixis(c))

            for pair in PAIRS:
                other = pair.split("-vs-")[1]
                differing, compared = _flip_rate(
                    _decisions(per_rep["A"][rep]), _decisions(per_rep[other][rep])
                )
                cross_flips[pair][0] += differing
                cross_flips[pair][1] += compared
                flips_by_doc[name][pair][0] += differing
                flips_by_doc[name][pair][1] += compared

                gate_differing, gate_compared = _flip_rate(
                    _gate(per_rep["A"][rep]), _gate(per_rep[other][rep])
                )
                cross_gate[pair][0] += gate_differing
                cross_gate[pair][1] += gate_compared
                gate_flips_by_doc[name][pair][0] += gate_differing
                gate_flips_by_doc[name][pair][1] += gate_compared

                for a_check, other_check in zip(per_rep["A"][rep], per_rep[other][rep]):
                    for field in ("is_assertable", "is_substantive", "is_atomic"):
                        a_value = getattr(a_check, field)
                        other_value = getattr(other_check, field)
                        if a_value != other_value:
                            way = "A_true_other_false" if a_value else "A_false_other_true"
                            key = f"{field} {way}"
                            directions[pair][key] = directions[pair].get(key, 0) + 1

            # Blinded, with the label assignment alternating by rep. The judge
            # decides A against C; arm B is the positive control and is decided by
            # the gate fields, which is where its effect was found.
            a_is_x = rep % 2 == 0
            a_set = per_rep_candidates["A"][rep]
            c_set = per_rep_candidates["C"][rep]
            verdict = await _judge(
                di_container,
                document,
                a_set if a_is_x else c_set,
                c_set if a_is_x else a_set,
            )

            def unblind(choice: str) -> str:
                if choice == "tie":
                    return "tie"
                chose_x = choice == "x"
                return "A" if chose_x == a_is_x else "C"

            def record(into: dict, positional: dict, dto: JudgeDto, name_of) -> None:
                """Tally one judge verdict, unblinded, plus its raw split."""
                for criterion, choice in (
                    ("self_contained", dto.self_contained_winner),
                    ("faithful", dto.faithful_winner),
                    ("atomic", dto.atomic_winner),
                ):
                    into[criterion].append(name_of(choice))
                    positional[choice] += 1

            record(judge_wins, judge_positional, verdict, unblind)
            judge_notes.append(f"{name} rep{rep}: {verdict.note}")

            # The unpaired per-claim check. Both arms in one gather: they are
            # independent calls and this is the one place in the probe where two
            # provider calls can overlap without either arm's cost measurement
            # seeing the other (the census closed before the judge ran).
            a_support, c_support = await asyncio.gather(
                _support(di_container, document, a_set),
                _support(di_container, document, c_set),
            )
            for arm, verdicts in (("A", a_support), ("C", c_support)):
                if verdicts is None:
                    support_dropped += 1
                    continue
                for one in verdicts:
                    support[arm][one] += 1
                if verdicts:
                    unsupported = sum(1 for v in verdicts if v != "supported")
                    support_rates[arm].append(unsupported / len(verdicts))

            # The two length controls. `keep` is the smaller set's size, so the
            # fuller arm is the one that gets trimmed and the other is untouched —
            # trimming both would throw away claims for nothing.
            keep = min(len(a_set), len(c_set))
            if len(a_set) > len(c_set):
                longer = "A"
            elif len(c_set) > len(a_set):
                longer = "C"
            else:
                longer = None
            longer_arm_counts[longer or "equal"] += 1
            fuller = a_set if longer == "A" else c_set
            trimmed = _trimmed(fuller, keep, f"{name}-{rep}") if longer else None

            # (1) The re-judge with the counts equal. Same blinding as above, so
            #     its tally is directly comparable to the endpoint's.
            a_matched = trimmed if longer == "A" else a_set
            c_matched = trimmed if longer == "C" else c_set
            matched = await _judge(
                di_container,
                document,
                a_matched if a_is_x else c_matched,
                c_matched if a_is_x else a_matched,
            )
            record(matched_wins, matched_positional, matched, unblind)

            # (2) The judge's length preference itself, measured on one arm's own
            #     output against a trimmed copy of it. Skipped when the counts
            #     already matched: there is no length difference to have an
            #     opinion about, and feeding it two identical sets would only
            #     measure how often it ties.
            if longer is not None:
                trimmed_amounts.append(len(fuller) - keep)
                fuller_is_x = rep % 2 == 0

                def unblind_length(choice: str) -> str:
                    if choice == "tie":
                        return "tie"
                    return "fuller" if (choice == "x") == fuller_is_x else "trimmed"

                length = await _judge(
                    di_container,
                    document,
                    fuller if fuller_is_x else trimmed,
                    trimmed if fuller_is_x else fuller,
                )
                record(length_wins, length_positional, length, unblind_length)

            counts = "  ".join(
                f"{arm} {len(per_rep_candidates[arm][rep]):2d}" for arm in ARMS
            )
            print(
                # "field flips", NOT "gate flips": this counter is over all three
                # fields. Reading it as the keep/drop rate is the misreading that
                # put a 43.3% into the 2026-09-11 mechanism paragraph when that
                # run's whole deciding-field disagreement was five items.
                f"  rep{rep}: candidates {counts}"
                f"   field flips A-vs-B {flips_by_doc[name]['A-vs-B'][0]:2d}"
                f" A-vs-C {flips_by_doc[name]['A-vs-C'][0]:2d} (cumulative)"
                f"   judge self-contained -> {unblind(verdict.self_contained_winner)}"
            )

        # Noise floors, over ALL rep pairs rather than consecutive ones. Same
        # meaning, more comparisons from the same calls — and the floor is what the
        # verdict is read against, so it is the number that can least afford to rest
        # on one pair that happened to agree.
        for arm in ARMS:
            for i in range(REPS):
                for j in range(i + 1, REPS):
                    differing, compared = _flip_rate(
                        _decisions(per_rep[arm][i]), _decisions(per_rep[arm][j])
                    )
                    within[arm][0] += differing
                    within[arm][1] += compared
                    differing, compared = _flip_rate(
                        _gate(per_rep[arm][i]), _gate(per_rep[arm][j])
                    )
                    within_gate[arm][0] += differing
                    within_gate[arm][1] += compared

    waited = time.monotonic() - started

    # --- Report ---------------------------------------------------------------

    def rate(pair) -> Optional[float]:
        return (pair[0] / pair[1]) if pair[1] else None

    def show(pair) -> str:
        value = rate(pair)
        return "not measured" if value is None else f"{value:6.1%} ({pair[0]}/{pair[1]})"

    print(f"\n{'=' * 66}\nwaited {waited:.1f}s")

    print("\nCOST (the thing being bought)")
    # Read this line first: a call that reported no usage is UNMEASURED, not zero,
    # so a shortfall here caps how much the prefill figures can be trusted.
    print("  calls reporting usage   " + "   ".join(
        f"{arm} {measured[arm]}/{calls[arm]}" for arm in ARMS))
    for arm in ARMS:
        print(f"  arm {arm} prefill {prefill[arm]:>10,} tokens over {calls[arm]:3d}"
              f" call(s)   (cache writes {cache_writes[arm]:,})")
    if prefill["A"]:
        for arm in ("B", "C"):
            measured_share = prefill[arm] / prefill["A"]
            print(f"  arm {arm} is {measured_share:.1%} of arm A  ->"
                  f"  {1 / measured_share:.1f}x cheaper AT THESE DOCUMENT SIZES,"
                  f" which is not the regime that matters")
    else:
        print("  arm A reported NO prefill — the census is not wired; ignore this run.")

    # The projection. Arms B and C send a size-INDEPENDENT prefill per call; arm A's
    # carries the source, so the ratio is a function of document size and the
    # ~1k-char documents above understate it by roughly the ratio of their size to a
    # window. Arm A's per-call figure is projected by swapping its own document's
    # source term for a full window's worth — a direct substitution rather than a
    # difference between arms, so it does not assume what the other arms carry.
    projected: dict[str, list[float]] = {"B": [], "C": []}
    print(f"\n  projected to one real window (CHUNK_SIZE = {CHUNK_SIZE:,} chars,"
          f" ~4 chars/token) — ESTIMATE, not a measurement:")
    for name, document in DOCUMENTS.items():
        arms = by_doc.get(name)
        if not arms or not all(arms[arm][1] for arm in ARMS):
            continue
        per_call = {arm: arms[arm][0] / arms[arm][1] for arm in ARMS}
        projected_a = per_call["A"] + (CHUNK_SIZE - len(document)) / 4
        shares = []
        for arm in ("B", "C"):
            share = per_call[arm] / projected_a
            projected[arm].append(share)
            shares.append(f"{arm} {share:5.1%} ({1 / share:4.1f}x)")
        print(f"    {name:<15} A {per_call['A']:8,.0f}/call ->"
              f" {projected_a:9,.0f} at window size;"
              f"  B {per_call['B']:6,.0f}  C {per_call['C']:6,.0f}/call"
              f"  ->  " + "  ".join(shares))

    projected_share = max(projected["C"]) if projected["C"] else None

    print("\nREASONING (the thing at risk)")
    print("  DECIDING fields only (is_assertable + is_substantive) — the verdict"
          " reads from these:")
    for arm in ARMS:
        print(f"    {arm}-vs-{arm}  {show(within_gate[arm])}   <- noise floor")
    for pair in PAIRS:
        label = "positive control" if pair == "A-vs-B" else "THE DECISION"
        print(f"    {pair}  {show(cross_gate[pair])}   <- {label}")
    print("  all three fields, `is_atomic` included (reported, not decisive):")
    for arm in ARMS:
        print(f"    {arm}-vs-{arm}  {show(within[arm])}")
    for pair in PAIRS:
        print(f"    {pair}  {show(cross_flips[pair])}")
    for pair in PAIRS:
        if directions[pair]:
            print(f"  which field moved, and which way ({pair}):")
            for key in sorted(directions[pair], key=lambda k: -directions[pair][k]):
                print(f"    {key:<40} {directions[pair][key]:3d}")
    # WHICH documents move is the prediction, not just how many: if dropping the
    # source matters it should show on the narrative and technical ones and NOT on
    # the self-contained control. Flips spread evenly across all three would mean
    # something other than lost context is moving the gate.
    # BOTH metrics per document, labelled, because these are the numbers that get
    # quoted into a mechanism story and the two differ by an order of magnitude.
    for name in flips_by_doc:
        for pair in PAIRS:
            print(f"              per-doc {name:<15} {pair}"
                  f"   deciding {show(gate_flips_by_doc[name][pair])}"
                  f"   all three {show(flips_by_doc[name][pair])}")
    for arm in ARMS:
        print(f"  candidates  {arm} {total_candidates[arm]:3d} total  {yielded[arm]}")
    print("  opens with unresolved deixis   " + "   ".join(
        f"{arm} {deixis[arm]:3d} (of {total_candidates[arm]})" for arm in ARMS))
    for criterion, votes in judge_wins.items():
        tally = {arm: votes.count(arm) for arm in ("A", "C", "tie")}
        print(f"  judge {criterion:<15} A {tally['A']}  C {tally['C']}  tie {tally['tie']}")
    def positional(split: dict) -> str:
        seen = split["x"] + split["y"]
        return (f"first-shown {split['x']}   second {split['y']}"
                f"   tie {split['tie']}"
                + (f"   ({split['x'] / seen:.0%} to the first"
                   f" — 50% is unbiased)" if seen else ""))

    # Read this before the three lines above. Lopsided here means the judge is
    # rating POSITION, and the alternating labels have spread that evenly across
    # the arms — which looks like "no arm effect" and is really "no signal".
    print(f"  judge positional control   {positional(judge_positional)}")
    print("\n  judge notes:")
    for note in judge_notes:
        print(f"    {note}")

    # --- Is the judge rating faithfulness, or length? -------------------------
    # Built 2026-09-17, after the run above failed its faithfulness endpoint while
    # arm A also happened to yield 6% more candidates. Diagnostic only; see the
    # note at the verdict.
    print("\nLENGTH AS A CONFOUND (does the judge prefer the fuller set?)")
    print(f"  which arm was longer   A {longer_arm_counts['A']}"
          f"   C {longer_arm_counts['C']}"
          f"   equal {longer_arm_counts['equal']} (control skipped)")
    if trimmed_amounts:
        print(f"  candidates trimmed off the fuller set   {trimmed_amounts}"
              f"   (max {max(trimmed_amounts)})")
    if not length_wins["faithful"]:
        print("  every comparison had equal counts, so there was nothing to"
              " control for and the endpoint above cannot be reading length.")
    else:
        print("  same arm on both sides, only the count differs — 'tie' is the"
              " clean result:")
        for criterion, votes in length_wins.items():
            tally = {k: votes.count(k) for k in ("fuller", "trimmed", "tie")}
            # `self_contained` is asked as two COUNTS before it is asked as a
            # winner, and a trimmed set has a smaller count by construction. So a
            # lean to `fuller` there is expected and is not evidence of a length
            # bias; it is evidence the judge is reading the question. Faithfulness
            # is the line that matters, and nothing about it scales with size.
            aside = "   <- expected: it is asked as a count" if (
                criterion == "self_contained") else ""
            print(f"    {criterion:<15} fuller {tally['fuller']}"
                  f"  trimmed {tally['trimmed']}  tie {tally['tie']}{aside}")
        print(f"    positional control   {positional(length_positional)}")
    print("  A against C with the counts equalised (the real comparison, but"
          " trimming discards real claims and which ones is luck):")
    for criterion, votes in matched_wins.items():
        tally = {arm: votes.count(arm) for arm in ("A", "C", "tie")}
        print(f"    {criterion:<15} A {tally['A']}  C {tally['C']}"
              f"  tie {tally['tie']}")
    print(f"    positional control   {positional(matched_positional)}")

    # --- Faithfulness with nothing to compare against -------------------------
    print("\nPER-CLAIM SUPPORT (unpaired: no other set, no position, no ties)")
    if support_dropped:
        print(f"  {support_dropped} call(s) DISCARDED for a verdict list that did"
              f" not line up with the set — those claims are not in the counts")
    for arm in ("A", "C"):
        counts = support[arm]
        total = sum(counts.values())
        if not total:
            print(f"  arm {arm}   nothing measured")
            continue
        unsupported = counts["distorted"] + counts["invented"]
        print(f"  arm {arm}   {unsupported / total:5.1%} not supported"
              f" ({unsupported}/{total})"
              f"   distorted {counts['distorted']}  invented {counts['invented']}")
        # Per-rep spread, because the arms' difference has to be read against how
        # much one arm varies from rep to rep. A gap smaller than that is nothing.
        spread = support_rates[arm]
        if spread:
            print(f"           per-rep  "
                  + " ".join(f"{r:.0%}" for r in spread)
                  + f"   (min {min(spread):.0%}, max {max(spread):.0%})")

    # --- Preregistered verdict ----------------------------------------------

    floors = [f for f in (rate(within_gate[arm]) for arm in ARMS) if f is not None]

    # The instrument's own sensitivity, checked BEFORE the verdict on arm C, because
    # a null from a blunt instrument is not a null. Arm B's effect is known and
    # directional; if it does not reappear, nothing below is evidence.
    control = rate(cross_gate["A-vs-B"])
    control_floors = [f for f in (rate(within_gate["A"]), rate(within_gate["B"]))
                      if f is not None]
    sensitive = (
        control is not None and control_floors and control > max(control_floors)
    )
    print("\nINSTRUMENT SENSITIVITY (arm B is the positive control)")
    if sensitive:
        print(f"  A-vs-B {control:.1%} clears its floors {max(control_floors):.1%}"
              f" — the known effect reproduced, so a null on arm C is readable.")
    else:
        print("  A-vs-B did NOT clear its floors in this run. The 2026-09-11 effect"
              " did not reproduce, so this instrument was not sensitive today and"
              " NO conclusion about arm C follows from the gate rate below.")

    failures: list[str] = []
    # Read against the PROJECTION, per the note at the top of this file: the
    # measured ratio here is a floor set by the documents' size, and judging the
    # change on it would reject a saving that only appears at production scale.
    if projected_share is None:
        failures.append("cost: no prefill recorded")
    elif projected_share >= 0.40:
        failures.append(
            f"cost: even projected to a full window, arm C is {projected_share:.1%}"
            f" of arm A — not under 40%"
        )

    cross = rate(cross_gate["A-vs-C"])
    if cross is not None and floors and cross > max(floors):
        failures.append(
            f"gate: A-vs-C flips {cross:.1%} clear the noise floor"
            f" {max(floors):.1%} — step 2's keep/drop decision DOES move"
            f" without the source"
        )
    # Arm C being less self-consistent than arm A is its own finding, separate from
    # the arms disagreeing: it means dropping the source leaves the gate sitting on
    # a boundary it then samples across, so the same document ingests differently
    # run to run. Worth failing on even if the cross-arm rate is inside the floor.
    floor_a, floor_c = rate(within_gate["A"]), rate(within_gate["C"])
    if floor_a is not None and floor_c is not None and floor_c > floor_a:
        failures.append(
            f"stability: arm C disagrees with ITSELF {floor_c:.1%} of the time"
            f" against arm A's {floor_a:.1%} — the source is stabilising the gate"
        )
    if deixis["C"] > deixis["A"]:
        failures.append(
            f"self-containment: C lost {deixis['C'] - deixis['A']} more candidate(s)"
            f" to unresolved referents"
        )
    faithful_a = judge_wins["faithful"].count("A")
    faithful_c = judge_wins["faithful"].count("C")
    if faithful_a * 2 > len(judge_wins["faithful"]):
        failures.append(
            f"faithfulness: the judge preferred A in {faithful_a} of"
            f" {len(judge_wins['faithful'])} comparisons"
        )
    # The preregistered endpoint above counts ties against itself, so a lopsided
    # split with many ties passes it. That is the threshold as written and it stays
    # as written — but the tie-excluded split is the more informative number, so it
    # is REPORTED and deliberately not promoted to an endpoint after the fact.
    faithful_decided = faithful_a + faithful_c
    if faithful_decided:
        lean = faithful_a / faithful_decided
        note = (
            f"  post-hoc, not an endpoint: excluding ties the judge put"
            f" faithfulness with A in {faithful_a} of {faithful_decided}"
            f" decided comparisons ({lean:.0%})"
        )
        if lean > 0.6 and not any(f.startswith("faithfulness") for f in failures):
            note += ".\n  This leans A while passing the endpoint as written."
        print(note)

    # The faithfulness reading, across all three instruments. DIAGNOSTIC, and
    # deliberately not an endpoint: this probe's discipline is that a reasoning
    # default moves on a preregistered measurement, and an instrument built after
    # seeing a result cannot retire the endpoint it was built to question. What it
    # can do is say whether that endpoint deserves a rerun under a better design.
    fuller_wins = length_wins["faithful"].count("fuller")
    trimmed_wins = length_wins["faithful"].count("trimmed")
    length_decided = fuller_wins + trimmed_wins
    matched_a = matched_wins["faithful"].count("A")
    matched_c = matched_wins["faithful"].count("C")

    def unsupported_rate(arm: str) -> Optional[float]:
        total = sum(support[arm].values())
        if not total:
            return None
        return (support[arm]["distorted"] + support[arm]["invented"]) / total

    print("\n  faithfulness reading (diagnostic, cannot change the verdict below):")
    print(f"    paired judge, the endpoint:  A {faithful_a}  C {faithful_c}"
          f"  tie {len(judge_wins['faithful']) - faithful_a - faithful_c}")
    if length_decided:
        # Say the DENOMINATOR out loud. A 2-0 on eight comparisons is a sign, not
        # a measurement, and the previous wording let it read as one.
        print(f"    length control:  the judge preferred the fuller of two"
              f" identical-provenance sets {fuller_wins} time(s) to"
              f" {trimmed_wins}, on {len(length_wins['faithful'])} comparison(s)"
              f" of which {length_decided} were decided")
    else:
        print("    length control:  no comparison had unequal counts, so the"
              " judge's size preference was not measured at all this run")
    print(f"    counts equalised:  A {matched_a}  C {matched_c}"
          f"  tie {len(matched_wins['faithful']) - matched_a - matched_c}")
    rate_a, rate_c = unsupported_rate("A"), unsupported_rate("C")
    if rate_a is None or rate_c is None:
        print("    per-claim support:  not measured")
    else:
        # The only one of the four with a denominator in the hundreds, and the
        # only one with no nuisance variable. Read against arm A's own rep-to-rep
        # spread: a gap smaller than how much one arm moves by itself is nothing.
        gap = rate_c - rate_a
        own = support_rates["A"]
        swing = (max(own) - min(own)) if len(own) > 1 else None
        line = (f"    per-claim support:  A {rate_a:.1%} unsupported,"
                f" C {rate_c:.1%}  ->  C is {abs(gap) * 100:.1f}pp"
                f" {'worse' if gap > 0 else 'better'}")
        if swing is not None:
            line += (f", against arm A's own rep-to-rep swing of"
                     f" {swing * 100:.1f}pp"
                     f" — {'INSIDE' if abs(gap) <= swing else 'OUTSIDE'} it")
        print(line)

    print()
    if failures:
        print(f"VERDICT: DON'T TAKE arm C — {len(failures)} endpoint(s) failed")
        for failure in failures:
            print(f"  - {failure}")
    elif not sensitive:
        print(
            "VERDICT: NO CALL — every arm-C endpoint passed, but the positive"
            " control did not reproduce, so passing is not evidence. Re-run with"
            " more reps before flipping the default."
        )
    else:
        # A TAKE is PROVISIONAL until it reproduces, and this is not a threshold
        # invented to dislike an answer: the same endpoints on the same code and
        # the same model gave DON'T TAKE and then TAKE on two 2026-09-17 runs, so
        # a single run of this protocol is demonstrably not decisive. The tie rate
        # is what moved (1 tie, then 6) while the judge's lean among decided
        # comparisons held at 82-83% both times, so the faithfulness endpoint's
        # pass/fail turns on how often the judge shrugs. Pool the runs recorded in
        # this file's RESULTS sections before touching the default.
        print(
            "VERDICT: TAKE arm C on THIS RUN — the saving is real, the instrument"
            " was sensitive enough to catch arm B, and no reasoning endpoint moved."
            "\n  PROVISIONAL: this protocol has already returned both answers on"
            " different runs. Pool this run with the RESULTS sections above and"
            " check the per-claim support line before flipping anything."
            " Flip `extraction_step2_carries_source` to False by default."
        )
    print("Record these numbers in this file's RESULTS section.")

    # Instrument wiring only. The verdict above is a MEASUREMENT and must not be
    # an assertion: a probe that fails when the answer is "don't take" cannot
    # report that answer.
    assert all(calls[arm] > 0 for arm in ARMS), "an arm made no calls at all"
    assert len({calls[arm] for arm in ARMS}) == 1, (
        f"arms made different call counts ({calls}) — they are not judging the"
        f" same items and nothing above is paired"
    )
    assert prefill["A"] > prefill["C"] > prefill["B"], (
        f"prefill is not ordered A > C > B ({prefill}), so the arms are not"
        f" carrying what they are supposed to carry and the premise of this whole"
        f" probe is wrong"
    )
