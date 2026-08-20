"""Does a recorded `accepted_cost` price the side the person CHOSE?

    poetry run pytest tests/e2e/probe_cost_side.py -s              # free half
    poetry run pytest tests/e2e/probe_cost_side.py --real-llm -s   # + classifier

WHY THE ENDPOINT IS LABEL-FREE, AND WHY THAT IS THE WHOLE POINT
===============================================================
The question this probe was built to answer started as "is A- under-recorded as
a price?", motivated by `agents/advisor/system_prompts.py::_INTERNAL_MODEL`
naming `T-` fourteen times and `A-` twice, with both operative rules written in
T-side terms only ("Every position generates its own T- necessarily", "it is
what the pathway (Ac+) has to work on").

That framing was wrong, and the reason is the one thing about a tetrad that
makes label-counting useless: **T and A are a labelling convention, not a fact.**
Read the antithesis as the thesis and its minus IS the T- of that reading. Since
`anchor`'s thesis parameter is documented as "what the person holds or
champions", a correctly-behaving system should record the T--labelled aspect
almost every time — so the archive's 93-T- / 7-A- split (n=100, see the free
test below) is what CORRECT looks like, not a symptom. Any endpoint defined over
the label would have measured the naming convention and reported it as a defect.

So the endpoint never names a position. For each record it asks:

    Did the person commit to the side whose price was recorded,
    or to the side that price belongs to the OTHER of?

This is answerable from the transcript, it is invariant under relabelling, and
it is the only form in which the `_INTERNAL_MODEL` asymmetry can actually bite.
The prompt's T-side-only language is CORRECT as a frame convention — "the side
in front of you is T, its price is T-". It can only mislead where the stored
labels stop aligning with that convention, which happens two ways:

  1. `ingest` assigns T/A from source material, not from the person's stance.
  2. The person decides AGAINST the side they opened with, at which point the
     price is the other labelled pole's minus.

In both cases a model following the LABEL records the wrong statement, and a
model following the SEMANTICS records the right one. That is the discrimination
this probe measures.

General form, for the systemic map: **an endpoint defined over a name that is
free to be swapped measures the naming, not the behaviour.** Before counting a
position, ask whether relabelling the tetrad would change the count.

HOW THE CHOSEN SIDE IS RECOVERED WITHOUT CIRCULARITY
====================================================
`rendering.decision_ground_line` appends a condition clause to an accepted_cost
line: "<cost> — arises when <HELD> is held without <REMEDY>", where HELD is the
neutral pole of the side the RECORD says was chosen and REMEDY is the opposing
side's constructive aspect (`rendering.py::_accepted_cost_condition`). So the
stored line already names, in plain text, the course the record claims the
person took.

The classifier is given that HELD text plus the person's OWN turns and the
rationale, and asked which way the person actually committed. The commitment
evidence comes from the transcript, not from the label, so the judgement is not
circular: HELD is the record's claim, the turns are the ground truth, and a
disagreement between them is the finding.

Records with no condition clause cannot be resolved this way — the clause is
suppressed when a shared minus sits at several positions and the decision's own
grounds do not disambiguate it. They are reported as UNRESOLVABLE and never
pooled with a pass, for the same reason `probe_rationale_integrity` refuses to
render 0/0 as 0%.

WHY THE POPULATION IS DEFINED BY THE CLAUSE AND NOT BY THE POSITION
===================================================================
The obvious filter is `accepted_cost_positions`, and it does not work.
`driver.py` merges both fields as independent SETS:

    record.accepted_cost_grounds  = sorted(set(...) | set(costs))
    record.accepted_cost_positions = sorted(set(...) | set(positions))

so the two lists have no positional correspondence — two distinct cost lines
sharing one position collapse to a single position entry, and 35 archived runs
carry unequal lengths for exactly that reason. Nothing already published is
wrong (`RunRecord.costs_grounded_on_risk` and `report.py` both ask only whether
ANY position is a minus, which is set-safe), but a per-line position cannot be
recovered from the archive, and a probe that zipped them would mis-attribute.

The clause is a stricter filter anyway: `rendering._accepted_cost_condition`
emits it only when the ground's relationship type is `T_MINUS` or `A_MINUS`, so
**a condition clause is proof the ground is a minus** — no position lookup
needed, and no dependence on a field that was never paired. The position tally
below is printed as run-level context only, and labelled as a set.

An earlier ad-hoc pass at this count reported n=100 by zipping `decision_hashes`
against the two cost lists. Those lengths differ too (one hash per decision,
zero or one cost per decision), so the zip mispaired. n is 87 rows, 68 of them
clause-bearing. Recorded because it is the third distinct way this archive has
produced an inflated count from a plausible-looking zip.

PRE-REGISTRATION (written before any classifier ran, 2026-08-20)
===============================================================
Population: every unique (round, arm, tier, scenario, replicate, branch,
cost-line) accepted_cost in `results/*.json` that carries a condition clause,
which is exactly the set of grounds sitting at T- or A- (see the section above).
Rounds are keyed by filename with the `-runs` / `-rejudged` sidecars stripped —
the archive keeps duplicate copies and an earlier ad-hoc count of this same
archive came out exactly double for missing that (`probe_rationale_integrity`
records the same bug). 131 accepted_cost lines total, n = 88 clause-bearing,
which is what the classifier sees.

The thresholds below were fixed when n was believed to be 77, and are left at
those ABSOLUTE counts now that the corrected loader reports 88. Restating a
pre-registered bar after the denominator moves is how a bar stops being one; and
the direction is conservative anyway — 5 of 88 is a lower rate than 5 of 77, so
the defect branch got harder to trip, not easier.

Primary endpoint: PRICES_REJECTED — records where the person committed to the
side opposed to HELD, i.e. the recorded price belongs to the road not taken.

Decision rule, fixed in advance:
  * DEFECT CONFIRMED     PRICES_REJECTED >= 5 of the clause-bearing population.
                         Five, not one: a classifier disagreeing with the
                         record on 1-2 of 77 is expected noise, and a 5/77
                         floor rate is already worth a prompt clause.
  * EXONERATED           PRICES_REJECTED <= 2 AND >= 15 records show the person
                         choosing against the side they opened with. Without
                         that second condition the labels never diverged from
                         the frame convention, so nothing was tested.
  * UNDERPOWERED         PRICES_REJECTED <= 2 with fewer than 15 divergent
                         records. Reported as UNTESTED, never as clean.

Pre-declared confound: the rationale is written by the same model that chose the
ground, so a model that mis-assigned the side may have written a rationale
consistent with its own error. That biases toward finding NO mismatch, which is
why the person's own turns are supplied alongside and why a null here is weak
evidence rather than proof. The `opened_against` count is the honest denominator
and is printed whatever the endpoint does.

The classifier runs on the JUDGE model (`DIALEXITY_E2E_JUDGE`), not on either
tier under test — the same independence rule `judge.py` documents, and it
matters more here than usual, since what is being classified is one model's
choice of ground.

RESULT (fable-5 judge, n = 88, 2026-08-20)
==========================================
The pre-registered bar FIRED and the number does not survive reading. Recorded
here in full, because the branch that printed is not the finding.

  run 1 (first classifier wording): chosen 50 / rejected 8 / unclear 30
  run 2 (wording fixed, see below): chosen 73 / rejected 7 / unclear 0 / ill_posed 8

Both runs printed DEFECT CONFIRMED. Re-reading all 7 of run 2 against the
transcripts by hand gives FOUR genuine record defects and three classifier false
positives. Four is below the floor of five. The pre-registered rule does not
fire on the adjudicated count, and the honest verdict is the power branch, not
the endpoint.

The four genuine ones, all A2 (the population is 100% A2 — only the framework arm
records an accepted_cost, so arm concentration carries no signal), all
cofounder_equity, all weak tier, in two adjacent rounds:
  * r15-voice/rep1  held "Secure anchor accounts BEFORE removing cofounder"
                    cost "Immediate buyout WITHOUT anchor accounts -> revenue cliff"
                    -> prices the rush, which is the course HELD refuses.
  * r15-voice/rep2  held "Buy out, consolidate full ownership"
                    cost "Indefinite retention as minority shareholder"
  * r16-floor/rep2  held "Solo ownership through buyout"
                    cost "Founders indefinitely retain collective control"
  * r16-floor/rep3  held "Retain cofounder in key customer relationships" while
                    the person said "I'm buying him out. That's the decision,
                    it's final" -> here HELD is misrecorded, which is a worse
                    defect than a mispriced cost and a different one.

WHY THE INSTRUMENT WAS WRONG THE FIRST TIME, since the fix generalises: run 1's
prompt asked whether the recorded cost was "a price they are actually paying".
An accepted cost is not a bill being paid — it is how the chosen course
DEGENERATES when pushed one-sidedly. So a person who had already mitigated their
own risk read as disowning it, and correct minuses were filed as the other
side's. That is what 30 `unclear` was: not ambiguity in the archive, an
inapplicable question. Run 2 states the definition, says mitigation does not move
the cost across the opposition, and gives one worked contrast per side; `unclear`
went to zero.

The fix did NOT fully take, and this is the part to distrust in any re-run: all
three remaining false positives are the same mitigation-reading error, and
ladder-return-r18 quotes the person's own mitigation ("not the lowest number I
could force") as evidence that "Forcing buyout terms regardless of consent" is
not their cost. It is a textbook T-. A definition stated in the prompt did not
displace the auditor's prior about what a cost is.

TWO FINDINGS THE ENDPOINT DID NOT ASK FOR, both worth more than it:

1. `opened_against` = 0 of 88, and that is a property of the BENCH, not of the
   framework. Every scenario in `scenarios.py` pins one `favoured_side` the
   persona holds from first turn to last; none scripts a reversal. The mechanism
   this probe set out to test — labels diverging from the "T = the person's side"
   convention because the person chooses against their opening side — is
   therefore STRUCTURALLY absent from the archive, not merely unobserved. The
   `_INTERNAL_MODEL` T-side asymmetry in `advisor/system_prompts.py` stays
   UNTESTED by this route no matter what the endpoint prints. Testing it needs a
   scenario that scripts a reversal; nothing in `results/` can substitute.

2. `ill_posed` = 8 of 88 is a real generation-layer defect and not noise. Six of
   the eight have a cost that RESTATES the chosen course and names no
   degeneration at all ("Buy out cofounder, run company solo" as the cost of
   "Buy out the cofounder now"); two have a HELD that is a circumstance rather
   than a stance ("Two anchor CEOs, 60% revenue, relate only personally"). Both
   shapes mean the tetrad pole carried no overdevelopment, which is upstream of
   anything the Advisor prompt says.

So: the asymmetry question came back UNTESTED (finding 1), and the probe surfaced
a different, measurable defect on the way (findings above + 2) — 4 mispriced and
8 non-minus accepted costs out of 88, concentrated in the weak tier.
"""

