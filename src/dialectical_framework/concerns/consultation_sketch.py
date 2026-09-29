"""
ConsultationSketch: the tensions a person is holding, drawn from their own
words alone — the graphless filler for the `ExplorationView`.

WHY THIS EXISTS
===============
The `Consultant` (`agents/consultant/consultant.py`) has no graph: nothing is
written, so `graph/views.py` has nothing to read for it, and a host that wants
to show the person a picture of their situation had no way to get one. This
concern is that way. One structured call over the PERSON's turns emits the
tensions as tetrads — thesis, antithesis, the four aspects, the axis each
diagonal opposes along — and `sketch_view` shapes them into the very same
`ExplorationView` the graph reader produces, so one visualiser serves both
heads. The picture is terminology-free BY CONSTRUCTION rather than by
projection: there is no hash to carry, no alias, no score, and none is asked
for. `without_terminology()` on the result is a no-op.

WHAT THE GRAPH PATH HAS THAT THIS DOES NOT
==========================================
Everything that makes a tetrad a checked one. No HS gate (`_rank_polarities`),
no complementarity, no SP/DV, no `PerspectiveValidation`, no dedup against what
was said before, no persistence — a sketch is drawn from the conversation as it
stands and forgotten with it, like every other output of the head it serves. A
host that wants the checked version has the upgrade (`migrate_consultation`,
then `exploration_view()` inside the Case's scope); this is the picture BEFORE
that decision, and it should not be dressed as more.

SPEAKER-AWARE, BY THE SAME RULE AS THE MIGRATION
================================================
Only the person's turns are material (`migration.person_turns`). The replies
are counsel about the situation, not statements of it, and a sketch drawn
speaker-blind would put the counselor's framings on the person's map — the
same reason the transcript-ingesting design was rejected in review
(`rounds.md`, 2026-09-24). `Consultant.exploration_view()` applies that rule before
calling here; a caller passing `turns` directly is trusted to have done the
same, and the parameter is named for it.
"""

from __future__ import annotations

import logging
from typing import Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.aspect_generation import (
    PLUS_RESTATEMENT_CHECK, is_axis_name)
from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS
from dialectical_framework.graph.nodes.perspective import Perspective
from dialectical_framework.graph.views import (PoleView, ExplorationView,
                                               PerspectiveView)
from dialectical_framework.protocols.has_config import SettingsAware

logger = logging.getLogger(__name__)

#: The most tensions one sketch names. Policy, not config: a tension map is a
#: picture, and one with more than a handful of tetrads on it stops being
#: readable; four is also the default `max_wheel_layer`, the most tensions the
#: graph path arranges together. Nobody deploys a different number.
SKETCH_MAX_TENSIONS = 4


# --- System prompt --------------------------------------------------------

SYSTEM_PROMPT = f"""You read what a person said about their situation and draw out the tensions they are actually holding — as dialectical tetrads.

{ASPECT_DEFINITIONS}

A tension is a thesis (T) and its antithesis (A): two positions the person is caught between, or one position they hold and the opposition it generates. Each tension resolves into two diagonal contradiction pairs, each along one **axis** — a single dimension on which the two aspects sit at opposite ends, so they cannot both hold at once. Derive each aspect from its own parent first, then name the axis; a minus is never obtained by negating the plus it faces.

Stay in the person's terms. The thesis and antithesis are things THEY said or are plainly caught between — not a counselor's reframing, not a generic pair the material happens to allow. If they hold one tension, return one. Return nothing rather than a tension the words do not support."""


# --- DTOs ---------------------------------------------------------------


class SketchedTensionDto(BaseModel):
    """One tension as a flat tetrad: texts only, no scores.

    Flat on purpose. `TetradDto` nests an `AspectDto` under each position
    because it carries scores; here there are none to carry, and the flatter
    the schema the less often the model drops a branch (the note on
    `TetradDto` itself). No score fields: a number here would be an unchecked
    guess dressed as a measurement, and the picture drops numbers anyway.
    """

    thesis: str = Field(description="T — the position, in the person's own terms.")
    antithesis: str = Field(
        description="A — what T is in tension with, in the person's own terms."
    )
    t_plus_vs_a_minus_axis: str = Field(
        description=(
            "The single dimension on which T+ and A- are opposite ends "
            "(e.g. 'closeness')."
        )
    )
    t_plus: str = Field(
        description=(
            "T+ — the THESIS developed constructively, so that it also strengthens "
            "what A offers. Derived from T; the positive end of the axis above."
        )
    )
    a_minus: str = Field(
        description=(
            "A- — the ANTITHESIS overdeveloped one-sidedly, with T underdeveloped. "
            "Derived from A, never by negating T+; the negative end of the axis above."
        )
    )
    a_plus_vs_t_minus_axis: str = Field(
        description="The single dimension on which A+ and T- are opposite ends."
    )
    a_plus: str = Field(
        description=(
            "A+ — the ANTITHESIS developed constructively, so that it also strengthens "
            "what T offers. Derived from A; the positive end of the axis above."
        )
    )
    t_minus: str = Field(
        description=(
            "T- — the THESIS overdeveloped one-sidedly, with A underdeveloped. "
            "Derived from T, never by negating A+; the negative end of the axis above."
        )
    )


