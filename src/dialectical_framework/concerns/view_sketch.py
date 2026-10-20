"""
The Consultant's view: the structure of its own conversation, drawn by the
same mind that is holding it.

WHY A TURN, NOT AN EXTRACTION
=============================
The `Consultant` (`agents/consultant/consultant.py`) has no graph, so
`graph/views.py` has nothing to read for it. The first version of this module
answered `exploration_view()` by handing the PERSON's turns to a fresh, separate
conversation and asking it to derive the tensions from scratch. That was the
wrong shape twice over. A view asked for mid-conversation must show what the
conversation has ESTABLISHED — the tension the counselor named and the person
agreed to — and a stranger reading half the transcript can disagree with the
prose on screen. And the ask often IS a request to reason: "show me a
perspective for that thesis" means find the antithesis, build the four aspects,
name the axes, and only then draw; on the Advisor that work is the tools', on
this head it can only be the model's own turn.

So the view is a STRUCTURED TURN on the consultant's own conversation: same
system prompt (method + persona), full history, both sides. What the turn
builds is kept in the history as the consultant's own words (`history_text`),
so the next turn can be asked about a corner it just drew. The turn thinks
(`format_mode="json"` is the one structured shape the provider lets think —
`ConversationFacilitator`), because building a tetrad in one shot is the
heaviest reasoning a structured call is asked to do here.

WHY BOTH SIDES ARE MATERIAL HERE, AND ONLY THE PERSON'S FOR THE MIGRATION
=========================================================================
`migrate_consultation` plants from the person's turns only, because it writes
structure the person will be held to and the replies are counsel, not
statements of the situation. A view writes nothing and shows the person the
structure they have been talking through — the counselor's framing is exactly
what they reacted to. Same transcript, two purposes, two rules; neither is
wrong for the other.

WHAT THE GRAPH PATH HAS THAT THIS DOES NOT
==========================================
Everything that makes a tetrad a checked one: no HS gate, no complementarity,
no SP/DV, no `PerspectiveValidation`, no dedup, no persistence. The output
shape is `graph/views.py::ExplorationView` with `nexus_hash` None — one
visualiser serves both heads — and it is terminology-free BY CONSTRUCTION
(no hash, alias or score exists to give; `without_terminology()` is a no-op).
The view BEFORE the upgrade, not a lighter version of the checked one.
"""

from __future__ import annotations

from typing import Optional, Sequence

from pydantic import BaseModel, Field

from dialectical_framework.concerns.antithesis_extraction import \
    _OPPOSING_POSITION_ASK
from dialectical_framework.concerns.aspect_generation import (
    PLUS_RESTATEMENT_CHECK, is_axis_name)
from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.views import (ExplorationView,
                                               PerspectiveView, PoleView)

#: The most tensions one view holds. Policy, not config: a view with more
#: than a handful of tetrads on it stops being readable; four is also the
#: default `max_wheel_layer`, the most tensions the graph path arranges
#: together. Nobody deploys a different number.
VIEW_SKETCH_MAX_PERSPECTIVES = 4


# --- DTOs ---------------------------------------------------------------