from __future__ import annotations

import asyncio
import collections
import glob
import json
import os
import re
from pathlib import Path
from typing import Literal, Optional

import pytest
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from e2e.config import E2EConfig
from e2e.modelctx import using_model

_RESULTS = Path(__file__).parent / "results"

#: The marker `rendering.ACCEPTED_COST_CONDITION_MARKER` writes. Duplicated as a
#: literal rather than imported: this probe reads an ARCHIVE, and the archive
#: holds text rendered by the version of the renderer that ran at the time.
#: Importing the constant would silently re-point the parse at today's wording
#: and drop every older row without saying so.
_CLAUSE = " — arises when "
_HELD_WITHOUT = re.compile(r"^(?P<held>.+?) is held without (?P<remedy>.+)$")
#: `- accepted cost: [[hash]] <text>`
_COST_LINE = re.compile(r"^- accepted cost:\s*(?:\[\[(?P<hash>[0-9a-f]+)\]\]\s*)?(?P<text>.*)$")

_PREREG_DEFECT_FLOOR = 5
_PREREG_EXONERATE_CEILING = 2
_PREREG_MIN_DIVERGENT = 15


class _Record(BaseModel):
    """One archived accepted_cost, with everything the classifier needs."""

    round_slug: str
    arm: str
    tier: str
    scenario: str
    replicate: int
    branch: Optional[str] = None
    #: The run's accepted_cost positions as a SET — descriptive only. Not
    #: attributable to this cost line; see the module docstring.
    run_positions: list[str] = Field(default_factory=list)
    cost_text: str
    held: Optional[str] = None
    remedy: Optional[str] = None
    rationales: list[str] = Field(default_factory=list)
    user_turns: list[str] = Field(default_factory=list)

    @property
    def key(self) -> str:
        return (
            f"{self.round_slug}|{self.arm}|{self.tier}|{self.scenario}|"
            f"{self.replicate}|{self.branch}|{self.cost_text[:60]}"
        )


