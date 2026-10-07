"""
TransformationSketch: the way through ONE tension, written in one call, graph-free.

WHY THIS EXISTS
===============
The framework hands a host a one-shot TETRAD without a graph (the Consultant's
view turn, `concerns/view_sketch.py`; `TetradSketch`), but had nothing for the
layer above it — the action and reflection that carry the person through the
tension, their developments, and what those produce together. The first app
needed exactly that for its card and wrote its own prompt, and in copying the
theory it kept half of the definition of the minus transitions (2026-10-06):
"Ac- is the action done without the reflection" without where Ac- GOES, which
is from T's strength into A's trap. The framework's own generator states both.
A host should not have to restate the theory to use it, so the statement of
the Transformation lives here, once, and the synthesis prompt reads the same
text (`synthesis_generation.SYSTEM_PROMPT`, "The shape of the inputs").

WHAT THE THEORY SAYS, AND WHY BOTH HALVES ARE IN THE TEXT
=========================================================
[P0 pp.6,16-17] gives each minus transition twice: by its ENDS (Ac- = T+ → A-,
Re- = A+ → T-, which is how `explore_transformations._create_transformation`
wires them) and by what it is MADE of ("Ac+ without Re+ degenerates into
Ac-"). A prompt that gives only the ends lets the model write the destination
(A- restated); one that gives only the makeup lets it write any bad action.
`TRANSFORMATION_POSITIONS` states both, plus the diagonal contradictions.

WHAT WAS MEASURED, AND WHAT WAS NOT
===================================
The ORDER and the S± rule are the measured part: one call asked for the poles
(Ac, Re) first, then each one's developments, then S± with S- as ONE named
state, scored 11/17 on the third-trap auditor where a call that skipped the
poles and stated the theory loosely scored 0/17 (`one-shot-transformation.md`,
arms 1 and 2; the auditor is saturated by the either/or instruction, so read
that as compliance). The endpoint half of the minus definitions was added
afterwards and, stated in text alone, did NOT land: valid Ac- / Re- in 30% /
26% of drafts by the theory-faithful auditor (`probe_transition_rescore.py`;
the app's stricter auditor read 14-30%). What lands the ends is the DTO, not
the sentence: the writer names where
each minus line starts and lands before writing it (`TransformationSketchDto`
says why and by how much). That probe is the gate for any change to the
definition text or those fields. Arm 1 is not evidence against the endpoints:
it differed from arm 2 in three ways at once, and its Ac- came back as T-,
which violates the endpoint reading too.

SCOPE
=====
One tension only. On a one-tension wheel the reflection side is the same
tetrad read backwards, so six corners are all the input there is. With two or
more tensions the reflection runs on the opposite edge's statements and the
layers refine one another (`docs/dev-notes/refinement-recursion.md`); that is
the graph path, `ExploreTransformations` + `GenerateSynthesis`, and whether a
one-shot can replace it there is a separate, gated measurement
(`one-shot-transformation.md`, "Open"). Texts only, nothing persisted, no
scores — a number here would be an unchecked guess.

Unthinking, like every concern: nothing measured thinking on this call, and
the measured arm ran without it.

SELECTION: AVAILABLE, OFF BY DEFAULT
====================================
The tetrad writers draw three and keep the most coherent
(`concerns/tetrad_candidates.py`). The same judge applies here without a new
prompt, because the paper states the transition tetrad's control statements in
the tetrad's own form [P0 pp.16-17, Rule 5.2]: "Ac+ without Re+ degenerates
into Ac-" and "Re+ without Ac+ degenerates into Re-" are "T+ without A+ yields
T-" with Ac+/Ac-/Re+/Re- in the corners (`as_control_tetrad`). So `attempts=`
draws N in parallel and keeps the best by that judge, exactly as the tetrad
writers do. The default is ONE, and that is deliberate: the tetrad's default
of three was earned by measurement first (52% → 72% → 80% on existing
draws, then pre-registered), and nothing about this call is measured yet —
not how often its control statements fail, not whether they separate draws.
The judge also cannot see the two things this layer has actually been caught
getting wrong: S-'s shape and whether Ac-/Re- end where the theory says. Turn
it on for a host on a measurement, not on analogy.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.graph.views import PerspectiveView
from dialectical_framework.protocols.has_config import SettingsAware

#: The Transformation as a tetrad of its own: the poles, their developments,
#: and the diagonal contradictions. ONE statement, read by this concern, by the
#: synthesis prompt that consumes graph-built Transformations, and by any host
#: that writes the way through a tension in its own voice (the first app's
#: card) — so none of them can restate the theory differently.
TRANSFORMATION_POSITIONS = """1. The action (Ac): the concrete move that carries T toward A. The reflection (Re): the re-reading that carries A back toward T. These are the two poles of the transformation.
2. Each developed well — Ac+ turns T's trap (T-) into A's strength (A+); Re+ turns A's trap (A-) into T's strength (T+).
3. Each overdeveloped one-sidedly — Ac- is the good action without the good reflection (Ac+ without Re+), which carries T's strength (T+) into A's trap (A-); Re- is the good reflection without the good action (Re+ without Ac+), which carries A's strength (A+) into T's trap (T-). They are the ACTION and the REFLECTION gone wrong: they END in the traps but are not the traps restated — a path is not its destination. Ac+ contradicts Re-, and Re+ contradicts Ac-."""

#: What the developments produce together. The S- sentences are the measured
#: fix (`one-shot-transformation.md`: third-trap 4/17 → 12/17 on graph-built
#: wheels once the synthesis prompt carried them) and are kept word for word.
SYNTHESIS_SHAPE = """S+ is what emerges only when Ac+ and Re+ run together — a gain in dimension, not a middle: not "both", not the two strengths listed side by side. S- is the ONE named state Ac- and Re- produce together: a single way of failing that is neither trap on its own and not a choice between them. "Either X or Y", "X versus Y" and "X while Y" with X and Y the two traps are the inputs listed, not the collapse named."""

#: How a one-shot call builds it: the poles FIRST, because a degraded action
#: needs an action to degrade (the measured order), then the developments,
#: then S±. A host embeds this in its own system prompt and its own voice.
TRANSFORMATION_BUILD_PROCEDURE = f"""Derive the way through as a SECOND tetrad, the transformation, in this order and no other:
{TRANSFORMATION_POSITIONS}
4. {SYNTHESIS_SHAPE}"""


#: Draws per transformation. ONE until measured — see "Selection" above for
#: why the tetrad writers' three does not carry over by analogy.
DEFAULT_TRANSFORMATION_ATTEMPTS = 1


def as_control_tetrad(sketch: Any) -> SimpleNamespace:
    """The transition tetrad in the corners the coherence judge reads.

    [P0 pp.16-17, Rule 5.2]: Ac±/Re± form a tetrad obedient to the same rules
    as T±/A±, so its control statements are the tetrad's with Ac+ for T+,
    Ac- for T-, Re+ for A+ and Re- for A-: "Ac+ without Re+ yields Ac-" and
    "Re+ without Ac+ yields Re-". Works on any object with the four fields —
    the framework's DTO or a host's subclass of it.
    """
    return SimpleNamespace(
        t_plus=sketch.ac_plus,
        t_minus=sketch.ac_minus,
        a_plus=sketch.re_plus,
        a_minus=sketch.re_minus,
    )


class TransformationSketchDto(BaseModel):
    """One transformation and its synthesis: eight texts, plus the two ends of
    each minus line written first.

    Flat and text-only for the reasons `ViewSketchPerspectiveDto` gives: the
    flatter the schema the less often a real provider drops a branch, and a
    score here would be a guess dressed as a measurement. The field ORDER is
    the build order (poles, developments, synthesis) because the model writes
    the fields in order.

    `ac_minus_from` / `ac_minus_into` (and the Re- pair) come BEFORE their
    line on purpose, and they are the measured fix, not decoration. Stating the
    ends in the definition does not make the writer use them: with the text
    alone a valid Ac- (lands in A-, is the action degenerated, the action
    causing the landing) came back in 32% of drafts and a valid Re- in 30%, because "the
    action without the reflection" reads like the tetrad's own "T+ without A+
    yields T-" and the line lands on T's OWN trap. Making the writer name the
    start and the landing first moved them to 62% / 64% (paired +30 / +34, both
    clearing noise), S- unchanged (third failure 75% / 75%; crossed pairwise 57-56 over 113 decided pairs) (`tests/e2e/probe_transformation_sketch.py`,
    25 tetrads x 2 reps, 2026-10-06, re-read by `probe_transition_rescore.py`
    with the auditor two blind theory panels agree with on 54/60 clear cases;
    the app's stricter auditor had read 22/18% -> 60/58%). A host may
    ignore the four scaffold fields; their job is done by the time the line is
    written.

    The price, measured: the ends rose and the makeup reads dip a little — a
    line written to land on its trap can stop reading as the operation
    overdone. "Re- is the reflection itself" 94% -> 88% (within noise) in the
    first run, "Ac- is the action itself" 100% -> 93% (-7, clears) in the
    second (2026-10-07, 100 pairs); the first app's pill saw Re- 98% -> 80% in
    its own voice. Against +30 / +34 on validity it is a good trade; if a
    host's makeup read keeps falling, measure it on this probe, do not drop the
    fields by eye.

    Hosts SUBCLASS it to add their own person-facing fields after these, so
    the derivation and the words that rest on it stay one call: the first
    app's card writes its three sentences from this derivation in the same
    response, which is what made them land. Field descriptions carry no word
    limits (they cannot read settings); the prompt body states them.
    """

    action: str = Field(
        description=(
            "Ac — the neutral ACTION that carries T toward A: what would actually be "
            "done. One line, concrete, in the person's own particulars."
        )
    )
    reflection: str = Field(
        description=(
            "Re — the neutral REFLECTION that carries A back toward T: what would be "
            "noticed or re-read. One line."
        )
    )
    ac_plus: str = Field(
        description=(
            "Ac+ — the action developed well: the version that turns T's trap (T-) "
            "into A's strength (A+)."
        )
    )
    ac_minus_from: str = Field(
        description=(
            "Which of T's strengths (T+) the degraded action starts from — a phrase."
        )
    )
    ac_minus_into: str = Field(
        description="Which part of A's trap (A-) it lands in — a phrase."
    )
    ac_minus: str = Field(
        description=(
            "Ac- — the good action without the good reflection (Ac+ without Re+): the "
            "action itself gone wrong, which carries T's strength (T+) into A's trap "
            "(A-). It ends in A- but is not A- restated."
        )
    )
    re_plus: str = Field(
        description=(
            "Re+ — the reflection developed well: the version that turns A's trap "
            "(A-) into T's strength (T+)."
        )
    )
    re_minus_from: str = Field(
        description=(
            "Which of A's strengths (A+) the degraded reflection starts from — a phrase."
        )
    )
    re_minus_into: str = Field(
        description="Which part of T's trap (T-) it lands in — a phrase."
    )
    re_minus: str = Field(
        description=(
            "Re- — the good reflection without the good action (Re+ without Ac+): the "
            "reflection itself gone wrong, which carries A's strength (A+) into T's "
            "trap (T-). It ends in T- but is not T- restated."
        )
    )
    s_plus: str = Field(
        description=(
            "S+ — what emerges only when Ac+ and Re+ run together: a new quality "
            "neither alone has. Not a compromise, not 'both'."
        )
    )
    s_minus: str = Field(
        description=(
            "S- — what Ac- and Re- running together collapse into: ONE named way of "
            "failing that is neither T- nor A- on its own. Never 'either X or Y'."
        )
    )


SYSTEM_PROMPT = f"""You build the way through a dialectical tension. You are handed one tetrad — a position (T), what it stands against (A), each side developed well (T+, A+) and each side's trap (T-, A-) — as given and final; you do not rework it.

{TRANSFORMATION_BUILD_PROCEDURE}

Write every line about the situation itself, in the tetrad's terms and the person's own words."""


def _corner(tetrad: PerspectiveView, name: str) -> str:
    pole = getattr(tetrad, name)
    return pole.text if pole is not None else ""


def transformation_sketch_prompt(
    tetrad: PerspectiveView,
    material: str,
    max_words: int,
    synthesis_max_words: int,
) -> str:
    """The request: the six corners as given, the person's words when there
    are any, and the lengths (which the DTO's descriptions cannot carry)."""
    said = f'They said: "{material.strip()}"\n\n' if material and material.strip() else ""
    return f"""{said}Position (T): {_corner(tetrad, "t")}
Stands against (A): {_corner(tetrad, "a")}
T developed well (T+): {_corner(tetrad, "t_plus")}
T's trap (T-): {_corner(tetrad, "t_minus")}
A developed well (A+): {_corner(tetrad, "a_plus")}
A's trap (A-): {_corner(tetrad, "a_minus")}

Derive the transformation. The six transition lines at most {max_words} words each; S+ and S- at most {synthesis_max_words} words each."""


class TransformationSketch(ReasonableConcern[TransformationSketchDto], SettingsAware):
    """The way through one complete tetrad, in one structured call.

    Usage:
        sketch = await TransformationSketch().resolve(view.perspectives[0], material=utterance)
        sketch.ac_plus, sketch.re_plus, sketch.s_minus, ...

    A host that writes person-facing text in the same call does not use this
    class: it subclasses `TransformationSketchDto` and embeds
    `TRANSFORMATION_BUILD_PROCEDURE` in its own system prompt, so the theory
    is still the framework's and the voice is the host's.

    A host that writes person-facing text from the result in a SECOND call
    must tell that call the lines are meaning only, not wording to reuse:
    otherwise it echoes them, and the lines are written to the theory's
    shape, not to a person. Measured by the first app on its card text
    (19–21 points lost until its writer said so; the record is in that app's
    repo).
    """

    def __init__(self) -> None:
        #: Set by `resolve`, as `TetradSketch` keeps them: the chosen draw's
        #: verdict (None with one draw, or when judging failed) and the
        #: runners-up with theirs.
        self.verdict: Optional[Any] = None
        self.alternatives: list[tuple[TransformationSketchDto, Optional[Any]]] = []

    async def resolve(
        self,
        tetrad: PerspectiveView,
        material: str = "",
        attempts: Optional[int] = None,
    ) -> TransformationSketchDto:
        """Raises on an incomplete tetrad: a transformation is built from all
        six corners, and an empty corner would be invented by the call rather
        than read. `attempts` > 1 draws that many in parallel and keeps the one
        whose transition tetrad is most coherent (see "Selection" above for
        why the default is one)."""
        from dialectical_framework.concerns.tetrad_candidates import (
            clamp_attempts, select_sketch)

        missing = [
            name
            for name in ("t", "a", "t_plus", "t_minus", "a_plus", "a_minus")
            if not _corner(tetrad, name).strip()
        ]
        if missing:
            self._report.ok = False
            self._report.summary = f"Incomplete tetrad: {', '.join(missing)} empty"
            raise ValueError(
                f"TransformationSketch needs a complete tetrad; empty: {', '.join(missing)}"
            )

        request = transformation_sketch_prompt(
            tetrad,
            material,
            self.settings.transition_length,
            self.settings.component_length,
        )

        async def draw() -> TransformationSketchDto:
            conversation = ConversationFacilitator()
            conversation.set_system_prompt(SYSTEM_PROMPT)
            return await conversation.submit(
                response_model=TransformationSketchDto, user_content=request
            )

        n = clamp_attempts(attempts, DEFAULT_TRANSFORMATION_ATTEMPTS)
        drawn = await asyncio.gather(*(draw() for _ in range(n)), return_exceptions=True)
        candidates = [d for d in drawn if not isinstance(d, BaseException)]
        if not candidates:
            self._report.ok = False
            first = next(d for d in drawn if isinstance(d, BaseException))
            self._report.summary = f"Transformation failed: {first}"
            raise first

        best, verdicts = await select_sketch(
            [as_control_tetrad(c) for c in candidates], material
        )
        sketch = candidates[best]
        self.verdict = verdicts[best]
        self.alternatives = [
            (c, v) for i, (c, v) in enumerate(zip(candidates, verdicts)) if i != best
        ]
        self._report.ok = True
        self._report.summary = f"Transformation: {sketch.ac_plus} / {sketch.re_plus}"
        self._report.artifacts["transformation"] = sketch.model_dump()
        if n > 1:
            self._report.artifacts["attempts"] = {
                "drawn": len(candidates),
                "selected": best,
                "floors": [None if v is None else round(v.floor, 2) for v in verdicts],
            }
        return sketch
