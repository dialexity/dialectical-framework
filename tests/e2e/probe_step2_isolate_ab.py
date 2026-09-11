"""
Does step 2 of thesis extraction need the source text in its history?

WHAT IS BEING DECIDED
=====================
`ThesisExtraction._step2_identify_candidates` fans out over step 1's content
items with `self._conversation.isolate()`, and `isolate()` COPIES the message
list — which at that point holds step 1's prompt, and step 1's prompt holds the
whole `<source_text>`. So a window sends its source once for step 1 and then
again for every one of its `count + 2` gate calls.

`probe_ingest_cost.py` priced that: **step 2 is 207,047 tokens, 75% of
everything the document's SIZE costs**, plus a cache-write surcharge nobody
reads. Switching step 2 to a FRESH facilitator would cut ~7 full-text sends per
extraction to 1 — the single biggest token win left on the ingestion path.

It was never taken, on purpose, because it is a REASONING change: step 2 decides
whether an item is assertable/substantive/atomic and decomposes compound items,
and today it can look at the source to do that. Nobody knew whether it USES it.
This probe answers that and nothing else.

THE DESIGN, AND WHY IT IS PAIRED
================================
Step 1 runs ONCE per document, and both arms then judge the SAME content items:

    arm A (today)      `conversation.isolate()`  — system prompt + step 1's
                       prompt (the whole source) + step 1's answer, per call
    arm B (candidate)  fresh `ConversationFacilitator` with the SAME system
                       prompt and NO history — the item and nothing else

Pairing matters more than sample size here. Step 1 is itself stochastic, and if
each arm ran its own step 1 the arms would be judging different items and any
difference would be unattributable. This way the ONLY variable is what step 2
can see.

**The gate is stochastic, so a raw A-vs-B disagreement rate means nothing on its
own.** Every arm therefore runs `REPS` times and the report prints three
numbers: A-vs-A, B-vs-B (the noise floors) and A-vs-B. An arm effect exists only
if the cross rate clears both floors. This is the whole reason the probe repeats
rather than running once per arm.

WHAT IS MEASURED
================
- **prefill tokens per arm** (`call_census`) — the thing being bought.
- **gate decisions per item** — `(is_assertable, is_substantive, is_atomic)`,
  compared within and across arms as above.
- **candidate yield** — how many atomic theses survive, per arm.
- **self-containment**, two ways: a mechanical leading-deixis count (a candidate
  starting "This/It/They..." has lost its referent) and a blinded judge. Both were
  expected to carry the signal and NEITHER DID — see RESULTS. They stay as
  regression guards; the finding came from the gate fields.
- The judge is **blinded and its labels alternate by rep**, and its raw
  first-vs-second split is reported, because alternating alone would convert a
  positional preference into a fake 50/50 between the arms instead of exposing it.
  It turned out to be biased, which is why that control is not optional.

The gate metric is read over `is_assertable` and `is_substantive` ONLY.
`is_atomic` is on the DTO and read by no code, so a flip in it cannot reach a
candidate list; it is reported separately. Mixing it in materially changed the
verdict on the first pass.

The documents are chosen for this question rather than for size: one whose
sentences are self-contained (the control — if B is fine anywhere it is here),
one narrative with referents spread across sentences, one technical with terms
defined once and used later. If dropping the source hurts, it should hurt those
two and not the first.

THE COST FIGURE IS PROJECTED, AND HAS TO BE
===========================================
The documents above are ~1k chars, because the reasoning question needs referents
that fit in one readable page. At that size the source is a SMALL part of a step-2
prompt (system prompt + item + instructions dominate), so the measured saving is
around 1.4x and says nothing about production. The saving is size-dependent by
construction: arm B's prefill per call is FIXED, while arm A's carries the source.

So the probe measures the per-call decomposition and projects it to one real
window (`CHUNK_SIZE`, 40,000 chars). The projection is labelled an ESTIMATE and
assumes ~4 chars/token; it is there to check the recorded ~7x is the right order,
not to replace `probe_ingest_cost`'s direct measurement of it.

PREREGISTERED READING
=====================
TAKE the change if (a) B's PROJECTED prefill at window size is under 40% of A's,
and (b) no reasoning regression: cross-arm gate flips do not clear the noise
floors, B's leading-deixis count is no worse than A's, and the judge does not
prefer A on faithfulness in a majority of comparisons. Anything else: DON'T TAKE,
and the print says which endpoint failed.

This probe measures; it does not change `_step2_identify_candidates`. It asserts
only that its own instrument is wired and that arm A still mirrors the real
function (`_the_real_function_still_matches_arm_a`) — because the day the real
one stops using `isolate()`, this file's arm A is measuring nothing.

Run: `poetry run pytest tests/e2e/probe_step2_isolate_ab.py -s --real-llm`
Env:  DIALEXITY_PROBE_S2_REPS (default 2)

RESULTS (2026-09-11, REPS=5, haiku-4-5 work / sonnet-5 judge, 3 documents)
=========================================================================
**VERDICT: DON'T TAKE as a straight swap.** The saving is real and large; the
gate's keep/drop decision moves, deterministically and in ONE direction.

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
SAYS SO. Arm B cannot see the earlier text, so it admits it. The effect
concentrates where that reading predicts — per-document cross-arm flips were
technical 43.3%, self-contained 16.7%, narrative 0.0% — the technical document
being the one that defines terms once and then references them. Candidate yield
shows the same thing from the other end: on that document A kept 8-11 and B kept
13-16.

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

WHAT THIS LEAVES OPEN (untested here, and the obvious next move): the gate needs
SOME sense of what the document already established, but there is no reason it
needs the whole source to get it. Feeding step 2 the other content items from
step 1, or a short digest, would plausibly keep the substance judgement at close
to arm B's price. That is a third arm, not a variation on these two, and nobody
has measured it.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from typing import Literal, Optional

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

# --- The documents, chosen for the failure mode under test ---------------------

#: Control. Every sentence stands alone, so step 2 has no reason to want the
#: source. If B degrades HERE, the gate is using the source for something other
#: than resolving referents.
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


# --- The two arms -------------------------------------------------------------


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


async def _arm_isolate(
    concern: ThesisExtraction, items: list[ContentItemDto]
) -> list[CandidateCheckDto]:
    """Arm A — what ships today. Byte-for-byte `_step2_identify_candidates`."""
    tasks = [
        concern._conversation.isolate().submit(
            response_model=CandidateCheckDto,
            user_content=concern._step2_prompt(item.content, item.content_type),
        )
        for item in items
    ]
    return list(await asyncio.gather(*tasks))


async def _arm_fresh(
    concern: ThesisExtraction, items: list[ContentItemDto]
) -> list[CandidateCheckDto]:
    """Arm B — the candidate change.

    The system prompt is KEPT; only step 1's history goes. Dropping the system
    prompt too would be a different and much larger change, and it is not the
    one that was priced.
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