class ViewSketchPerspectiveDto(BaseModel):
    """One tension as a flat tetrad: texts only, no scores.

    Flat on purpose. `TetradDto` nests an `AspectDto` under each position
    because it carries scores; here there are none to carry, and the flatter
    the schema the less often the model drops a branch (the note on
    `TetradDto` itself). No score fields: a number here would be an unchecked
    guess dressed as a measurement, and the view drops numbers anyway.

    A position not yet worked out is left EMPTY, not invented: a view of
    "the two poles" is a tetrad with four blank corners, and the view shows it
    as unfinished rather than filled in.

    Tried and reverted (2026-10-02): two `*_takes_up` text fields, each ahead
    of its plus, naming what the OTHER pole is for that the plus delivers — a
    verification step made into output, aimed at the restated-A+ shape
    ("Ownership builds equity", 10/80 plus slots on this turn, 7% on the
    one-shot build). It worked on its target and broke the tetrad: restatement
    0/80, antitheses 40/40 positions, and coherence 25/40 → 15/40 (paired 6
    gained / 15 lost) with compromise pluses 18 → 23 of 40 — a plus made to
    carry the other pole no longer satisfies "T+ without A+ yields T-". The
    archive registered exactly this over-correction as the secondary risk of
    any restatement fix (`probe_plus_takeup`); this is its measurement
    (`tests/e2e/probe_view_turn_ask.py`, tag `takeup`;
    docs/dev-notes/antithesis-selection.md). Restatement at 7–12% stays open;
    the next lever must be measured on coherence first.
    """

    thesis: str = Field(description="T — the position, in the person's own terms.")
    antithesis: str = Field(
        description=(
            "A — what T is in tension with, in the person's own terms. Empty if "
            "the ask stops at the thesis."
        )
    )
    t_plus_vs_a_minus_axis: str = Field(
        description=(
            "The single dimension on which T+ and A- are opposite ends "
            "(e.g. 'closeness'). Empty when those two are not drawn."
        )
    )
    t_plus: str = Field(
        description=(
            "T+ — the THESIS developed constructively, so that what A is for stays "
            "possible alongside it. T's own side developed — never T blended with A, "
            "made conditional on it, or the middle between the two. Derived from T; "
            "the positive end of the axis above. A position held, not a move to "
            "make. Empty when not drawn."
        )
    )
    a_minus: str = Field(
        description=(
            "A- — the ANTITHESIS overdeveloped one-sidedly, with T underdeveloped. "
            "Derived from A, never by negating T+; the negative end of the axis "
            "above. Empty when not drawn."
        )
    )
    a_plus_vs_t_minus_axis: str = Field(
        description=(
            "The single dimension on which A+ and T- are opposite ends. Empty when "
            "those two are not drawn."
        )
    )
    a_plus: str = Field(
        description=(
            "A+ — the ANTITHESIS developed constructively, so that what T is for "
            "stays possible alongside it. A's own side developed — never A blended "
            "with T, made conditional on it, or the middle between the two. Derived "
            "from A; the positive end of the axis above. A position held, not a move "
            "to make. Empty when not drawn."
        )
    )
    t_minus: str = Field(
        description=(
            "T- — the THESIS overdeveloped one-sidedly, with A underdeveloped. "
            "Derived from T, never by negating A+; the negative end of the axis "
            "above. Empty when not drawn."
        )
    )


class ViewSketchDto(BaseModel):
    """The tensions to draw, most central to the person's situation first."""

    tensions: list[ViewSketchPerspectiveDto] = Field(
        description=(
            "The tensions the view shows, most central first. Empty when "
            "nothing in the conversation supports one yet."
        )
    )


# --- The request (the user prompt of the view turn) -----------------------

#: How a tetrad is built when a one-shot call builds one — the same procedure
#: the graph path gives `AspectGeneration._tetrad_prompt`, stated once here and
#: shared by the view turn and `concerns/tetrad_sketch.py`, so the two
#: one-shot builders cannot drift apart.
#:
#: Step 1's two measured sentences (2026-10-12, `probe_decided_stance.py`; the
#: story is on `PLUS_RESTATEMENT_CHECK`, which carries the same rule as the
#: step-3 check): a plus LEAVES the other pole's good possible rather than
#: delivering it, and an aspect is a POSITION rather than a move. The second
#: is what took A+ from 75% to 94% own-strength and coherence from 72% to 91%
#: on decided stances — the failures it removes are imperatives ("Leave a path
#: back that she must earn"), and a move that answers both sides at once is a
#: compromise by construction. It is also where the layering is stated to the
#: writer: positions live in the tetrad, moves in the Transformation.
#: What the thesis IS, for a writer that finds it in free words. Measured
#: without it (`tests/e2e/probe_question_entry.py`, 2026-10-04, 20 questions
#: through the view turn): the tetrad was statement-grade (CC 17/20, a genuine
#: opposing position 18/20) but T echoed the QUESTION in 6/20 — "Why should I
#: keep paying for his phone when he never calls?" came back as T "Why keep
#: paying when he never calls me" — so the card showed the person a question
#: as their own position. Shared by the view turn and `tetrad_sketch_prompt`
#: (its free-thesis branch; a GIVEN thesis is kept as given); a host's intake
#: gate reads the same constant (the alsotrue app's `StanceCapture`), so the
#: writers and the gate say the same thing about what a stance is. Re-run with it: the echo went to 0/20 and the view turn declined
#: 3 of 4 informational questions it had drawn before; a third example that
#: named the lean of "why do I keep hiring people like me" was then removed
#: because the writer used that line as BOTH poles on its own utterance
#: (one item, unmeasured deletion, said so). Story: the alsotrue app repo, docs/lab-notes-entry.md.
#:
#: The last sentence — WHICH claim when the words hold several — is from the
#: first app's second handoff (2026-10-20, `docs/handoff-2026-10-20-thesis-choice.md`):
#: a six-sentence polemic holding four claims and a concession came back as a
#: tetrad about its mildest sub-claim ("society has the right to ask"), while
#: the demand the person would sign ("stop mass migration") sat in no corner.
#: Every figure above was taken on one-sentence, one-claim inputs, where the
#: question never arose. UNMEASURED: to be run on a set of long multi-claim
#: inputs (`tests/e2e/probe_view_turn_ask.py` once there is a case set), with
#: the question-echo figure above re-checked, since it is the same constant.
#: A host's intake gate reads this text too (`systemic-map.md` 0d), so its
#: cut moves with it — by design: the gate's cut is what the writer reads as T.
THESIS_IS_A_STANCE = """The thesis (T) is a STANCE: something the person holds, wants or is about to do, written as a claim they could say in the first person — never their question restated, never a description of what happens to them. When they asked a question, T is the answer their wording leans to: "Why should I keep paying for his phone when he never calls?" carries "I should stop paying for his phone"; "Isn't it time we stopped standups?" carries "We should stop standups". A behaviour described is not yet a stance; the stance is what the person holds about it. When the question is genuinely open between options ("Zurich or Vilnius?"), T is one of those options held as a stance. A request for information ("what is the best way to learn Spanish?") carries no stance at all. When the words hold SEVERAL claims, T is the one the person would sign — the conclusion or demand the rest leads to — not a premise or a hedge on the way to it ("we have the right to ask" is the run-up to the demand that follows), and not a claim they concede in passing ("not only X but also Y" concedes X; their stance is Y)."""

