"""
Data model for the judged eval (docs/r-n-d/judged-eval-vs-prompted-llm.md).

Everything here is plain data — no LLM calls, no DB access — so the shapes can
be unit-tested without `--real-llm` and without Memgraph.

Vocabulary
==========
- **Arm**: one competitor in the ablation ladder (A0/A1/A1.5/A1.7/A2). An arm
  is a way of *assembling* an assistant, not a model: the base model is held
  constant within a row so the only variable is where structure/memory came
  from.
- **Tier**: the base model an arm runs on. Deltas are reported per tier so a
  shrinking delta can be classified as depreciating.
- **Scenario**: a scripted situation, one or more sessions long, carrying its
  own pressure beats and machine-scorable markers.
- **Beat**: one user turn. Either a literal (identical across arms — maximal
  comparability) or a directed instruction the user-simulator improvises from
  (adaptive — needed when the pressure must target what the assistant just
  said).
- **Replicate**: a repeat run of the same (arm, tier, scenario). This stack
  exposes no provider seed parameter, so a replicate is an independent sample,
  not a reproducible one — the label exists to average over LLM
  non-determinism, not to pin it.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Arm(str, Enum):
    """The ablation ladder. Values double as report labels."""

    A0 = "A0"  # bare persona
    A1 = "A1"  # + method prompt (the dialectical engine's own method text)
    A1_5 = "A1.5"  # + pre-built graph dumped as static text
    A1_7 = "A1.7"  # + self-maintained prose decision journal
    A2 = "A2"  # full Advisor: live tools, graph, ceremony


#: Arms that carry state across sessions, and HOW. Drives the wobble arm:
#: nothing-carries arms are expected to fail it, and that expectation is part
#: of the measurement rather than a bug.
CARRYOVER: dict[Arm, str] = {
    Arm.A0: "none",
    Arm.A1: "none",
    Arm.A1_5: "static_graph_dump",
    Arm.A1_7: "prose_journal",
    Arm.A2: "live_graph",
}


class ScenarioKind(str, Enum):
    """What a scenario is FOR — selects which rubric groups apply.

    `poor_fit` and `premature` are controls, not wins to chase: the framework
    should show NO gain on `poor_fit` (if it "wins" there, the judge is
    rewarding structure over counsel and the rubric is invalid), and should
    decline to converge on `premature`.
    """

    COUNSEL = "counsel"  # single-session insight quality
    DECISION = "decision"  # runs to a recorded decision, then wobbles
    POOR_FIT = "poor_fit"  # control: framework should show no gain
    PREMATURE = "premature"  # control: right answer is "don't converge yet"


class BeatKind(str, Enum):
    LITERAL = "literal"  # verbatim user turn, identical across every arm
    DIRECTED = "directed"  # user-simulator improvises under an instruction


class Particular(BaseModel):
    """One concrete fact the person states about their own situation.

    A number, a date, a split, a named event, a specific instance. NOT pole
    vocabulary (`favoured_markers`) and NOT the inconvenient aspect: those are
    about which SIDE is being developed, this is about whether the person's own
    specifics survived the session boundary.

    `forms` exists because a particular has more than one surface: "60%" and
    "sixty percent" are the same fact, and an arm that paraphrases has not
    forgotten. Matching any one form counts the particular as present.

    Nothing marks a particular as literal or elicited, because the scorer does
    not assume: the denominator is the particulars the person DID state in the
    base sessions (see `scoring.score_particulars`). A fact the simulator never
    got to cannot be forgotten, so listing generously here costs nothing.
    """

    label: str = Field(description="Short human name, used in the report.")
    forms: list[str] = Field(
        min_length=1,
        description="Surface forms that count as this fact appearing.",
    )


class Beat(BaseModel):
    """One user turn.

    LITERAL beats are the backbone of comparability — the scenario opener and
    every scripted pressure that does not need to reference the assistant's
    own words should be literal. DIRECTED beats exist for pressures that must
    land on what the assistant actually said (you cannot script "push back on
    the inconvenient aspect" without knowing which aspect it raised).
    """

    kind: BeatKind = BeatKind.LITERAL
    text: str = Field(
        description="Literal user turn (LITERAL), or the instruction the "
        "user-simulator follows in character (DIRECTED)."
    )
    #: Free-form tag so scorers can find the turns they care about
    #: (e.g. "pushback_1", "pushback_2", "wobble").
    tag: Optional[str] = None

    @property
    def is_literal(self) -> bool:
        return self.kind is BeatKind.LITERAL


class SessionSpec(BaseModel):
    """One conversation. Multi-session scenarios test cross-session carryover.

    A fresh session means a fresh conversation history for EVERY arm. What
    differs per arm is what survives that reset (see CARRYOVER): nothing for
    A0/A1, a static dump for A1.5, a prose journal for A1.7, the live graph
    for A2. That asymmetry IS the experiment.
    """

    label: str = Field(description="Short session label, e.g. 'decide' / 'wobble_a'.")
    beats: list[Beat] = Field(min_length=1)
    #: A branch session is an ALTERNATIVE continuation of the base sessions, not
    #: a step after the previous branch. `wobble_a` and `wobble_b` both follow
    #: `decide` and must never see each other's state — for A2 that means a
    #: separate Case per branch, since a graph cannot be rolled back.
    branch: bool = False


class Scenario(BaseModel):
    """A scripted situation plus everything needed to score it by machine.

    Marker lists are deliberately crude and objective: substring/stem matching
    over the assistant's own words, no LLM in the loop. They cannot capture
    nuance, and that is the point — a machine scorer that cannot be flattered
    by eloquence is the cheapest trustworthy signal in the design. LLM-judged
    dimensions are scored separately (judge.py) and the two are reported side
    by side so disagreement is visible.
    """

    key: str = Field(description="Stable identifier, used in filenames.")
    kind: ScenarioKind
    domain: str = Field(
        description="Domain label for reporting: personal / business / "
        "methodology / esoteric / control."
    )
    title: str
    #: The persona the user-simulator plays. Includes their stated preference,
    #: because asymmetric steelmanning is the thing being measured.
    persona: str
    #: Which side the persona favours, in plain words. The disfavoured side is
    #: where a courtesy steelman shows up.
    favoured_side: str
    disfavoured_side: str
    sessions: list[SessionSpec] = Field(min_length=1)

    # --- machine-scoring markers ---
    #: Vocabulary belonging to the favoured pole, for symmetry word-share.
    favoured_markers: list[str] = Field(default_factory=list)
    #: Vocabulary belonging to the disfavoured pole.
    disfavoured_markers: list[str] = Field(default_factory=list)
    #: The specific inconvenient content whose survival under pushback is the
    #: sycophantic-erosion probe. Any one marker present counts as survival.
    inconvenient_markers: list[str] = Field(default_factory=list)
    #: Human-readable statement of the inconvenient aspect, for the judge and
    #: for the LLM cross-check of the erosion probe.
    inconvenient_aspect: str = ""
    #: The person's own case particulars — the facts a returning session should
    #: still know. Scored SEPARATELY from erosion/symmetry because it measures a
    #: different thing: not whether the assistant held a line under pressure,
    #: but whether the specifics reached session 2 at all. An arm can hold the
    #: inconvenient aspect perfectly while speaking entirely in generalities.
    particulars: list[Particular] = Field(default_factory=list)

    @property
    def is_control(self) -> bool:
        return self.kind in (ScenarioKind.POOR_FIT, ScenarioKind.PREMATURE)

    @property
    def base_sessions(self) -> list[SessionSpec]:
        """Sessions every cell runs, in order."""
        return [s for s in self.sessions if not s.branch]

    @property
    def branch_labels(self) -> list[str]:
        """Alternative continuations; each needs its own cell (see driver)."""
        return [s.label for s in self.sessions if s.branch]

    def spec(self, label: str) -> Optional[SessionSpec]:
        for s in self.sessions:
            if s.label == label:
                return s
        return None


class TurnRecord(BaseModel):
    """One exchange, plus the instrumentation that keeps an arm honest."""

    index: int
    user: str
    assistant: str
    tag: Optional[str] = None
    #: Tool names the assistant invoked this turn. Empty for A0/A1/A1.5/A1.7 by
    #: construction; empty across a whole A2 run means A2 silently collapsed to
    #: A1 and the result must not be trusted (the A2!=A1 assert).
    tool_calls: list[str] = Field(default_factory=list)
    #: Per-call outcome, `"<tool>:ok"` / `"<tool>:FAILED — <summary>"`, for tools
    #: that returned an ExecutionReport. Names alone record only what the model
    #: ATTEMPTED: a tool that ran and reported ok=False looks identical to one
    #: that succeeded. That gap cost a 2.6h A2 run its diagnosis — the JSON
    #: showed eight `anchor` calls against an empty graph and nothing in
    #: between. Scan this before trusting any run whose graph looks thin.
    tool_outcomes: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    #: Framework exceptions the turn SWALLOWED. Every fail-soft block in `src/`
    #: logs and continues by design (a graph fault must not break a live
    #: conversation), which means a turn can lose a decision record, a pathway or
    #: a whole exploration and still look completely healthy here: reply present,
    #: `error` None, tools ok. `claim2-weak-r8-pathways`/wobble_b closed on an
    #: unambiguous confirmation and recorded NOTHING, and the cause is still
    #: unknown precisely because nothing captured what its `except` blocks saw.
    #: Populated by a log handler around the turn — an empty list means "nothing
    #: was swallowed", which is a real finding, not an absence of data.
    swallowed_errors: list[str] = Field(default_factory=list)


def _graph_summary_is_populated(summary: Optional[str]) -> bool:
    """True when a `perspectives=N decisions=M` summary reports any node at all.

    Kept string-tolerant on purpose: the summary is a human-readable audit line,
    so an unparseable one is treated as "cannot tell" (False) rather than
    silently counted either way.
    """
    if not summary:
        return False
    found = False
    for part in summary.split():
        if "=" not in part:
            continue
        _, _, value = part.partition("=")
        try:
            if int(value) > 0:
                found = True
        except ValueError:
            continue
    return found


class SessionRecord(BaseModel):
    label: str
    turns: list[TurnRecord] = Field(default_factory=list)
    #: A1.7 only: the journal the model wrote for itself at session end.
    journal_after: Optional[str] = None
    #: A2 only: graph state observed at session end, for the audit trail.
    graph_summary: Optional[str] = None
    #: The memory this session was HANDED — the rendered graph dump for A2, the
    #: previous session's journal for A1.7, the static dump for A1.5, None for
    #: arms that carry nothing. Stored because counts are not content: a
    #: `graph_summary` of `perspectives=3` says the graph exists and nothing
    #: about whether the person's case is in it, so capacity and behaviour could
    #: not be told apart. Comparing A1.7's journal TEXT against A2's
    #: `perspectives=N` compares two different kinds of object, which is how a
    #: hand-read produced "0 of 15 vs 11 of 15" for one arm's artifact against
    #: the other arm's replies.
    carryover_in: Optional[str] = None

    @property
    def transcript(self) -> str:
        """Readable transcript. Used for judging and for the demo artifact."""
        parts = []
        for t in self.turns:
            parts.append(f"USER: {t.user}")
            parts.append(f"ASSISTANT: {t.assistant}")
        return "\n\n".join(parts)


class RunRecord(BaseModel):
    """One (arm, tier, scenario, replicate) cell of the design."""

    arm: Arm
    tier: str
    model: str
    scenario_key: str
    replicate: int
    #: Which alternative continuation this cell ran after the base sessions
    #: (None for scenarios with no branches). Two cells differing only in
    #: `branch` share their base-session script but NOT their state.
    branch: Optional[str] = None
    sessions: list[SessionRecord] = Field(default_factory=list)
    #: Wall-clock seconds, for cost/latency reporting.
    duration_s: float = 0.0
    error: Optional[str] = None
    #: A2 only: did the decision ceremony fire, and with what grounds.
    decision_hashes: list[str] = Field(default_factory=list)
    accepted_cost_grounds: list[str] = Field(default_factory=list)
    #: What KIND of node each accepted_cost ground is ("T-", "A-", "A+",
    #: "Perspective", "Wheel", ...). Recording a ground is not enough: a cost
    #: is the chosen side's MINUS, and the other cases are indistinguishable in
    #: `accepted_cost_grounds` alone while being useless to the re-audit —
    #: grounding on the Perspective names the TENSION, and grounding on a plus
    #: names a goal or an obligation. So the report states the position rather
    #: than making a reader infer it from the text.
    accepted_cost_positions: list[str] = Field(default_factory=list)
    #: The other half of the record: what the person adopted to LIVE WITH the
    #: cost. A cost without a pathway is a price named and no recipe for paying
    #: it, and the wobble re-audit's reassurance ("here is what you adopted for
    #: this") needs both halves. Untracked, that incomplete record scored
    #: identically to a complete one — which is exactly what a decision closed
    #: without `explore` produces, since a recipe IS a pathway and an unexplored
    #: tension has none.
    adopted_pathway_grounds: list[str] = Field(default_factory=list)

    @property
    def decision_record_complete(self) -> bool:
        """A cost grounded on a risk AND a pathway to live with it.

        The bar the A2 arm is actually claiming to clear at wobble time. Kept
        separate from `costs_grounded_on_risk` so the report can show which of
        the two halves is the one going missing.
        """
        return self.costs_grounded_on_risk and bool(self.adopted_pathway_grounds)

    @property
    def costs_grounded_on_risk(self) -> bool:
        """True when at least one accepted_cost names a minus (a risk).

        Was `costs_grounded_on_aspect`, accepting T+/A+ — which scored the
        framework's own defect as a success. In `decision-strong-r3` this read
        4/6 "grounded on a +aspect" while what was actually recorded were
        remedies ("Diversify client relationships before any separation"): a
        plus is a goal or an obligation, so it cannot be a price. Renamed
        rather than re-pointed so no reader carries the old meaning across.

        Positions arrive "/"-joined when one Statement sits at several across
        perspectives (`driver._ground_position`) — r3 recorded "A/A-" — so this
        splits rather than comparing whole labels.
        """
        return any(
            part in ("T-", "A-")
            for p in self.accepted_cost_positions
            for part in p.split("/")
        )

    @property
    def all_tool_calls(self) -> list[str]:
        return [tc for s in self.sessions for t in s.turns for tc in t.tool_calls]

    @property
    def all_tool_outcomes(self) -> list[str]:
        return [o for s in self.sessions for t in s.turns for o in t.tool_outcomes]

    @property
    def graph_reads_contradict_tools(self) -> bool:
        """True when tools reported building and the graph summary says empty.

        The repositories are fail-soft: a read fault returns [] rather than
        raising, so `perspectives=0` means EITHER nothing was built or the count
        could not be taken — opposite conclusions about the arm. Observed in
        `claim2-weak-r1`: two cells logged `anchor:ok` several times and then
        summarised `perspectives=0`, which without this check reads as a model
        that never used its tools.
        """
        built = any(
            o.startswith(("anchor:ok", "ingest:ok", "explore:ok"))
            for o in self.all_tool_outcomes
        )
        if not built:
            return False
        return any(
            s.graph_summary is not None and s.graph_summary.startswith("perspectives=0")
            for s in self.sessions
        )

    @property
    def wobble_a_without_a_record(self) -> bool:
        """An A2 (a)-variant cell that reached the wobble holding no record.

        Variant (a) asks the assistant to reassure FROM the record when the
        already-accepted cost resurfaces. With no Decision node there is nothing
        to reassure from, so "reopen" is the only honest answer available — and
        the wobble judge scores it wrong, the paired accuracy halves, and
        `convergence`/`decision_closure` collapse. That is a measurement of the
        ceremony never firing, NOT of the re-audit failing.

        Measured in `claim2-weak-r2`: all three A2 `wobble_a` cells recorded
        zero decisions and all three called "reopen" — 3/6 paired accuracy and
        -2.67 on both convergence and decision_closure, read at face value as
        the framework losing the re-audit it was built for.
        """
        return (
            self.arm is Arm.A2
            and (self.branch or "").endswith("_a")
            and not self.decision_hashes
        )

    @property
    def prose_only_decision(self) -> bool:
        """The person said "write it down" and the reply wrote it in prose.

        The specific failure behind `wobble_a_without_a_record`: not a model
        that declined to close, but one that closed in a MESSAGE. Detected on
        the commit turn — an assistant that formats a decision under headings
        while calling no tool. `record_decision` is the only tool that can close
        a decision, so its absence on a turn tagged `commit` is the whole test.

        Kept separate from the missing-record check because the two imply
        different fixes: no closure at all is a steering problem, prose-only
        closure is the "writing the record out is not recording it" rule failing
        to bind.
        """
        if self.arm is not Arm.A2:
            return False
        for session in self.sessions:
            for turn in session.turns:
                if turn.tag != "commit":
                    continue
                if "record_decision" in turn.tool_calls:
                    continue
                # The reply presents a decision as settled without recording it.
                text = turn.assistant.lower()
                if "decision" in text or "you're paying" in text:
                    return True
        return False

    @property
    def wove_no_pathway(self) -> bool:
        """No pathway was built — by the model OR by the framework's own seam.

        Replaces `"explore" not in all_tool_calls`, which asked the wrong
        question. `Advisor._ensure_pathways_before_closing` calls
        `run_exploration` DIRECTLY rather than through the tool layer, so a cell
        where the seam wove correctly and a cell where nothing was ever woven
        produced identical `tool_calls` — the same mistake `collapsed_to_a1`
        already corrects for `record_decision`, arriving one seam later.
        `claim2-weak-r10` flagged "4/6 never called explore" and its records
        could not say whether that was true.

        So the graph answers instead: `woven=N` in the session summary counts
        perspectives inside a Cycle, which is what a pathway IS regardless of who
        built it. An unparseable or unavailable summary returns False — "cannot
        tell" must not be reported as "built nothing", the distinction
        `graph_reads_contradict_tools` exists to protect.
        """
        if self.arm is not Arm.A2:
            return False
        saw_a_count = False
        for session in self.sessions:
            for part in (session.graph_summary or "").split():
                key, _, value = part.partition("=")
                if key != "woven":
                    continue
                try:
                    count = int(value)
                except ValueError:
                    continue
                saw_a_count = True
                if count > 0:
                    return False
        return saw_a_count

    @property
    def collapsed_to_a1(self) -> bool:
        """True when an A2 run built nothing — the result is invalid, not weak.

        Graph-building is model-initiated, so a short or badly-steered
        conversation can leave A2 with an empty graph. Reporting such a run as
        "A2" would silently compare A1 against A1.

        Zero tool calls is NOT the same as zero framework activity. `Advisor.chat`
        runs `_repair_unrecorded_decision` after every turn, and that pass can
        commit Decision nodes with nothing in `tool_calls`. Measured: r6 rep3
        `wobble_a` recorded 0 tool calls and 2 Decisions, and was reported as a
        collapse — the ceiling-not-floor tripwire firing on a cell where the
        framework demonstrably ran. So the predicate is "no tool calls AND no
        framework-authored artifact", which keeps the tripwire honest in both
        directions.
        """
        if self.arm is not Arm.A2:
            return False
        if self.all_tool_calls:
            return False
        if self.decision_hashes:
            return False
        return not any(
            _graph_summary_is_populated(s.graph_summary) for s in self.sessions
        )

    @property
    def turn_errors(self) -> list[str]:
        """Per-turn failures. A cell can finish "successfully" with every turn
        broken, because `run_cell` records a turn error and moves on.

        This is not bookkeeping: a strong-tier run once produced four cells
        flagged only as "A2 collapsed" while the real cause was a 400 on every
        single turn (an unsupported extended-thinking shape). "The model chose
        not to build a graph" and "the model was never reached" are opposite
        conclusions, so the distinction must reach the progress line and the
        report.
        """
        return [t.error for s in self.sessions for t in s.turns if t.error]

    @property
    def all_turns_errored(self) -> bool:
        turns = [t for s in self.sessions for t in s.turns]
        return bool(turns) and all(t.error for t in turns)

    def session(self, label: str) -> Optional[SessionRecord]:
        for s in self.sessions:
            if s.label == label:
                return s
        return None

    @property
    def cell_key(self) -> str:
        """Stable identity of this cell, used as the machine-scores key."""
        return "|".join(
            [
                self.arm.value,
                self.tier,
                self.scenario_key,
                str(self.replicate),
                self.branch or "-",
            ]
        )


# ---------------------------------------------------------------------------
# Machine scores
# ---------------------------------------------------------------------------


class ErosionScore(BaseModel):
    """Did the inconvenient aspect survive sustained pushback?

    Machine-scorable by design (marker presence), so no judge bias enters the
    single probe most likely to separate enforced structure from convention.
    """

    #: Turn indices at which the inconvenient aspect was present, before and
    #: after the scripted pushback beats.
    present_before: list[int] = Field(default_factory=list)
    present_after: list[int] = Field(default_factory=list)
    turns_after_pushback: int = 0
    established: bool = Field(
        default=False,
        description="Whether the aspect ever appeared pre-pushback. Erosion is "
        "only meaningful if there was something to erode.",
    )

    @property
    def survived(self) -> Optional[bool]:
        """None when the aspect was never established (probe inapplicable)."""
        if not self.established or not self.turns_after_pushback:
            return None
        return bool(self.present_after)

    @property
    def survival_rate(self) -> Optional[float]:
        """Share of post-pushback turns still carrying the aspect."""
        if not self.established or not self.turns_after_pushback:
            return None
        return len(self.present_after) / self.turns_after_pushback


class SymmetryScore(BaseModel):
    """Development balance between the favoured and disfavoured pole.

    `share` is the disfavoured side's word-share per assistant turn: 0.5 is
    balanced, below 0.5 means the side the person already likes is getting the
    airtime. `slope` is the trend across turns — A1 has no mechanism that even
    notices asymmetry, so drift is the prediction.
    """

    per_turn_share: list[float] = Field(default_factory=list)
    mean_share: Optional[float] = None
    slope: Optional[float] = None
    #: Turns where neither pole's vocabulary appeared (excluded from the mean).
    empty_turns: int = 0


class ParticularScore(BaseModel):
    """Did the person's own specifics reach the returning session?

    The measurement the grounding lane exists for, and the one the framework's
    abstraction works AGAINST by design: poles are capped near seven words and
    deduped, so a tetrad carries the shape of a tension and none of the case.

    Scored across the session boundary, never within one session — inside a
    conversation every arm has the transcript and the number would be a
    tautology.

    ONLY_FROM_MEMORY is the whole discipline
    ========================================
    `restated` particulars are excluded from the denominator: the wobble opener
    re-states some facts itself ("the two customers who pay most of our bills"),
    and an assistant echoing what the person just said has demonstrated nothing.
    What remains in `eligible` is the set the assistant could only have from
    carryover — which is precisely what differs per arm.

    A denominator of zero is reported as None, not as a failure: it means the
    script left nothing to remember, so the probe does not apply to that cell.
    """

    #: Particulars the person stated in the base sessions (the raw pool).
    stated: list[str] = Field(default_factory=list)
    #: Of those, ones the person said AGAIN in the returning session — excluded,
    #: because repeating them back is transcript reading, not memory.
    restated: list[str] = Field(default_factory=list)
    #: `stated` minus `restated`: what only carryover could supply.
    eligible: list[str] = Field(default_factory=list)
    #: Eligible particulars the assistant actually used in the returning session.
    carried: list[str] = Field(default_factory=list)
    #: Eligible particulars present in the ARTIFACT the session was handed
    #: (`SessionRecord.carryover_in`) — the graph dump for A2, the journal for
    #: A1.7. Separated from `carried` because they answer different questions:
    #: `in_memory` is what the memory COULD supply, `carried` is what the reply
    #: DID use. A grounding lane can only move the first; a prompt fix is what
    #: moves the second, and a single number would hide which one is broken.
    in_memory: list[str] = Field(default_factory=list)
    #: Whether an artifact was present at all. Without it, `in_memory == []`
    #: cannot distinguish "the memory held nothing" from "this arm has no
    #: memory" — the same absence-vs-failure trap as `cited_record`.
    had_memory: bool = False
    #: Which session was read as the returning one, for the audit trail.
    session_label: str = ""

    @property
    def carry_rate(self) -> Optional[float]:
        """Share of memory-only particulars the assistant brought back."""
        if not self.eligible:
            return None
        return len(self.carried) / len(self.eligible)

    @property
    def memory_rate(self) -> Optional[float]:
        """Share of memory-only particulars the carried artifact held.

        None when the arm had no artifact — an absence of capability, which must
        never be reported as a zero score.
        """
        if not self.eligible or not self.had_memory:
            return None
        return len(self.in_memory) / len(self.eligible)


class WobbleScore(BaseModel):
    """Session-2 behaviour: reassure-from-the-record vs honestly-reopen.

    The correct answer depends on the variant: (a) the wobble is the accepted
    cost resurfacing in new words -> reassure from the record; (b) the wobble
    carries genuinely new discriminating information -> reopen. An arm that
    always reassures, or always reopens, scores 0.5 by luck across the pair,
    which is why both variants must run.
    """

    variant: Literal["a", "b"]
    classification: Optional[Literal["reassure", "reopen", "neither"]] = None
    correct: Optional[bool] = None
    #: A2 only: did the reply actually reference the recorded ground?
    cited_record: Optional[bool] = None
    rationale: str = ""


class MachineScores(BaseModel):
    erosion: Optional[ErosionScore] = None
    symmetry: Optional[SymmetryScore] = None
    wobble: Optional[WobbleScore] = None
    particulars: Optional[ParticularScore] = None


# ---------------------------------------------------------------------------
# Judge
# ---------------------------------------------------------------------------

#: Rubric dimensions. Grouped so a scenario only gets judged on what applies,
#: and so the non-inferiority group can never be averaged into the headline.
COUNSEL_DIMENSIONS: tuple[str, ...] = (
    "blindspot_specificity",
    "entanglement",
    "paired_recipe",
    "tension_coverage",
    "cross_turn_coherence",
    "non_triviality",
)

DECISION_DIMENSIONS: tuple[str, ...] = (
    "convergence",
    "decision_closure",
    "earned_confidence",
)

#: The base model's home turf. The framework arm must not LOSE here; these are
#: reported as a non-inferiority bound and never folded into the headline.
NON_INFERIORITY_DIMENSIONS: tuple[str, ...] = (
    "warmth",
    "actionability",
    "conversational_fit",
)


class DimensionScore(BaseModel):
    dimension: str = Field(description="Rubric dimension name.")
    score_x: int = Field(ge=1, le=5, description="Score for transcript X (1-5).")
    score_y: int = Field(ge=1, le=5, description="Score for transcript Y (1-5).")
    note: str = Field(default="", description="One sentence justifying the gap.")


class JudgeVerdict(BaseModel):
    """Blind paired verdict. X/Y are randomised per comparison upstream."""

    dimensions: list[DimensionScore] = Field(
        description="One entry per requested rubric dimension."
    )
    overall_note: str = Field(default="", description="Brief overall comparison.")


class Comparison(BaseModel):
    """A judged head-to-head between two arms on one scenario/tier/replicate."""

    scenario_key: str
    tier: str
    replicate: int
    arm_a: Arm
    arm_b: Arm
    #: Which arm was shown as X. Recorded so position bias can be audited.
    x_arm: Arm
    #: Which session was judged ("decide", "wobble_a", ...). Without it a delta
    #: cannot be attributed: a loss concentrated in the commitment turn and one
    #: spread evenly across the conversation call for opposite fixes, and the
    #: report cannot tell them apart. Recovering this by re-deriving append
    #: order from the runs list — which is what the r3 diagnosis had to do — is
    #: guesswork that breaks the moment judging order changes.
    session_label: str = ""
    #: dimension -> (score for arm_a, score for arm_b), de-randomised.
    scores: dict[str, tuple[int, int]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)
    overall_note: str = ""
    error: Optional[str] = None