class ConsultationSketchDto(BaseModel):
    """The tensions found, most central to the person's situation first."""

    tensions: list[SketchedTensionDto] = Field(
        description=(
            "The tensions the person is holding, most central first. Empty when "
            "their words support none."
        )
    )


# --- The view shaping (pure) ----------------------------------------------


def _pole(text: Optional[str]) -> Optional[PoleView]:
    """A pole from a text, or None for an empty one.

    The model may leave a position blank; the view's own rule applies — an
    absent pole is `None`, not an empty box — and `complete` says so.
    """
    text = (text or "").strip()
    return PoleView(text=text) if text else None


def perspective_from_sketch(tension: SketchedTensionDto) -> PerspectiveView:
    """One sketched tension as a `PerspectiveView`.

    Its `intent` is the reading a generated tetrad would carry, composed the
    way `ExpandPolarity` composes it (`Perspective.compose_reading`) from the
    two axes the model named, after the same disclaimer filter
    (`is_axis_name`) — so the graphless picture labels a tension exactly as
    the graph does.
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


def sketch_view(sketch: ConsultationSketchDto) -> ExplorationView:
    """The whole sketch as a `ExplorationView` — no nexus, so no `nexus_hash`.

    A tension with no thesis or no antithesis is dropped: it is not a tension,
    and a tetrad with no poles at either end would draw as an empty frame.
    """
    tetrads = [perspective_from_sketch(t) for t in sketch.tensions[:SKETCH_MAX_TENSIONS]]
    return ExplorationView(
        perspectives=[t for t in tetrads if t.t is not None and t.a is not None]
    )


# --- The concern ----------------------------------------------------------


class ConsultationSketch(ReasonableConcern[ExplorationView], SettingsAware):
    """One structured call over the person's turns → a `ExplorationView`.

    Usage (what `Consultant.exploration_view()` does):
        view = await ConsultationSketch().resolve(turns=person_turns(messages))
        widget.draw(view.to_dict())

    No scope is needed and none is read: nothing here touches a Case or the
    graph. No material means an empty map and no provider call. A provider
    failure RAISES rather than returning an empty map — this is a
    person-triggered read, and "nothing to draw" and "the drawing failed" must
    stay distinguishable to the host that pressed the button.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(self, turns: list[str]) -> ExplorationView:
        """
        Args:
            turns: What the PERSON said, in order — `migration.person_turns`.
                The replies are not material; see the module docstring.
        """
        material = [t.strip() for t in turns if t and t.strip()]
        if not material:
            self._report.ok = True
            self._report.summary = "Nothing said yet; nothing to sketch"
            return ExplorationView()

        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        sketch = await self._ask(self._prompt(material))
        view = sketch_view(sketch)
        self._report.ok = True
        self._report.summary = f"Sketched {len(view.perspectives)} tension(s)"
        return view

    async def _ask(self, prompt: str) -> ConsultationSketchDto:
        """The one provider call, on its own so a test can stand in for it."""
        return await self._conversation.submit(
            response_model=ConsultationSketchDto, user_content=prompt
        )

    def _prompt(self, turns: list[str]) -> str:
        max_words = self.settings.component_length
        account = "\n\n".join(f"<turn>\n{t}\n</turn>" for t in turns)
        return f"""<what_the_person_said>
{account}
</what_the_person_said>

Name the tensions this person is holding — at most {SKETCH_MAX_TENSIONS}, most central first, and none the words do not support.

For each tension, build the tetrad as its two diagonal contradiction pairs (T+ vs A-, A+ vs T-).
Each aspect has one fixed parent: T+ and T- develop T; A+ and A- develop A.
For each pair:
1. Derive each aspect from ITS OWN parent — a plus develops that parent so it also takes up what the other pole offers; a minus overdevelops that parent one-sidedly, with the other pole absent.
2. Then name the **axis** — the single dimension on which the two aspects are opposite ends, so they cannot both hold at once.
3. Re-read both aspects against step 1 for two distinct failures. (a) Wrong parent: if one is really the OTHER parent developed, rewrite it from its own parent. (b) {PLUS_RESTATEMENT_CHECK}

Write every position in the person's own terms, {max_words} words or fewer each."""