def _round_slug(filename: str) -> str:
    name = filename[:-5] if filename.endswith(".json") else filename
    for suffix in ("-runs", "-rejudged", "-rejudge"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def _load() -> list[_Record]:
    """Every T-/A- accepted_cost in the archive, deduplicated."""
    by_key: dict[str, _Record] = {}
    for path in sorted(glob.glob(str(_RESULTS / "*.json"))):
        try:
            payload = json.loads(Path(path).read_text())
        except Exception:  # noqa: BLE001 - a malformed sidecar must not stop the count
            continue
        slug = _round_slug(Path(path).name)
        for run in payload.get("runs") or []:
            grounds = run.get("accepted_cost_grounds") or []
            if not grounds:
                continue
            # NOT zipped against `accepted_cost_positions`: driver.py set-unions
            # the two fields independently, so there is no line-to-position
            # correspondence to recover (35 archived runs have unequal lengths
            # for that reason). The run's positions are carried whole, as the set
            # they are, purely for descriptive reporting.
            run_positions = sorted(set(run.get("accepted_cost_positions") or []))
            user_turns = [
                t.get("user") or ""
                for session in run.get("sessions") or []
                for t in session.get("turns") or []
                if t.get("user")
            ]
            for ground in grounds:
                head, _, clause = ground.partition(_CLAUSE)
                match = _COST_LINE.match(head.strip())
                cost_text = (match.group("text") if match else head).strip()
                held = remedy = None
                if clause:
                    parsed = _HELD_WITHOUT.match(clause.strip())
                    if parsed:
                        held = parsed.group("held").strip()
                        remedy = parsed.group("remedy").strip()
                record = _Record(
                    round_slug=slug,
                    arm=str(run.get("arm")),
                    tier=str(run.get("tier")),
                    scenario=str(run.get("scenario_key")),
                    replicate=int(run.get("replicate") or 0),
                    branch=run.get("branch"),
                    run_positions=run_positions,
                    cost_text=cost_text,
                    held=held,
                    remedy=remedy,
                    rationales=list(run.get("decision_rationales") or []),
                    user_turns=user_turns,
                )
                by_key.setdefault(record.key, record)
    return list(by_key.values())


_SYSTEM_PROMPT = """You are auditing one decision record from a counselling transcript.

A decision record names an ACCEPTED COST. Read it precisely: it is the way the
course the person CHOSE degenerates when that course is pushed one-sidedly. It
is a standing risk that belongs to their own choice — NOT a bill already paid,
and NOT a prediction that the risk will land.

Two consequences, and the first is where auditors go wrong:

- A person who has SEEN the risk, planned around it, mitigated it, or argued it
  down still owns it. Their choice is what generates it. Mitigation does not
  move the cost to the other side; it only makes it smaller. Do not read "they
  addressed this" as "this is not theirs".
- A cost that names what happens if they take the OTHER course is wrong, however
  true it is. That is the price of the road not taken, and it tells a later
  reader the opposite of the truth.

Worked contrast, for a person who chose to buy their cofounder out:

- "Chaotic solo rule with no accountability check" — CORRECT. Overdevelopment of
  buying out. Still correct if they have already hired a board to prevent it.
- "Cofounder's customer relationships lost when he leaves" — CORRECT. Also an
  overdevelopment of buying out, and still correct if they have a transition plan.
- "Partnership resentment festers unaddressed" — WRONG SIDE. That degenerates
  from KEEPING him, which they declined.
- "Delaying the buyout until accounts are secured stalls the company" — WRONG
  SIDE when the record claims they chose to secure accounts first: it prices
  moving fast, which is the course they declined.

The record claims the person committed to this course:

    {held}

The record says taking that course costs them:

    {cost}

The record says that cost arises because the following is not in place:

    {remedy}

Here is what the person themselves said, in order, in their own words:

{turns}

Here is the rationale that was written onto the record. Treat it with suspicion:
it was written by the same process that chose the cost, so if that process
mis-assigned the side, this text may agree with its own error. The person's own
words above outrank it.

{rationales}

Decide which of these the transcript supports:

- "prices_chosen": the recorded cost is a way the course named above degenerates.
  Use this even if the person has already mitigated or discounted that risk.
- "prices_rejected": the recorded cost is a way the OPPOSITE course degenerates —
  the one they turned down. Includes the case where the cost describes what
  happens if they act without the precondition the course named above insists on.
- "ill_posed": the text above does not name a course the person chose between
  alternatives — it states a circumstance, a fact about their situation, or a
  neutral description with no direction — so there is no chosen side for the cost
  to belong to. Also use this when the cost itself names no degeneration, just a
  restatement of the course.
- "unclear": a course and a cost are both present and readable, but the
  transcript genuinely does not let you tell which side the cost degenerates from.

Separately, report whether the person ended up choosing AGAINST the position
they opened the conversation with. Judge this from their first turns versus their
last: someone who arrives leaning one way and commits the other way is the case
that matters. If they never leaned, or held the same line throughout, that is
not choosing against.

Judge only what the transcript shows. Do not reward a well-written rationale."""


class _SideVerdict(BaseModel):
    """Literal order matters: the mock brain fills the FIRST allowed value, so
    "unclear" leads — a mocked run must not manufacture a finding."""

    verdict: Literal["unclear", "ill_posed", "prices_chosen", "prices_rejected"] = Field(
        description="Which side of the opposition the recorded cost degenerates from."
    )
    opened_against: bool = Field(
        description="True when the person committed against the position they "
        "opened the conversation with."
    )
    evidence: str = Field(
        description="The person's own words that settle it — quoted, one or two "
        "short fragments, not a summary."
    )


def _render_turns(record: _Record, *, cap: int = 14) -> str:
    """The person's turns, first and last kept when there are too many.

    Opening AND closing turns are what `opened_against` needs; dropping either
    end would make that field unanswerable while leaving it required.
    """
    turns = [t.strip() for t in record.user_turns if t.strip()]
    if len(turns) > cap:
        head, tail = turns[: cap // 2], turns[-(cap - cap // 2) :]
        turns = head + ["[... middle turns omitted ...]"] + tail
    return "\n\n".join(f"PERSON: {t}" for t in turns) or "(no turns recorded)"


def _prompt(record: _Record) -> str:
    return _SYSTEM_PROMPT.format(
        held=record.held or "(not recorded)",
        cost=record.cost_text,
        remedy=record.remedy or "(not recorded)",
        turns=_render_turns(record),
        rationales="\n\n".join(record.rationales) or "(no rationale recorded)",
    )


# --------------------------------------------------------------------------- #
# The free half: the population, printed so the pre-registration is auditable
# without spending anything.
# --------------------------------------------------------------------------- #


def test_the_population_matches_the_preregistration() -> None:
    records = _load()
    with_clause = [r for r in records if r.held]
    run_positions = collections.Counter(
        p for r in records for p in r.run_positions
    )

    print(f"\n=== population (free, no model) ===")
    print(f"accepted_cost lines in the archive : {len(records)}")
    print(f"clause-bearing => a minus, and classifiable : {len(with_clause)}")
    print(f"UNRESOLVABLE (no condition clause) : {len(records) - len(with_clause)}")
    print(
        "\nRun-level position SET (descriptive only — driver.py set-unions this\n"
        "field, so it cannot be attributed to a cost line):"
    )
    for name, count in run_positions.most_common():
        print(f"  {name:14s} {count}")
    print(
        "\nAnd the split is NOT the endpoint even as context. T and A are a\n"
        "labelling convention: relabel the tetrad and it inverts. The endpoint\n"
        "asks whether the cost prices the side the person CHOSE."
    )

    by_round = collections.Counter(r.round_slug for r in with_clause)
    print("\nclassifiable records by round:")
    for name, count in sorted(by_round.items()):
        print(f"  {name:40s} {count}")

    print("\n=== one rendered classifier prompt (the first record) ===")
    if with_clause:
        print(_prompt(with_clause[0])[:2400])

    assert records, "archive has no accepted_cost rows — did results/ move?"
    assert with_clause, "no record carries a condition clause; parse is broken"


# --------------------------------------------------------------------------- #
# The paid half.
# --------------------------------------------------------------------------- #


@pytest.mark.real_llm
@pytest.mark.asyncio
async def test_the_recorded_cost_prices_the_chosen_side(di_container) -> None:
    records = [r for r in _load() if r.held]
    limit = int(os.environ.get("PROBE_COST_SIDE_LIMIT") or 0)
    if limit:
        # Printed, not silent: a partial run that reads like a full one is the
        # "no silent caps" failure the bench keeps re-learning.
        print(f"\n!! PROBE_COST_SIDE_LIMIT={limit} — {len(records)} available")
        records = records[:limit]
    if not records:
        pytest.skip("no clause-bearing accepted_cost rows in the archive")

    judge_model = E2EConfig.from_env().judge_model
    print(f"\n=== classifier model: {judge_model} ===")
    print(f"=== records: {len(records)} ===")

    semaphore = asyncio.Semaphore(6)

    async def classify(record: _Record) -> tuple[_Record, Optional[_SideVerdict]]:
        async with semaphore:
            conversation = ConversationFacilitator()
            conversation.set_system_prompt(_prompt(record))
            try:
                with using_model(di_container, judge_model):
                    verdict = await conversation.submit(
                        _SideVerdict,
                        "Classify this record.",
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"  !! {record.key[:70]}: {type(exc).__name__}: {exc}")
                return record, None
            return record, verdict

    results = await asyncio.gather(*(classify(r) for r in records))

    tally = collections.Counter()
    divergent = 0
    errors = 0
    rejected: list[tuple[_Record, _SideVerdict]] = []
    for record, verdict in results:
        if verdict is None:
            errors += 1
            continue
        tally[verdict.verdict] += 1
        if verdict.opened_against:
            divergent += 1
        if verdict.verdict == "prices_rejected":
            rejected.append((record, verdict))

    print("\n=== endpoint ===")
    print(f"prices_chosen    : {tally['prices_chosen']}")
    print(f"prices_rejected  : {tally['prices_rejected']}   <-- primary endpoint")
    print(f"ill_posed        : {tally['ill_posed']}")
    print(f"unclear          : {tally['unclear']}")
    print(f"classifier errors: {errors}")
    print(f"\nopened_against (person chose against the side they opened with): {divergent}")
    # Read this as a property of the ARCHIVE, not of the framework. Every scenario
    # in scenarios.py pins one `favoured_side` the persona holds from first turn to
    # last; none scripts a reversal. So a low count here is what the bench was built
    # to produce, and the power branch below is the honest verdict, not the endpoint.
    print(
        "  (scenarios.py pins a fixed favoured_side per scenario and never scripts\n"
        "   a reversal, so this count is bounded by the bench's design)"
    )

    # Every verdict printed, not only the findings. A high `unclear` share would
    # make the endpoint uninformative rather than null, and that is only visible
    # if the classifier's reasoning on those rows is on the page.
    print("\n=== per record ===")
    for record, verdict in results:
        if verdict is None:
            continue
        print(
            f"\n  [{verdict.verdict}{' / opened_against' if verdict.opened_against else ''}] "
            f"{record.round_slug} / {record.arm} / {record.scenario} "
            f"/ rep{record.replicate} / {record.branch}"
        )
        print(f"    held     : {record.held}")
        print(f"    cost     : {record.cost_text}")
        print(f"    evidence : {verdict.evidence}")

    if rejected:
        print("\n=== records whose cost prices the ROAD NOT TAKEN ===")
        for record, verdict in rejected:
            print(f"\n  {record.round_slug} / {record.arm} / {record.scenario} "
                  f"/ rep{record.replicate} / {record.branch}")
            print(f"    record says held : {record.held}")
            print(f"    recorded cost    : {record.cost_text}")
            print(f"    evidence         : {verdict.evidence}")

    if tally["ill_posed"]:
        print("\n=== records with no chosen side to price (ill-posed) ===")
        for record, verdict in results:
            if verdict is None or verdict.verdict != "ill_posed":
                continue
            print(f"\n  {record.round_slug} / {record.arm} / {record.scenario} "
                  f"/ rep{record.replicate} / {record.branch}")
            print(f"    record says held : {record.held}")
            print(f"    recorded cost    : {record.cost_text}")
            print(f"    evidence         : {verdict.evidence}")

    scored = sum(tally.values())
    # `ill_posed` rows are excluded from the rate: a record that names no chosen
    # side cannot price the right one or the wrong one, so counting it in the
    # denominator would dilute the endpoint with rows it does not apply to. The
    # pre-registered bars are absolute counts, so this changes no branch — it only
    # keeps the printed rate honest.
    decidable = scored - tally["ill_posed"]
    print(f"\ndecidable records (excluding ill_posed): {decidable}/{scored}")
    print("\n=== verdict against the pre-registered rule ===")
    if tally["prices_rejected"] >= _PREREG_DEFECT_FLOOR:
        print(
            f"DEFECT CONFIRMED: {tally['prices_rejected']}/{scored} price the "
            f"rejected side (floor was {_PREREG_DEFECT_FLOOR})."
        )
    elif tally["prices_rejected"] <= _PREREG_EXONERATE_CEILING:
        if divergent >= _PREREG_MIN_DIVERGENT:
            print(
                f"EXONERATED: {tally['prices_rejected']}/{scored} mispriced with "
                f"{divergent} divergent records — the labels DID diverge from the "
                f"frame convention and the model followed the semantics."
            )
        else:
            print(
                f"UNDERPOWERED / UNTESTED: only {tally['prices_rejected']}/{scored} "
                f"mispriced, but just {divergent} records show the person choosing "
                f"against their opening side (needed {_PREREG_MIN_DIVERGENT}). "
                f"Absence of mispricing here cannot distinguish a correct model "
                f"from an archive that never exercised the case."
            )
    else:
        print(
            f"INDETERMINATE: {tally['prices_rejected']}/{scored} sits between the "
            f"pre-registered ceiling ({_PREREG_EXONERATE_CEILING}) and floor "
            f"({_PREREG_DEFECT_FLOOR}). Neither branch fires; more n is the answer, "
            f"not a re-read of these."
        )

    # No assertion on the endpoint: this is a MEASUREMENT, and a probe that fails
    # when the framework misbehaves would make the number un-runnable exactly when
    # it is most interesting. It fails only if it could not measure at all.
    assert scored, "no record was classified — every call errored"
