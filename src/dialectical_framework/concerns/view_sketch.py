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

    thesis: str = Field(description="T — the position, in its holder's own terms.")
    thesis_held_by: str = Field(
        description=(
            "Who holds T, named from the words, ONLY when it is not the person's own "
            "position — the quoted party, the speaker, 'critics', 'the Minister' — "
            "and only a party whose own words take it. "
            "Empty when the person speaks for themselves."
        )
    )
    antithesis: str = Field(
        description=(
            "A — what T is in tension with, in its holder's own terms. Empty if "
            "the ask stops at the thesis."
        )
    )
    antithesis_held_by: str = Field(
        description=(
            "Who holds A, named from the words, ONLY when a party's own words state "
            "or plainly take it — in a debate, the other speaker. Empty when the "
            "person speaks for themselves, and Empty when you BUILT the opposition "
            "because no one in the words holds it: never a name on words they did "
            "not say."
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
#: first app's second handoff (2026-10-20, `docs/dev-notes/antithesis-selection.md`, "The hedge wins on coherence"):
#: a six-sentence polemic holding four claims and a concession came back as a
#: tetrad about its mildest sub-claim ("society has the right to ask"), while
#: the demand the person would sign ("stop mass migration") sat in no corner.
#: Every figure above was taken on one-sentence, one-claim inputs, where the
#: question never arose. UNMEASURED: to be run on a set of long multi-claim
#: inputs (`tests/e2e/probe_view_turn_ask.py` once there is a case set), with
#: the question-echo figure above re-checked, since it is the same constant.
#: A host's intake gate reads this text too (`systemic-map.md` 0d), so its
#: cut moves with it — by design: the gate's cut is what the writer reads as T.
#:
#: WHOSE stance (2026-10-26, `tests/e2e/probe_pasted_material.py`): the text
#: used to presume authorship — "something the person holds, written as a claim
#: they could say in the first person" — and on pasted MATERIAL (20 third-party
#: articles, 17 Hansard dialogue windows, none carrying the reader's position)
#: the writer took one of the OTHER parties' positions as T in 28 of 28 draws
#: with nothing saying whose, so a card would show it as the person's. The
#: first-person device was never reaching the wording anyway: both the old and
#: this text produce bare claims ("Drop the family farm tax"), and the device's
#: real job — stopping the writer echoing a question as T (6/20 → 0/20) — is
#: done by the sentences kept here. Measured as an arm before it shipped: on
#: material it stops the writer DECLINING articles (11/20 → 20/20 drawn) and
#: draws the tension in them (a held position 16/20); on the 20-question echo
#: probe it is neutral within one case (own stance 15/15, echo 1/15, requests
#: for information declined 4/4). The holder is carried by `held_by` on the DTO
#: and the view, because no wording of this rule can carry it: 0 of 37 draws
#: named one in either arm. Story: `docs/dev-notes/views.md`, "Pasted material".
THESIS_IS_A_STANCE = """The thesis (T) is a STANCE: a claim that someone in these words HOLDS, wants or is about to act on — never a question restated, never a description of what happens. WHOSE stance depends on the words. When the person speaks for themselves, T is their own position, worded as they could say it. When the words report, quote or transcribe OTHER people's positions and carry none of the person's own — an article, a debate, a conversation they are relaying — T is one of THOSE positions, worded as its holder would state it and never as the person's own, and the holder is NAMED (in the `held_by` field) so that nobody is told it is theirs; the person is reading, not asserting. When they asked a question, T is the answer their wording leans to: "Why should I keep paying for his phone when he never calls?" carries "I should stop paying for his phone"; "Isn't it time we stopped standups?" carries "We should stop standups". A behaviour described is not yet a stance; the stance is what its holder holds about it. When the question is genuinely open between options ("Zurich or Vilnius?"), T is one of those options held as a stance. A request for information ("what is the best way to learn Spanish?") carries no stance at all. When the words hold SEVERAL claims, T is the one their holder would sign — the conclusion or demand the rest leads to — not a premise or a hedge on the way to it ("we have the right to ask" is the run-up to the demand that follows), and not a claim conceded in passing ("not only X but also Y" concedes X; the stance is Y)."""

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

#: WHO HOLDS A POLE is read off the words (2026-10-27, `tests/e2e/probe_pasted_material.py`,
#: "a name on words never said"). The field descriptions alone said "the other
#: speaker" and nothing about an opposition the writer BUILT, and on the
#: shipped text's dialogue run the writer put a speaker's name on its own
#: construction: the Exchequer Secretary given "Fund public services through
#: taxing business" over a window in which he defended a rates support package,
#: Anna Turley given the opposition to a position she had just agreed with. A
#: screen then shows "the Minister's position" over words the Minister never
#: said — a misquotation, worse than "your position" was. The same run drew the
#: opposition itself in 2 of 17 dialogues where the other speaker's stood in the
#: text (an honest construction, left unnamed), and took the other speaker's in
#: the rest once a text-grounded judge read them (the position-list judge had
#: called 8 of 17 "none", most of them paraphrases). This text is read by the
#: view turn ONLY: the one-shot build drops the holder before the graph (a
#: Statement stores none), so its half of the rule is unmeasured there.
#: Measured before it shipped, WITH against WITHOUT, two draws per case over the
#: 37 pasted-material cases (74 draws an arm), text-grounded reads: A a position
#: the text attributes to someone 58 against 46 (paired 16/4, p = 0.012, the one
#: resolved effect); A named for words the text does not bear 16 against 23
#: (dialogues 4 against 8) — the pre-registered absolute bar of 2 MISSED, on a
#: same-party read that counts compound names as mismatches in both arms, about
#: 4 against 10 by one hand read; coherence 41 against 46, at its bar and inside
#: the judge's variance. Shipped with the miss stated: the rule halves the
#: misquotation and does not end it; the lever left is a code-side attribution
#: check after the draw (unbuilt). Story and table: `docs/dev-notes/views.md`,
#: "A name on words never said".
HOLDER_FROM_THE_WORDS = """Who HOLDS a pole is read off the words, never supplied. Name a party as holding a position only when their own words state it or plainly take it; a party who agrees with T does not hold A. When another party in the words holds the position T stands against, A IS that party's position, in their terms, and they are named — a transcript's tension is between its speakers. When no one in the words holds the opposition, build it by the method below and leave its holder EMPTY: an opposition you built is nobody's, and a name on words never said is a misquotation."""



#: THE ONE RE-ASK (2026-10-28, the first app's third handoff,
#: `docs/dev-notes/antithesis-selection.md`, "A is the view the author
#: granted"). On the petition sets the writer drew A as the view the author
#: had set down to argue past ("X is true, however Y" → A = X) on about half
#: the conceding texts, in every draw of the card and under both prompt arms:
#: the mirror sentence in `_OPPOSING_POSITION_ASK` is inert at the pole, and
#: selection cannot choose what no draw offers. So when the fit judge reads
#: every draw's A as granted (`tetrad_candidates.every_opposition_granted`),
#: `Consultant.exploration_view` CAN send the SAME request once more with this
#: section added, naming the granted view, the re-draw joining the field
#: under the ordinary ranking — a second request after the card, not a draw
#: of the first (the different-opposition ask for draws 2..N was measured and
#: rejected, `view_sketch_prompt`'s docstring). MEASURED AND OFF the same day
#: (`Consultant.REDRAW_ON_GRANTED_OPPOSITION`, `probe_granted_opposition_redraw.py`):
#: on the 22 conceding petitions it fired on 5 cards, moved the granted A
#: 5 → 4 against a bar of −4 and cost coherence 21 → 18. The re-draw WAS a
#: different opposition in 4 of 5 — and in 2 of those it lost the ranking to
#: the granted original, the 2026-10-13 finding again (a different opposition
#: is a weaker tetrad on the pass rule). The text stays as the measured arm;
#: the model is not the lever either: the writer on Opus 5.5 drew the granted
#: view on 4 of 22 against Sonnet 5.5's 5, the same four petitions, and the
#: re-ask fired on 4 and moved nothing (4 → 4).
GRANTED_OPPOSITION_REASK = """The opposition drawn for this position so far — "{antithesis}" — is a view the person's OWN words already grant: they set it down as true or legitimate in order to argue past it, so a tetrad on it shows them their own sentence as the other side. Do not draw it again — not reworded, not folded into the corners. Find the position that genuinely opposes the claim they actually make: one someone holds for its own value, that their words do not concede — and build the tetrad on that."""


def granted_opposition_section(antithesis: str) -> str:
    return GRANTED_OPPOSITION_REASK.format(antithesis=(antithesis or "").strip())


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
    focus: Optional[str],
    max_words: int,
    thesis: Optional[str] = None,
    granted_opposition: Optional[str] = None,
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
    Who HOLDS each pole is read off the words (`HOLDER_FROM_THE_WORDS`, on both
    branches — a pinned T is the person's own, but the words it came with may
    still carry someone else's opposition): a name goes on a position only
    when that party's own words take it, and a built opposition has none.

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

    `granted_opposition` is NOT a per-draw argument: it is the one re-ask the
    view turn can send AFTER the card's draws, when every draw's A was read
    as a view the person's words grant (`GRANTED_OPPOSITION_REASK`, above;
    off by measurement). The request is otherwise the same, so the re-draw
    is the same ask with the granted view excluded by name.
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
    reask = (
        f"\n\n{granted_opposition_section(granted_opposition)}"
        if granted_opposition and granted_opposition.strip()
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

{_OPPOSING_POSITION_ASK}{reask}

{HOLDER_FROM_THE_WORDS}

{TETRAD_BUILD_PROCEDURE}

Write every position in the person's own terms, {max_words} words or fewer each.{length_exception}"""


# --- The view shaping (pure) ----------------------------------------------


def _pole(text: Optional[str], held_by: Optional[str] = None) -> Optional[PoleView]:
    """A pole from a text, or None for an empty one — the view's own rule: an
    absent position is `None`, not an empty box, and `complete` says so.
    `held_by` empty means the person's own, and is `None` on the pole: absence
    is None, never a sentinel."""
    text = (text or "").strip()
    held_by = (held_by or "").strip() or None
    return PoleView(text=text, held_by=held_by) if text else None


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
        "t": _pole(tension.thesis, tension.thesis_held_by),
        "a": _pole(tension.antithesis, tension.antithesis_held_by),
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
        # Whose, when it is not the person's own — so the next reply says "the
        # Minister's position", not "your position" (the pasted-material run).
        t_whose = f" ({p.t.held_by}'s position)" if p.t and p.t.held_by else ""
        a_whose = f" ({p.a.held_by}'s)" if p.a and p.a.held_by else ""
        if t and not a:
            lines.append(f'{n}. Position: "{t}"{t_whose} — its opposition not yet found.')
            continue
        head = f'{n}. Tension: "{t}"{t_whose} against "{a}"{a_whose}'
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