def _candidates(checks: list[CandidateCheckDto]) -> list[str]:
    """The concern's own collection rule: gate, then dedup preserving order."""
    out: list[str] = []
    for check in checks:
        if check.is_assertable and check.is_substantive:
            out.extend(check.atomic_theses)
    return list(dict.fromkeys(out))


def _decisions(checks: list[CandidateCheckDto]) -> list[tuple[bool, bool, bool]]:
    return [(c.is_assertable, c.is_substantive, c.is_atomic) for c in checks]


def _gate(checks: list[CandidateCheckDto]) -> list[tuple[bool, bool]]:
    """Only the fields that DECIDE anything.

    `_candidates` — and `_step2_identify_candidates`, which it mirrors — keeps an
    item on `is_assertable and is_substantive`. `is_atomic` is returned by the DTO
    and read by nobody, so a flip in it changes no downstream output. Counting it
    as a decision flip makes the reasoning metric fire on a difference that cannot
    reach a candidate list, which is why this is measured apart from `_decisions`.
    """
    return [(c.is_assertable, c.is_substantive) for c in checks]


def _flip_rate(
    left: list[tuple[bool, bool, bool]], right: list[tuple[bool, bool, bool]]
) -> tuple[int, int]:
    """Per-item decisions that differ, over items compared."""
    pairs = list(zip(left, right))
    return sum(1 for a, b in pairs if a != b), len(pairs)