TETRAD_BUILD_PROCEDURE = f"""Building a tetrad, when you build one — as its two diagonal contradiction pairs (T+ vs A-, A+ vs T-).
Each aspect has one fixed parent: T+ and T- develop T; A+ and A- develop A.
For each pair:
1. Derive each aspect from ITS OWN parent — a plus develops that parent so that what the other pole is for stays POSSIBLE alongside it, not so that it delivers it; a minus overdevelops that parent one-sidedly, with the other pole absent. Each aspect is a POSITION held or a good someone values, never a move to make: the moves come later, from the way through the tension.
2. Then name the **axis** — the single dimension on which the two aspects are opposite ends, so they cannot both hold at once.
3. Re-read both aspects against step 1 for two distinct failures. (a) Wrong parent: if one is really the OTHER parent developed, rewrite it from its own parent. (b) {PLUS_RESTATEMENT_CHECK}"""


#: What the thesis is when the HOST already has it and wants it kept word for
#: word. Distinct from `tetrad_sketch_prompt`'s given-thesis line, which asks
#: for the position "worded in the person's own terms, {max_words} words or
#: fewer" — a condensation, which is right for `anchor` (the model named the
#: position, the graph stores a headline) and wrong for a host that shows the
#: person their OWN sentence as their position (the first app, 2026-10-12: the
#: card displays the typed words while T was a seven-word recomposition of
#: them). So this one forbids the rewording the other one invites, and the
#: framework does not rely on it being obeyed: `Consultant.exploration_view`
#: writes the given text back over the drawn one (the pin is in code; this
#: text only stops the writer building the rest of the tetrad around a position
#: it has quietly reworded).
THESIS_IS_FIXED = """The thesis (T) is GIVEN, in the person's own words, and it is FIXED: carry it into the view exactly as it stands — do not reword, shorten, sharpen or generalise it, and do not put a different position in its place. Everything else in the tetrad is built around it as given."""



#: How much of the person's own words the view turn's JUDGE reads (characters,
#: newest turns kept whole). The judge never sees T or A, so without context
#: it scores the four aspects' coherence against nothing: the persisted path
#: and the one-shot build pass their material, and the view turn passed ""
#: until 2026-10-13 (the first app's handoff, §3). The person's turns are what
#: the migration mines as material too (`migration.person_turns`); a card's
#: history is one utterance, a long consultation is bounded here so six judge
#: calls do not each re-read it whole (no cache breakpoint sits on a judge
#: call). Policy, not config.
JUDGE_CONTEXT_CHARS = 4_000


def judge_context(person_texts: Sequence[str], budget: int = JUDGE_CONTEXT_CHARS) -> str:
    """The person's turns as the judge's `<context>`, in order, the NEWEST
    kept whole within `budget` and older ones dropped first — a tetrad drawn
    now answers what was said last. Empty when nothing was said."""
    kept: list[str] = []
    used = 0
    for text in reversed([t.strip() for t in person_texts if t and t.strip()]):
        if kept and used + len(text) > budget:
            break
        kept.append(text)
        used += len(text)
    return "\n\n".join(reversed(kept))


