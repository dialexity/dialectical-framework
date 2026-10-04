"""
SketchTetrad: the one-shot build — reason the tetrad whole, then persist it whole.

Three steps, two of them the existing skills unchanged:

1. `TetradSketch` — ONE thinking call over the person's words writes T, A and
   the four aspects (`concerns/tetrad_sketch.py`).
2. `IntroducePolarity(thesis, antithesis, …)` — the two-pole anchor's own step:
   classification and headline for both poles, OPPOSITE_OF with HS, Mode and
   Arousal on the antithesis, the Polarity, the source Input linked to both.
3. `ExpandPolarity(polarity_hash, given_tetrad=…)` — scores the given aspects
   (`AspectGeneration.score_given`) instead of generating them, then dedups,
   names the reading, commits, grounds and validates exactly as today.

What this replaces, where it is wired: the thesis-only `anchor`'s staged build
(headline → ladder → aspects for a pair never seen whole), measured at 14/40
coherent first tetrads on free utterances against the Consultant's one-shot
view turn at 24/40 (docs/dev-notes/antithesis-selection.md). It is NOT wired
into `anchor` until the pre-registered arm passes (`TETRAD_PROBE_MODE=oneshot`:
first-tetrad CC ≥ 20/40, antithesis a position ≥ 30/40, restatement ≤ 3/80);
until then the probe calls it directly. The staged path stays for `ingest` of
documents (many theses) and for the two-pole `anchor`/`note` (A given).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject

from dialectical_framework.agents.analyst.skills.expand_polarities import \
    ExpandPolarity
from dialectical_framework.agents.analyst.skills.introduce_polarity import \
    IntroducePolarity
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.aspect_generation import GivenTetrad
from dialectical_framework.concerns.tetrad_sketch import TetradSketch
from dialectical_framework.concerns.view_sketch import (
    ViewSketchPerspectiveDto, is_axis_name)
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.utils.progress import (expect_progress,
                                                  report_progress)

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class SketchTetrad(ReasonableConcern[list[Perspective]]):
    """One utterance → one scored, validated, persisted tetrad."""

    def __init__(
        self,
        input_hashes: Optional[list[str]] = None,
        thesis: Optional[str] = None,
        context: str = "",
        persona: Optional[str] = None,
        attempts: Optional[int] = None,
        sketch: Optional[ViewSketchPerspectiveDto] = None,
    ) -> None:
        #: The material: Inputs in the current Case — the person's turn the
        #: Advisor's `anchor` captured, or a host's paste (`capture_input`).
        #: Read through `input_context` (digest or words), and linked to both
        #: poles as their source by `IntroducePolarity`. Not the thesis: the
        #: build finds the position IN the material unless `thesis` pins it.
        self.input_hashes = list(input_hashes or [])
        #: The position to plant, when the caller already named it (`anchor`'s
        #: `thesis`): pinned in the sketch request. None = find it in the material.
        self.thesis = (thesis or "").strip() or None
        #: The model's particulars about the tension (`anchor`'s `context`);
        #: composed ahead of the material for every prompt, as on the staged path.
        self.context = (context or "").strip()
        self._persona = persona
        #: Sketches drawn in parallel, the best kept by the coherence check
        #: (`concerns/tetrad_candidates.py`; None = its default, max 3).
        self.attempts = attempts
        #: After `resolve`: the runners-up as (sketch, verdict) — texts a host
        #: can offer as "another" without a new reasoning call. Not persisted.
        self.alternatives: list = []
        #: A tetrad already drawn — one of a previous build's `alternatives` —
        #: to persist WITHOUT a new reasoning call: the person said "another"
        #: and the framework already has one. Classified, scored, grounded and
        #: validated exactly as a fresh sketch; `thesis` and `attempts` are
        #: ignored when this is given.
        self.sketch = sketch

    @inject
    async def _material(
        self, input_resolver: InputResolver = Provide[DI.input_resolver]
    ) -> str:
        """What the Inputs say, as every skill reads material: digests, words
        as the fallback, bounded. Empty when there are no Inputs."""
        if not self.input_hashes:
            return ""
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository
        from dialectical_framework.utils.input_context import input_context

        inputs = NodeRepository().find_by_hashes(self.input_hashes, node_type=Input)
        unresolved = len(self.input_hashes) - len(inputs)
        if unresolved > 0:
            self._report.artifacts["unresolved_input_hashes"] = unresolved
        return await input_context(inputs, input_resolver)

    async def resolve(self) -> list[Perspective]:
        material = await self._material()
        if self.sketch is not None:
            tension = self.sketch
            self._report.artifacts["sketch"] = tension.model_dump()
        else:
            if not material and not self.thesis:
                self._report.ok = False
                self._report.summary = "Nothing to build: no material and no thesis"
                self._report.artifacts["perspective_hashes"] = []
                return []

            expect_progress(1)
            report_progress("Thinking the tension through, whole")
            sketch = TetradSketch(persona=self._persona)
            tension = await sketch.resolve(
                material, self.context, thesis=self.thesis, attempts=self.attempts
            )
            self.alternatives = list(sketch.alternatives)
            self._report = self._report.merge(sketch.report)

        # The poles' classification reads the same material; `IntroducePolarity`
        # reads it from the Inputs itself, so only the particulars travel here.
        introduce = IntroducePolarity(
            thesis=tension.thesis,
            antithesis=tension.antithesis,
            text=self.context,
            input_hashes=self.input_hashes,
        )
        # Phase 1 commits the pair and the Polarity (HS still unknown); the
        # opposition's evaluation (phase 2, LLM only) then OVERLAPS the
        # expansion below, and phase 3 writes its result afterwards on this
        # task — one writer at a time. Measured before the split: ~12 s of
        # `AntithesisClassification` standing in the chain ahead of ~14 s of
        # scoring, grounding and validation that never needed it.
        prepared = await introduce.prepare()
        if not prepared.primary_polarity_hash:
            self._report = self._report.merge(introduce.report)
            self._report.artifacts["perspective_hashes"] = []
            return []
        result = prepared

        given = GivenTetrad(
            texts={
                POSITION_T_PLUS: tension.t_plus,
                POSITION_T_MINUS: tension.t_minus,
                POSITION_A_PLUS: tension.a_plus,
                POSITION_A_MINUS: tension.a_minus,
            },
            axes={
                key: axis
                for key, axis in (
                    ("t_plus_vs_a_minus", tension.t_plus_vs_a_minus_axis),
                    ("a_plus_vs_t_minus", tension.a_plus_vs_t_minus_axis),
                )
                if is_axis_name(axis)
            },
        )
        # Grounding: the particulars when the model named them, else the material
        # itself — on this path the person's words ARE their particulars.
        expand = ExpandPolarity(
            polarity_hash=result.primary_polarity_hash,
            grounding_context=self.context or material,
            given_tetrad=given,
        )
        classification, perspectives = await asyncio.gather(
            introduce.classify_opposition(), expand.resolve()
        )
        introduce.record_opposition(classification)
        self._report = self._report.merge(introduce.report)
        self._report = self._report.merge(expand.report)

        self._report.ok = True
        self._report.artifacts["perspective_hashes"] = [
            pp.hash for pp in perspectives if pp.hash
        ]
        # The same quality line the staged pipeline reports, for one tension:
        # no ladder ran, so there is no potential to report (`None`, honestly).
        polarities = introduce.report.artifacts.get("polarities") or []
        self._report.artifacts["polarity_quality"] = [
            {
                **entry,
                "tetrad_potential": None,
                "expanded": bool(perspectives),
                "status": "expanded" if perspectives else "failed",
            }
            for entry in polarities
        ]
        self._report.summary = (
            f"Built one tetrad whole: {tension.thesis} vs {tension.antithesis}"
            if perspectives
            else "The sketched tension did not expand"
        )
        return perspectives