def _the_real_function_still_matches_arm_a() -> None:
    """Arm A must be what ships, or this probe compares two of its own inventions.

    Checked structurally rather than by calling `_step2_identify_candidates`,
    which returns only the merged candidate list and would hide the per-item gate
    decisions the whole analysis rests on.
    """
    source = inspect.getsource(te.ThesisExtraction._step2_identify_candidates)
    assert "self._conversation.isolate()" in source, (
        "step 2 no longer fans out over `isolate()`, so arm A is not the shipped"
        " behaviour and this probe measures nothing. Re-read the change before"
        " trusting any number below."
    )
    assert "self._step2_prompt(item.content, item.content_type)" in source, (
        "step 2's prompt call changed shape; arm A copies it verbatim and must be"
        " updated with it."
    )


@pytest.mark.real_llm
@pytest.mark.asyncio
@pytest.mark.timeout(3600)
# Deliberately NOT @traced — serializing `di_container` HANGS (CLAUDE.md).
async def test_probe_step2_isolate_ab(di_container):
    _the_real_function_still_matches_arm_a()

    logging.getLogger("dialectical_framework").setLevel(logging.WARNING)

    print(f"\nwork model:  {DEFAULT_TIER_WEAK}")
    print(f"judge model: {DEFAULT_TIER_STRONG}")
    print(f"documents:   {len(DOCUMENTS)}   reps per arm: {REPS}   count: {COUNT}")
    if REPS < 2:
        print(
            "  NOTE: REPS < 2, so there is NO noise floor and a cross-arm"
            " difference cannot be attributed. Raise DIALEXITY_PROBE_S2_REPS."
        )

    # Accumulators, per arm.
    prefill: dict[str, int] = {"A": 0, "B": 0}
    cache_writes: dict[str, int] = {"A": 0, "B": 0}
    calls: dict[str, int] = {"A": 0, "B": 0}
    measured: dict[str, int] = {"A": 0, "B": 0}
    yielded: dict[str, list[int]] = {"A": [], "B": []}
    deixis: dict[str, int] = {"A": 0, "B": 0}
    total_candidates: dict[str, int] = {"A": 0, "B": 0}
    cross_flips = [0, 0]
    within: dict[str, list[int]] = {"A": [0, 0], "B": [0, 0]}
    #: The same three comparisons over the DECIDING fields only. `is_atomic` is
    #: returned and never read, so these are the rates the verdict is read from.
    cross_gate = [0, 0]
    within_gate: dict[str, list[int]] = {"A": [0, 0], "B": [0, 0]}
    #: Which field moved and which way, so a flip can be attributed rather than
    #: just counted. Keyed field -> "A_true_B_false" / "A_false_B_true".
    directions: dict[str, int] = {}
    judge_wins = {"self_contained": [], "faithful": [], "atomic": []}
    #: The judge's RAW choices, before unblinding. A judge that mostly picks the
    #: first set shown has a positional bias, and alternating the labels by rep
    #: only converts that bias into a fake 50/50 split between the arms — it does
    #: not detect it. This is the control that detects it.
    judge_positional = {"x": 0, "y": 0, "tie": 0}
    judge_notes: list[str] = []
    #: Per-document, per-arm (prefill, calls). The projection needs the per-call
    #: figure against a KNOWN document size, which the aggregate cannot give.
    by_doc: dict[str, dict[str, list[int]]] = {}
    #: Cross-arm flips per document, printed separately because the prediction is
    #: about WHICH documents move: the self-contained control should not.
    flips_by_doc: dict[str, list[int]] = {}

    started = time.monotonic()

    for name, document in DOCUMENTS.items():
        print(f"\n--- {name} ({len(document):,} chars) " + "-" * 30)

        with using_model(di_container, DEFAULT_TIER_WEAK):
            concern, items = await _step1(document)
        print(f"  step 1 -> {len(items)} content item(s)")
        if not items:
            print("  NOTE: step 1 found nothing; this document contributes nothing.")
            continue

        per_rep: dict[str, list[list[CandidateCheckDto]]] = {"A": [], "B": []}
        per_rep_candidates: dict[str, list[list[str]]] = {"A": [], "B": []}
        by_doc[name] = {"A": [0, 0], "B": [0, 0]}
        flips_by_doc[name] = [0, 0]

        for rep in range(REPS):
            for arm, runner in (("A", _arm_isolate), ("B", _arm_fresh)):
                with using_model(di_container, DEFAULT_TIER_WEAK):
                    with call_census() as census:
                        checks = await runner(concern, items)
                # `CallRecord.prefill_tokens`' definition: everything the provider
                # processed, however it was billed. Cache writes are counted in —
                # `isolate()`'s copied source is what pays that surcharge, so
                # excluding them would understate exactly what is under test.
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

            differing, compared = _flip_rate(
                _decisions(per_rep["A"][rep]), _decisions(per_rep["B"][rep])
            )
            cross_flips[0] += differing
            cross_flips[1] += compared
            flips_by_doc[name][0] += differing
            flips_by_doc[name][1] += compared

            gate_differing, gate_compared = _flip_rate(
                _gate(per_rep["A"][rep]), _gate(per_rep["B"][rep])
            )
            cross_gate[0] += gate_differing
            cross_gate[1] += gate_compared

            for a_check, b_check in zip(per_rep["A"][rep], per_rep["B"][rep]):
                for field in ("is_assertable", "is_substantive", "is_atomic"):
                    a_value = getattr(a_check, field)
                    b_value = getattr(b_check, field)
                    if a_value != b_value:
                        way = "A_true_B_false" if a_value else "A_false_B_true"
                        directions[f"{field} {way}"] = (
                            directions.get(f"{field} {way}", 0) + 1
                        )

            # Blinded, with the label assignment alternating by rep.
            a_is_x = rep % 2 == 0
            set_x = per_rep_candidates["A" if a_is_x else "B"][rep]
            set_y = per_rep_candidates["B" if a_is_x else "A"][rep]
            with using_model(di_container, DEFAULT_TIER_STRONG):
                judge_conversation = ConversationFacilitator()
                judge_conversation.set_system_prompt(_JUDGE_SYSTEM)
                verdict = await judge_conversation.submit(
                    response_model=JudgeDto,
                    user_content=_judge_prompt(document, set_x, set_y),
                )

            def unblind(choice: str) -> str:
                if choice == "tie":
                    return "tie"
                chose_x = choice == "x"
                return "A" if chose_x == a_is_x else "B"

            judge_wins["self_contained"].append(unblind(verdict.self_contained_winner))
            judge_wins["faithful"].append(unblind(verdict.faithful_winner))
            judge_wins["atomic"].append(unblind(verdict.atomic_winner))
            for raw in (verdict.self_contained_winner, verdict.faithful_winner,
                        verdict.atomic_winner):
                judge_positional[raw] += 1
            judge_notes.append(f"{name} rep{rep}: {verdict.note}")

            print(
                f"  rep{rep}: A {len(per_rep_candidates['A'][rep]):2d} candidate(s)"
                f"   B {len(per_rep_candidates['B'][rep]):2d}"
                f"   gate flips A-vs-B {differing}/{compared}"
                f"   judge self-contained -> {unblind(verdict.self_contained_winner)}"
            )

        # Noise floors, over ALL rep pairs rather than consecutive ones. Same
        # meaning, more comparisons from the same calls — and the floor is what the
        # verdict is read against, so it is the number that can least afford to rest
        # on one pair that happened to agree.
        for arm in ("A", "B"):
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
    print(f"  calls reporting usage   A {measured['A']}/{calls['A']}"
          f"   B {measured['B']}/{calls['B']}")
    print(f"  arm A prefill {prefill['A']:>10,} tokens over {calls['A']:3d} call(s)"
          f"   (cache writes {cache_writes['A']:,})")
    print(f"  arm B prefill {prefill['B']:>10,} tokens over {calls['B']:3d} call(s)"
          f"   (cache writes {cache_writes['B']:,})")
    if prefill["A"]:
        measured_share = prefill["B"] / prefill["A"]
        print(f"  arm B is {measured_share:.1%} of arm A  ->"
              f"  {1 / measured_share:.1f}x cheaper AT THESE DOCUMENT SIZES,"
              f" which is not the regime that matters")
    else:
        print("  arm A reported NO prefill — the census is not wired; ignore this run.")

    # The projection. Arm B's per-call prefill is size-INDEPENDENT; arm A's carries
    # the source, so the ratio is a function of document size and the ~1k-char
    # documents above understate it by roughly the ratio of their size to a window.
    projected: list[float] = []
    print(f"\n  projected to one real window (CHUNK_SIZE = {CHUNK_SIZE:,} chars,"
          f" ~4 chars/token) — ESTIMATE, not a measurement:")
    for name, document in DOCUMENTS.items():
        arms = by_doc.get(name)
        if not arms or not arms["A"][1] or not arms["B"][1]:
            continue
        a_per_call = arms["A"][0] / arms["A"][1]
        b_per_call = arms["B"][0] / arms["B"][1]
        # What arm A carries and arm B does not: the source plus step 1's answer.
        # Only the source scales with document size, so the answer is held fixed and
        # the source term replaced with a full window's worth.
        source_est = len(document) / 4
        history_est = max(0.0, (a_per_call - b_per_call) - source_est)
        projected_a = b_per_call + CHUNK_SIZE / 4 + history_est
        share = b_per_call / projected_a
        projected.append(share)
        print(f"    {name:<15} A {a_per_call:8,.0f}/call  B {b_per_call:8,.0f}/call"
              f"  ->  at window size B is {share:5.1%} of A ({1 / share:4.1f}x)")

    projected_share = max(projected) if projected else None

    print("\nREASONING (the thing at risk)")
    print("  DECIDING fields only (is_assertable + is_substantive) — the verdict"
          " reads from these:")
    print(f"    A-vs-A  {show(within_gate['A'])}   <- noise floor")
    print(f"    B-vs-B  {show(within_gate['B'])}   <- noise floor")
    print(f"    A-vs-B  {show(cross_gate)}   <- arm effect, if any")
    print("  all three fields, `is_atomic` included (reported, not decisive):")
    print(f"    A-vs-A  {show(within['A'])}")
    print(f"    B-vs-B  {show(within['B'])}")
    print(f"    A-vs-B  {show(cross_flips)}")
    if directions:
        print("  which field moved, and which way:")
        for key in sorted(directions, key=lambda k: -directions[k]):
            print(f"    {key:<34} {directions[key]:3d}")
    # WHICH documents move is the prediction, not just how many: if dropping the
    # source matters it should show on the narrative and technical ones and NOT on
    # the self-contained control. Flips spread evenly across all three would mean
    # something other than lost context is moving the gate.
    for name, pair in flips_by_doc.items():
        print(f"              per-doc {name:<15} {show(pair)}")
    print(f"  candidates  A {total_candidates['A']:3d} total  {yielded['A']}")
    print(f"              B {total_candidates['B']:3d} total  {yielded['B']}")
    print(f"  opens with unresolved deixis   A {deixis['A']:3d}   B {deixis['B']:3d}"
          f"   (of {total_candidates['A']} / {total_candidates['B']})")
    for criterion, votes in judge_wins.items():
        tally = {arm: votes.count(arm) for arm in ("A", "B", "tie")}
        print(f"  judge {criterion:<15} A {tally['A']}  B {tally['B']}  tie {tally['tie']}")
    # Read this before the three lines above. Lopsided here means the judge is
    # rating POSITION, and the alternating labels have spread that evenly across
    # the arms — which looks like "no arm effect" and is really "no signal".
    decided = judge_positional["x"] + judge_positional["y"]
    print(f"  judge positional control   first-set-shown {judge_positional['x']}"
          f"   second {judge_positional['y']}   tie {judge_positional['tie']}"
          + (f"   ({judge_positional['x'] / decided:.0%} to the first set"
             f" — 50% is unbiased)" if decided else ""))
    print("\n  judge notes:")
    for note in judge_notes:
        print(f"    {note}")

    # --- Preregistered verdict ----------------------------------------------

    failures: list[str] = []
    # Read against the PROJECTION, per the note at the top of this file: the
    # measured ratio here is a floor set by the documents' size, and judging the
    # change on it would reject a saving that only appears at production scale.
    if projected_share is None:
        failures.append("cost: no prefill recorded")
    elif projected_share >= 0.40:
        failures.append(
            f"cost: even projected to a full window, arm B is {projected_share:.1%}"
            f" of arm A — not under 40%"
        )

    cross = rate(cross_gate)
    floors = [f for f in (rate(within_gate["A"]), rate(within_gate["B"]))
              if f is not None]
    if cross is not None and floors and cross > max(floors):
        failures.append(
            f"gate: cross-arm flips {cross:.1%} clear the noise floor"
            f" {max(floors):.1%} — step 2's keep/drop decision DOES move"
            f" without the source"
        )
    # Arm B being less self-consistent than arm A is its own finding, separate from
    # the arms disagreeing: it means dropping the source leaves the gate sitting on
    # a boundary it then samples across, so the same document ingests differently
    # run to run. Worth failing on even if the cross-arm rate is inside the floor.
    floor_a, floor_b = rate(within_gate["A"]), rate(within_gate["B"])
    if floor_a is not None and floor_b is not None and floor_b > floor_a:
        failures.append(
            f"stability: arm B disagrees with ITSELF {floor_b:.1%} of the time"
            f" against arm A's {floor_a:.1%} — the source is stabilising the gate"
        )
    if deixis["B"] > deixis["A"]:
        failures.append(
            f"self-containment: B lost {deixis['B'] - deixis['A']} more candidate(s)"
            f" to unresolved referents"
        )
    faithful_a = judge_wins["faithful"].count("A")
    faithful_b = judge_wins["faithful"].count("B")
    if faithful_a * 2 > len(judge_wins["faithful"]):
        failures.append(
            f"faithfulness: the judge preferred A in {faithful_a} of"
            f" {len(judge_wins['faithful'])} comparisons"
        )
    # The preregistered endpoint above counts ties against itself, so a lopsided
    # split with many ties passes it. That is the threshold as written and it stays
    # as written — but the tie-excluded split is the more informative number, so it
    # is REPORTED and deliberately not promoted to an endpoint after the fact.
    faithful_decided = faithful_a + faithful_b
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

    print()
    if failures:
        print("VERDICT: DON'T TAKE — " + str(len(failures)) + " endpoint(s) failed")
        for failure in failures:
            print(f"  - {failure}")
    else:
        print(
            "VERDICT: TAKE — the saving is real and no reasoning endpoint moved."
            " Switch `_step2_identify_candidates` to a fresh facilitator."
        )
    print("Record these numbers in this file's RESULTS section.")

    # Instrument wiring only. The verdict above is a MEASUREMENT and must not be
    # an assertion: a probe that fails when the answer is "don't take" cannot
    # report that answer.
    assert calls["A"] > 0 and calls["B"] > 0, "an arm made no calls at all"
    assert calls["A"] == calls["B"], (
        f"arms made different call counts ({calls['A']} vs {calls['B']}) — they are"
        f" not judging the same items and nothing below is paired"
    )
    assert prefill["A"] > prefill["B"], (
        "arm A did not prefill more than arm B, so `isolate()` is not carrying the"
        " source and the premise of this whole probe is wrong"
    )
