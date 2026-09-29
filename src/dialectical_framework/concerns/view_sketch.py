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

from typing import Optional

from pydantic import BaseModel, Field

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
            "T+ — the THESIS developed constructively, so that it also strengthens "
            "what A offers. Derived from T; the positive end of the axis above. "
            "Empty when not drawn."
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
            "A+ — the ANTITHESIS developed constructively, so that it also strengthens "
            "what T offers. Derived from A; the positive end of the axis above. "
            "Empty when not drawn."
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


def view_sketch_prompt(focus: Optional[str], max_words: int) -> str:
    """The structured turn's request, over the consultant's own conversation.

    Two instructions in one, because the ask is one or the other and the model
    knows which: render what is ESTABLISHED (a tension already named and taken
    up), and BUILD what the ask needs that is not yet worked out (a perspective
    for a thesis so far only stated). The build follows the same procedure the
    graph path gives `AspectGeneration` — one fixed parent per aspect, axis
    named second, both re-read — so a drawn tetrad is built to the graph's
    rules even though nothing checks it here.
    """
    focus_line = (
        f"What to show: {focus}\n\n"
        if focus and focus.strip()
        else "What to show: the tensions this conversation has worked out so far.\n\n"
    )
    return f"""Draw the structure of this conversation as dialectical tetrads.

{focus_line}{ASPECT_DEFINITIONS}

Rules for what goes in the view:
- Show what this conversation has ESTABLISHED: a tension you named and the person took up is drawn as you both have it, in their terms. Do not re-derive what is already on the table.
- Where the ask needs structure not yet worked out — a perspective for a thesis so far only stated, the antithesis of a position, the corners of a tension you only named — build it now, by the method below, and then draw it.
- Where the ask stops short of a full tetrad (only the two poles, only the antitheses), leave the positions not asked for EMPTY. An empty corner is honest; an invented one is not.
- At most {VIEW_SKETCH_MAX_PERSPECTIVES} tensions, most central first. Nothing at all rather than a tension the conversation does not support.

Building a tetrad, when you build one — as its two diagonal contradiction pairs (T+ vs A-, A+ vs T-).
Each aspect has one fixed parent: T+ and T- develop T; A+ and A- develop A.
For each pair:
1. Derive each aspect from ITS OWN parent — a plus develops that parent so it also takes up what the other pole offers; a minus overdevelops that parent one-sidedly, with the other pole absent.
2. Then name the **axis** — the single dimension on which the two aspects are opposite ends, so they cannot both hold at once.
3. Re-read both aspects against step 1 for two distinct failures. (a) Wrong parent: if one is really the OTHER parent developed, rewrite it from its own parent. (b) {PLUS_RESTATEMENT_CHECK}

Write every position in the person's own terms, {max_words} words or fewer each."""


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

_HISTORY_POSITIONS = (
    ("t", "T"), ("a", "A"), ("t_plus", "T+"), ("t_minus", "T-"),
    ("a_plus", "A+"), ("a_minus", "A-"),
)


def history_text(view: ExplorationView) -> str:
    """The view as the consultant's own words in its history.

    The structured result would otherwise enter the history as a Pydantic repr
    (`_assistant_history_text` falls back to `str()`), which the facilitator's
    own note warns invites imitation. This is replayed to the provider only,
    never shown to the person, so the position labels are fine here — they are
    how the model refers to the corners it drew when the next turn asks about
    one.
    """
    if not view.perspectives:
        return "I drew nothing: the conversation has not established a tension yet."
    lines = ["I drew the structure we have so far:"]
    for n, p in enumerate(view.perspectives, 1):
        parts = [
            f"{label}: {pole.text}"
            for name, label in _HISTORY_POSITIONS
            if (pole := getattr(p, name)) is not None
        ]
        head = f"{n}. " + "; ".join(parts)
        if p.intent:
            head += f" ({p.intent})"
        lines.append(head)
    return "\n".join(lines)
