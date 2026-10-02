"""
TetradSketch: ONE reasoning call writes a whole tetrad from the person's words.

Why this exists. The staged build — headline the thesis, pick an antithesis off
the ladder, generate four aspects for a pair the generator never saw whole —
passed the coherence check on 14/40 first tetrads from free utterances, in
~55 s; the Consultant's view turn, which reasons the whole tetrad in one
thinking call over the utterance itself, passed 24/40 in ~7 s on the same
utterances and the same judge (docs/dev-notes/antithesis-selection.md). Every
fix to the stages moved a piece and not the end-to-end figure, because the
loss is in the chopping. So the Advisor's build gets the same reasoning shape:
this concern writes T, A and the four aspects in one json-mode call with
thinking, and `agents/analyst/skills/sketch_tetrad.py` then does what a prompt
alone cannot — classifies, scores, dedups, grounds, validates and persists it
as a normal tetrad in the graph.

The system prompt is `method_prompt()` READ from the Consultant, never a copy:
the method stated once, so the bench's A1 baseline and this builder cannot
drift apart (`TestTetradSketch.test_the_system_prompt_is_the_method`). The
building procedure is `view_sketch.TETRAD_BUILD_PROCEDURE`, shared with the
view turn for the same reason. Texts only — a score here would be an unchecked
guess (`AspectGeneration.score_given` scores afterwards).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.antithesis_extraction import \
    _OPPOSING_POSITION_ASK
from dialectical_framework.concerns.scoring_scales import ASPECT_DEFINITIONS
from dialectical_framework.concerns.view_sketch import (
    TETRAD_BUILD_PROCEDURE, ViewSketchPerspectiveDto)
from dialectical_framework.protocols.has_config import SettingsAware


class TetradSketchDto(BaseModel):
    """Exactly one tension, whole. The view turn's flat per-tension DTO, reused:
    texts for T, A, two axes and four aspects, no numbers."""

    tension: ViewSketchPerspectiveDto = Field(
        description="The ONE tension at the heart of what the person said, as a full tetrad."
    )


def tetrad_sketch_prompt(
    material: str, context: str, max_words: int, thesis: Optional[str] = None
) -> str:
    """The request: the material, then the ask. One tension, all six positions,
    by the shared procedure, with the antithesis asked for as a POSITION (the
    Optimum-A ask the ladder path carries), and every position in the person's
    own terms.

    `material` is whatever the person said or pasted, as the Input renders it
    (`input_context`: the digest of a long paste, the words of a short one) —
    never the thesis. `thesis` pins T: on the Advisor's `anchor` the model has
    already named the position to plant, and the tool's contract is to plant
    THAT one — the call may word it in the person's terms, not replace it.
    Without it (a host's one paste, the probe's free form) the call finds the
    position IN the material. One of the two must be present.

    There is deliberately NO way to pin the antithesis as well. It was tried
    (2026-10-02, `tests/e2e/probe_aspect_variants.py` arm `oneshot_pinned`):
    with both poles given and "keep BOTH poles" in the request, this writer
    still built its aspects on a shifted tension in 17/40 and 22/40 of the
    pairs (coherence 20/40 and 23/40, non-inferior). Where the poles already
    exist as nodes that is disqualifying, so the staged four-aspect call
    (`AspectGeneration._generate_tetrad`) stays THE writer for a given pair and
    this one writes only where it also chooses the opposition. Two writers,
    measured — not an accident to tidy away (docs/dev-notes/antithesis-selection.md).
    """
    context_section = f"<context>\n{context}\n</context>\n\n" if context.strip() else ""
    material_section = f"<material>\n{material}\n</material>\n\n" if material.strip() else ""
    thesis_line = (
        f'The thesis (T) is GIVEN: "{thesis.strip()}". Keep its meaning as the position; '
        f"word it in the person's own terms, {max_words} words or fewer."
        if thesis and thesis.strip()
        else "The thesis (T) is the position the person holds or is weighing in this material, in their own terms — not a restatement of the whole, not a generalisation they did not make."
    )
    return f"""{context_section}{material_section}Work out the ONE tension at the heart of this material — what the person said or pasted — as a complete dialectical tetrad. Answer with ONE JSON object in the requested schema and nothing else — no prose.

{ASPECT_DEFINITIONS}

{thesis_line}

{_OPPOSING_POSITION_ASK}

{TETRAD_BUILD_PROCEDURE}

Fill every position — this is a complete tetrad, no corner left empty. Write every position in the person's own terms, {max_words} words or fewer each."""


class TetradSketch(ReasonableConcern[ViewSketchPerspectiveDto], SettingsAware):
    """One thinking call over the utterance → six texts. Nothing persisted here."""

    def __init__(self, persona: Optional[str] = None) -> None:
        #: An app persona placed ABOVE the method, for measurement only: the
        #: 26/40 harness arm carried `COUNSELOR_PERSONA + method_prompt()`, and
        #: whether the persona did any of that work is unmeasured. Production
        #: passes None — the method alone.
        self._persona = persona

    @staticmethod
    def system_prompt(persona: Optional[str] = None) -> str:
        from dialectical_framework.agents.consultant.consultant import method_prompt

        method = method_prompt(include_decision=False)
        return f"{persona}\n\n{method}" if persona else method

    async def resolve(
        self, material: str, context: str = "", thesis: Optional[str] = None
    ) -> ViewSketchPerspectiveDto:
        material = (material or "").strip()
        if not material and not (thesis or "").strip():
            self._report.ok = False
            self._report.summary = "Nothing to sketch: no material and no thesis"
            raise ValueError("TetradSketch needs material or a thesis")

        # Thinks at the deployment's conversational level: this is the heaviest
        # reasoning a structured call is asked to do, and it is the ONE
        # ingredient the staged generator was measured not to profit from while
        # the whole-tetrad call did (20/40 without, 26/40 with, in the harness).
        level = ConversationFacilitator()._thinking_kwargs().get("thinking")
        conversation = ConversationFacilitator(format_mode="json", thinking=level)
        conversation.set_system_prompt(self.system_prompt(self._persona))
        result = await conversation.submit(
            TetradSketchDto,
            tetrad_sketch_prompt(
                material, context or "", self.settings.component_length, thesis
            ),
        )
        tension = result.tension
        missing = [
            name
            for name in ("thesis", "antithesis", "t_plus", "t_minus", "a_plus", "a_minus")
            if not (getattr(tension, name) or "").strip()
        ]
        if missing:
            self._report.ok = False
            self._report.summary = f"Sketch left positions empty: {', '.join(missing)}"
            raise ValueError(self._report.summary)

        self._report.ok = True
        self._report.summary = f"Sketched: {tension.thesis} vs {tension.antithesis}"
        self._report.artifacts["sketch"] = tension.model_dump()
        return tension