def view_sketch_prompt(
    focus: Optional[str], max_words: int, thesis: Optional[str] = None
) -> str:
    """The structured turn's request, over the consultant's own conversation.

    Two instructions in one, because the ask is one or the other and the model
    knows which: render what is ESTABLISHED (a tension already named and taken
    up), and BUILD what the ask needs that is not yet worked out (a perspective
    for a thesis so far only stated). The build follows the same procedure the
    graph path gives `AspectGeneration` — one fixed parent per aspect, axis
    named second, both re-read — so a drawn tetrad is built to the graph's
    rules even though nothing checks it here. The antithesis is asked for as a
    POSITION (`_OPPOSING_POSITION_ASK`, the same words the ladder and the
    one-shot build carry): on the pipeline's auditor the view turn's
    antitheses were a position for 30/40 and plain mirrors for 6 before the
    ask was here, against the one-shot build's 36–38/40 with it
    (docs/dev-notes/antithesis-selection.md, 2026-10-02). The thesis is asked
    for as a STANCE (`THESIS_IS_A_STANCE`): on 20 questions the turn echoed the
    question as T in 6 before the ask was here (the alsotrue app repo, docs/lab-notes-entry.md).

    With `thesis` the host has the position already and wants it kept verbatim
    (`THESIS_IS_FIXED`): the stance ask comes OFF — there is nothing to find —
    and the view is asked for the ONE tension that position stands in, because
    a pinned T says nothing about any other tension and a card shows one.

    ONE request for every draw of a best-of-N, by measurement (2026-10-13,
    `tests/e2e/probe_view_turn_ask.py`, pinned, 40 utterances, two arms the
    same day): asking draw 2..N for a different opposition made every card's
    spares a different position (75/80 positions) and cost the WINNER —
    coherence 19/40 against 27/40 with identical draws, positions 34 against
    37, 1.26x the seconds — so the draws stay a re-roll of one request and
    the spares stay the same tension reworded. The rejected ask and its
    figures: `docs/dev-notes/antithesis-selection.md`, "Best-of-3 drew the
    same tetrad three times".
    """
    pinned = (thesis or "").strip()
    focus_line = (
        f"What to show: {focus}\n\n"
        if focus and focus.strip()
        else "What to show: the tensions this conversation has worked out so far.\n\n"
    )
    scope_line = (
        "- ONE tension: the one the given position below stands in. How much of "
        "it is drawn is still the ask's to say, by the rule above."
        if pinned
        else f"- At most {VIEW_SKETCH_MAX_PERSPECTIVES} tensions, most central "
        "first. Nothing at all rather than a tension the conversation does not "
        "support — a turn that carries no stance (a request for information) "
        "supports none."
    )
    thesis_section = (
        f'{THESIS_IS_FIXED}\n\nThe position: "{pinned}"'
        if pinned
        else THESIS_IS_A_STANCE
    )
    # The exception rides on the line that states the limit, not as a
    # cross-reference from the section above it: a rule and its exception in
    # two places is the competing-signal shape, and the limit is the last line
    # the model reads.
    length_exception = (
        " The given position is the one exception: it stays exactly as it is, "
        "whatever its length."
        if pinned
        else ""
    )
    return f"""Draw the structure of this conversation as dialectical tetrads. Answer with ONE JSON object in the requested schema and nothing else — no prose. Earlier drawings in this conversation are recorded in prose; that is their record, not the format of this answer.

{focus_line}{ASPECT_DEFINITIONS}

Rules for what goes in the view:
- Show what this conversation has ESTABLISHED: a tension you named and the person took up is drawn as you both have it, in their terms. Do not re-derive what is already on the table.
- Where the ask needs structure not yet worked out — a perspective for a thesis so far only stated, the antithesis of a position, the corners of a tension you only named — build it now, by the method below, and then draw it.
- Where the ask stops short of a full tetrad (only the two poles, only the antitheses), leave the positions not asked for EMPTY. An empty corner is honest; an invented one is not.
{scope_line}

{thesis_section}

{_OPPOSING_POSITION_ASK}

{TETRAD_BUILD_PROCEDURE}

Write every position in the person's own terms, {max_words} words or fewer each.{length_exception}"""


# --- The view shaping (pure) ----------------------------------------------


