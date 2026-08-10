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


class SessionRecord(BaseModel):
    label: str
    turns: list[TurnRecord] = Field(default_factory=list)
    #: A1.7 only: the journal the model wrote for itself at session end.
    journal_after: Optional[str] = None
    #: A2 only: graph state observed at session end, for the audit trail.
    graph_summary: Optional[str] = None

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
    def collapsed_to_a1(self) -> bool:
        """True when an A2 run built nothing — the result is invalid, not weak.

        Graph-building is model-initiated, so a short or badly-steered
        conversation can leave A2 with an empty graph. Reporting such a run as
        "A2" would silently compare A1 against A1.
        """
        return self.arm is Arm.A2 and not self.all_tool_calls

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