def _pole(text: Optional[str]) -> Optional[PoleView]:
    """A pole from a text, or None for an empty one — the view's own rule: an
    absent position is `None`, not an empty box, and `complete` says so."""
    text = (text or "").strip()
    return PoleView(text=text) if text else None


def perspective_from_sketch(tension: ViewSketchPerspectiveDto) -> PerspectiveView:
    """One drawn tension as a `PerspectiveView`.

    Its `intent` is the reading a generated tetrad would carry, composed the
    way `ExpandPolarity` composes it (`Perspective.compose_reading`) from the
    axes the model named, after the same disclaimer filter (`is_axis_name`) —
    so a drawn tension is labelled exactly as a generated one.
    """
    axes = {
        key: axis.strip()
        for key, axis in (
            ("t_plus_vs_a_minus", tension.t_plus_vs_a_minus_axis),
            ("a_plus_vs_t_minus", tension.a_plus_vs_t_minus_axis),
        )
        if is_axis_name(axis)
    }
    poles = {
        "t": _pole(tension.thesis),
        "a": _pole(tension.antithesis),
        "t_plus": _pole(tension.t_plus),
        "t_minus": _pole(tension.t_minus),
        "a_plus": _pole(tension.a_plus),
        "a_minus": _pole(tension.a_minus),
    }
    return PerspectiveView(
        **poles,
        intent=Perspective.compose_reading(axes),
        complete=all(pole is not None for pole in poles.values()),
    )


def exploration_view_from_sketch(sketch: ViewSketchDto) -> ExplorationView:
    """The whole view as an `ExplorationView` — no nexus, so no `nexus_hash`.

    A tension with no thesis is dropped: there is nothing to draw. One with a
    thesis and no antithesis is KEPT — "the position, opposition not yet
    found" is a real state of a conversation and a real thing to show.
    """
    perspectives = [
        perspective_from_sketch(t) for t in sketch.tensions[:VIEW_SKETCH_MAX_PERSPECTIVES]
    ]
    return ExplorationView(
        perspectives=[p for p in perspectives if p.t is not None]
    )


# --- What the turn leaves in the conversation --------------------------------


def history_ask(focus: Optional[str]) -> str:
    """The user line the view turn leaves in the history in place of the
    request. The request itself is long (definitions, procedure) and, kept
    with a prose record after it, became a Q→A exemplar: the SECOND view turn
    of a real run answered the JSON request in the record's prose and failed
    to parse ten times (`tests/test_view_sketch_real_llm.py`, 2026-09-29). So
    the history keeps what the person effectively asked, and the record."""
    focus = (focus or "").strip()
    return f"Show me: {focus}" if focus else "Show me the structure of what we've worked out so far."


def history_text(view: ExplorationView) -> str:
    """The view as the consultant's own words in its history.

    The structured result would otherwise enter the history as a Pydantic repr
    (`_assistant_history_text` falls back to `str()`), which the facilitator's
    own note warns invites imitation.

    NO position labels here, deliberately. The first version wrote
    "T+: …; T-: …" and the very next reply told the person "the one I'd flag is
    T-" (`tests/test_view_sketch_real_llm.py`, 2026-09-29) — the bare-label
    leak CLAUDE.md documents, produced by feeding the model the labels in its
    own memory. So each corner is described in the person's terms: the pole it
    develops and whether it develops it well or overdoes it. The model can
    still refer to any corner by content on the next turn, which is what
    "remembering what it drew" is for.
    """
    if not view.perspectives:
        return "I drew nothing: the conversation has not established a tension yet."
    lines = ["I drew the structure we have so far:"]
    for n, p in enumerate(view.perspectives, 1):
        t = p.t.text if p.t else None
        a = p.a.text if p.a else None
        if t and not a:
            lines.append(f'{n}. Position: "{t}" — its opposition not yet found.')
            continue
        head = f'{n}. Tension: "{t}" against "{a}"'
        if p.intent:
            head += f" ({p.intent})"
        corners = [
            (p.t_plus, f'"{t}" developed well'),
            (p.t_minus, f'"{t}" overdone'),
            (p.a_plus, f'"{a}" developed well'),
            (p.a_minus, f'"{a}" overdone'),
        ]
        drawn = [f"{how}: {pole.text}" for pole, how in corners if pole is not None]
        if drawn:
            lines.append(head + ".")
            lines.append("   " + " ".join(f"{d}." for d in drawn))
        else:
            lines.append(head + " — the two sides only, not yet developed.")
    return "\n".join(lines)
