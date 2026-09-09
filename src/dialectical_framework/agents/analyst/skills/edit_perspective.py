"""
EditPerspective: Unified skill for editing any position of a Perspective.

Accepts changes to any combination of positions (T, A, T+, T-, A+, A-) and routes:
- If T or A changed → polarity editing (regenerates all aspects)
- If only aspects changed → tetrad editing (validates aspect coherence)

Creates a new PP linked to the original via CHANGED_TO relationship (evolution, not
replacement). The caller decides what to do with the new PP — add to a Nexus, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Optional, cast

from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.antithesis_classification import (
    AntithesisClassification,
)
from dialectical_framework.concerns.antithesis_extraction import AntithesisExtraction
from dialectical_framework.concerns.aspect_classification import (
    AspectClassification,
    AspectClassificationResult,
)
from dialectical_framework.concerns.aspect_generation import AspectGeneration
from dialectical_framework.concerns.control_statements_check import (
    ControlStatementsCheck,
)
from dialectical_framework.concerns.diagonal_oppositions_check import (
    DiagonalOppositionsCheck,
)
from dialectical_framework.concerns.statement_classification import (
    StatementClassification,
)
from dialectical_framework.graph.nodes.perspective import (
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    Perspective,
)
from dialectical_framework.graph.nodes.polarity import POSITION_A, POSITION_T, Polarity
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship,
    APlusRelationship,
    HasPolarityRelationship,
    PolarityRelationship,
    TMinusRelationship,
    TPlusRelationship,
)
from dialectical_framework.graph.relationships.changed_to_relationship import (
    ChangedToRelationship,
)
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.estimation import (
    ArousalEstimation, ModeEstimation)
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.utils.progress import (expect_progress,
                                                  progress_hash_key,
                                                  progress_scope,
                                                  report_progress)

ALL_POSITIONS = {POSITION_T, POSITION_A, POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS}
POLARITY_POSITIONS = {POSITION_T, POSITION_A}
ASPECT_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]

HS_WRONG_CATEGORY_THRESHOLD = 0.1


def _checking_wording_label(index: int, total: int) -> str:
    """The per-part label for the aspect-only edit path.

    A helper rather than an f-string at the site so the singular case has no
    parenthetical at all: one changed part is by far the common edit, and
    "(1 of 1)" beside a host's spinner is noise that says nothing.

    Says "where you put it" and not which position, deliberately. `T+`/`A-` are the
    framework's names for the corners of a tetrad, and the whole contract of this
    channel is that a host may render these lines to a person verbatim — the
    machinery stays on this side of the seam
    (`tests/test_ingest_progress.py`'s banned-vocabulary list).
    """
    if total <= 1:
        return "Checking your wording fits where you put it"
    return f"Checking your wording fits where you put it ({index} of {total})"


@dataclass
class EditPerspectiveResult:
    """Result of editing a Perspective."""

    perspective: Optional[Perspective] = None
    is_valid: bool = True
    changed_positions: list[str] = field(default_factory=list)
    regenerated_positions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_message: str = ""


class EditPerspective(ReasonableConcern[EditPerspectiveResult]):
    """
    Unified skill for editing any position(s) of a Perspective.

    Routes internally based on which positions are changing:
    - T or A changing → regenerates all aspects
    - Only aspects changing → validates coherence (diagonal oppositions, control statements)

    Creates a new PP and connects old→new via CHANGED_TO (analytical lineage).
    Does not discard the old PP or modify Nexus memberships — that's up to the caller.

    PROGRESS: no fixed step count, deliberately
    ===========================================
    Every other instrumented skill either declares its denominator up front or
    exposes a `PROGRESS_STEPS` constant (`IntroducePolarity`, pinned by
    `tests/test_progress.py`). This one cannot honestly do either: what it costs is
    decided by which positions changed, and then again by whether they validate.

        both T and A changed  3 awaits  (classify T, weigh the pair, generate four)
        T changed             3 awaits  + `AntithesisExtraction`'s own chain if the
                                          existing A no longer opposes the new T
        A changed             2 awaits  happy; 1 + up to 4 on the refusal path
        aspects only        N+2 awaits  (N = positions changed, 1-4), and the two
                                          coherence checks gather 2 calls each, so
                                          the four-aspect edit is 8 calls in 6 waits;
                                          a rejected aspect adds 3 and then bails

    So each step is declared at its own site, immediately before its own await, and
    the denominator grows as the path reveals itself. The cost of that is the
    backwards-jump caveat `utils/progress.py` documents — a host's bar can shrink
    when a branch adds work. The alternative is worse: a count declared at entry
    would be wrong on every path that refuses, and a step declared for work that a
    guard then skips is a phantom, indistinguishable to a host from a step that
    failed. NOTHING is declared above a guard that can return without a provider call.

    None of this is measured. No probe covers `edit_perspective` yet — the counts
    above are read off the code, not off a run, and the labels' timings are unknown.
    """

    def __init__(self, perspective_hash: str, changes: dict[str, str], text: str = "") -> None:
        self.perspective_hash = perspective_hash
        self.changes = changes
        self.text = text
        self._working_pp: Optional[Perspective] = None
        self._original_pp: Optional[Perspective] = None
        self._was_committed: bool = False

    async def resolve(self) -> EditPerspectiveResult:
        valid_changes = {k: v.strip() for k, v in self.changes.items() if k in ALL_POSITIONS and v and v.strip()}

        if not valid_changes:
            result = EditPerspectiveResult(
                is_valid=False,
                error_message="No valid changes. Accepted positions: T, A, T+, T-, A+, A-",
            )
            self._build_report(result)
            return result

        # Resolve existing PP
        pp = self._resolve_perspective(self.perspective_hash)
        if pp is None:
            result = EditPerspectiveResult(
                is_valid=False,
                error_message=f"Perspective '{self.perspective_hash}' not found",
            )
            self._build_report(result)
            return result

        self._original_pp = pp
        self._was_committed = pp.is_committed

        # Prepare working PP (clone if committed)
        if self._was_committed:
            working_pp = pp.clone()
            # Drop the inherited reading (intent): the axis was named for the
            # ORIGINAL aspects — after a user edit it may no longer describe
            # this tetrad, and a stale reading is worse than none.
            working_pp.intent = None
            working_pp.save()
            self._report.node_created(working_pp)
        else:
            working_pp = pp
            if not working_pp._id:
                working_pp.save()
                self._report.node_created(working_pp)
        self._working_pp = working_pp

        # Route based on what's changing
        has_polarity_changes = bool(valid_changes.keys() & POLARITY_POSITIONS)

        if has_polarity_changes:
            polarity_changes = {k: v for k, v in valid_changes.items() if k in POLARITY_POSITIONS}
            result = await self._handle_polarity_edit(polarity_changes)
        else:
            aspect_changes = {k: v for k, v in valid_changes.items() if k in ASPECT_POSITIONS}
            result = await self._handle_tetrad_edit(aspect_changes)

        if not result.is_valid:
            self._discard_working_pp()
        elif result.is_valid and self._was_committed and self._original_pp:
            self._original_pp.changed_to.connect(
                result.perspective,
                relationship=ChangedToRelationship(
                    changed_positions=list(valid_changes.keys()),
                ),
            )
            self._report.relationship_created(
                self._original_pp.changed_to,
                self._original_pp,
                result.perspective,
                patch={"changed_positions": list(valid_changes.keys())},
            )

        self._build_report(result)
        return result

    # ─── Polarity editing (T/A change → regenerate all aspects) ───

    async def _handle_polarity_edit(self, changes: dict[str, str]) -> EditPerspectiveResult:
        """Handle T and/or A changes — regenerates all aspects."""
        t_changed = POSITION_T in changes
        a_changed = POSITION_A in changes

        if t_changed and a_changed:
            return await self._handle_both_ta_changed(changes[POSITION_T], changes[POSITION_A])
        if t_changed:
            return await self._handle_thesis_change(changes[POSITION_T])
        return await self._handle_antithesis_change(changes[POSITION_A])

    async def _handle_both_ta_changed(self, new_t_text: str, new_a_text: str) -> EditPerspectiveResult:
        assert self._working_pp is not None

        # Both poles are the person's own wording here, which is precisely
        # `introduce_polarity`'s situation — so its two labels are reused verbatim
        # rather than paraphrased. A person who introduces a tension and then
        # corrects it should not be able to tell from the vocabulary which of the
        # two tools they are watching.
        expect_progress(1)
        report_progress("Taking in both sides of what you described")
        t_classifier = StatementClassification()
        t_classification = await t_classifier.resolve(statement=new_t_text, text=self.text)
        self._report = self._report.merge(t_classifier.report)

        new_t = Statement(text=new_t_text, meaning=t_classification.meaning)
        new_t.commit()
        self._report.node_created(new_t)

        expect_progress(1)
        report_progress("Weighing how strongly the two pull against each other")
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.resolve(thesis=new_t, antithesis_statement=new_a_text, text=self.text)
        self._report = self._report.merge(a_classifier.report)

        warnings: list[str] = []
        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            warnings.append(f"Very low HS={a_validation.heuristic_similarity:.2f} between T and A")

        new_a = Statement(text=new_a_text, meaning=a_validation.meaning)
        new_a.commit()
        self._report.node_created(new_a)

        await self._fill_pp_and_regenerate_aspects(
            thesis=new_t, antithesis=new_a, a_hs=a_validation.heuristic_similarity,
            mode_value=a_validation.mode_value, arousal_value=a_validation.arousal_value,
        )

        self._create_edit_rationale(
            new_t,
            f"Both T and A changed. New opposition: '{new_t_text}' <-> '{new_a_text}' "
            f"(HS={a_validation.heuristic_similarity:.2f})",
        )

        return EditPerspectiveResult(
            perspective=self._working_pp,
            is_valid=True,
            warnings=warnings,
            changed_positions=[POSITION_T, POSITION_A],
            regenerated_positions=list(ASPECT_POSITIONS),
        )

    async def _handle_thesis_change(self, new_t_text: str) -> EditPerspectiveResult:
        assert self._original_pp is not None
        assert self._working_pp is not None

        current_a = self._original_pp.get_component(POSITION_A)
        if not current_a:
            return EditPerspectiveResult(is_valid=False, error_message="Original Perspective has no antithesis")

        # Declared BELOW the `current_a` guard, not above it: that guard returns
        # without a single provider call, and a step declared over it would be a
        # phantom — announced, never reported, and to a host indistinguishable from
        # one that failed.
        #
        # Singular wording, because only one side was retyped. `anchor_theses` says
        # the same sentence for the same work (one statement of the person's own,
        # classified once).
        expect_progress(1)
        report_progress("Taking in the position you named")
        t_classifier = StatementClassification()
        t_classification = await t_classifier.resolve(statement=new_t_text, text=self.text)
        self._report = self._report.merge(t_classifier.report)

        new_t = Statement(text=new_t_text, meaning=t_classification.meaning)
        new_t.commit()
        self._report.node_created(new_t)

        expect_progress(1)
        report_progress("Weighing how strongly the two pull against each other")
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.resolve(thesis=new_t, antithesis_statement=current_a.text, text=self.text)
        self._report = self._report.merge(a_classifier.report)

        warnings: list[str] = []
        antithesis_to_use = current_a
        a_hs = a_validation.heuristic_similarity
        regenerated: list[str] = []

        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            # NOTHING is declared for this branch, and it is the longest one on the
            # path — `AntithesisExtraction.resolve` declares its own steps ("Weighing
            # what could stand against this", then "Judging how strongly each
            # opposition holds") and notes each angle as it comes back. A step here
            # would publish in the same instant as extraction's own and be superseded
            # before a person could read it: the 0.0s flash that moved the extraction
            # label out of `AnalysisPipeline` and into `FindPolarities.resolve()`.
            extractor = AntithesisExtraction()
            antitheses = await extractor.resolve(thesis=new_t, text=self.text)
            self._report = self._report.merge(extractor.report)

            if not antitheses:
                return EditPerspectiveResult(
                    is_valid=False,
                    error_message=(
                        f"Cannot generate valid antithesis for new thesis. "
                        f"Original A has HS={a_validation.heuristic_similarity:.2f}"
                    ),
                )

            best_antithesis = max(antitheses, key=lambda a: a.heuristic_similarity)
            antithesis_to_use = best_antithesis.component
            a_hs = best_antithesis.heuristic_similarity
            regenerated.append(POSITION_A)
            warnings.append(f"Antithesis regenerated (original had HS={a_validation.heuristic_similarity:.2f})")

        await self._fill_pp_and_regenerate_aspects(thesis=new_t, antithesis=antithesis_to_use, a_hs=a_hs)
        self._create_edit_rationale(new_t, f"Thesis changed to '{new_t_text}' (HS={a_hs:.2f})")
        regenerated.extend(ASPECT_POSITIONS)

        return EditPerspectiveResult(
            perspective=self._working_pp,
            is_valid=True,
            warnings=warnings,
            changed_positions=[POSITION_T],
            regenerated_positions=regenerated,
        )

    async def _handle_antithesis_change(self, new_a_text: str) -> EditPerspectiveResult:
        assert self._original_pp is not None
        assert self._working_pp is not None

        current_t = self._original_pp.get_component(POSITION_T)
        if not current_t:
            return EditPerspectiveResult(is_valid=False, error_message="Original Perspective has no thesis")

        # Below the guard, for the same reason as the thesis path above.
        expect_progress(1)
        report_progress("Weighing how strongly the two pull against each other")
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.resolve(thesis=current_t, antithesis_statement=new_a_text, text=self.text)
        self._report = self._report.merge(a_classifier.report)

        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            current_a = self._original_pp.get_component(POSITION_A)
            if current_a:
                # Up to four more provider calls before the person is told "no".
                # This is a REFUSAL path, which makes it the worst kind of silence to
                # leave: the wait is indistinguishable from a wait that is going to
                # succeed, and it ends in nothing being written to the graph, so
                # there is no node event to cover it either.
                for aspect_pos in ASPECT_POSITIONS:
                    # One step per iteration, declared inside the loop and immediately
                    # before the await. These calls are SEQUENTIAL, so each genuinely
                    # starts at its own moment and a step per iteration says something
                    # true — the gathered case, where N steps would share one instant,
                    # is what `note_progress` is for and does not apply here. No
                    # fraction in the label: the loop returns early the moment
                    # something fits, and a line that stops at "2 of 4" reads as
                    # broken rather than as finished.
                    expect_progress(1)
                    report_progress("Checking where what you wrote fits better")
                    aspect_classifier = AspectClassification()
                    try:
                        aspect_result = await aspect_classifier.resolve(
                            thesis=current_t, antithesis=current_a,
                            aspect_statement=new_a_text, position=aspect_pos, text=self.text,
                        )
                        if aspect_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                            return EditPerspectiveResult(
                                is_valid=False,
                                error_message=(
                                    f"'{new_a_text}' looks more like {aspect_pos} "
                                    f"(HS={aspect_result.heuristic_similarity:.2f}) than an antithesis."
                                ),
                            )
                    except Exception:
                        continue

            return EditPerspectiveResult(
                is_valid=False,
                error_message=(
                    f"'{new_a_text}' is not a valid antithesis for '{current_t.text}' "
                    f"(HS={a_validation.heuristic_similarity:.2f})"
                ),
            )

        new_a = Statement(text=new_a_text, meaning=a_validation.meaning)
        new_a.commit()
        self._report.node_created(new_a)

        await self._fill_pp_and_regenerate_aspects(
            thesis=current_t, antithesis=new_a, a_hs=a_validation.heuristic_similarity,
            mode_value=a_validation.mode_value, arousal_value=a_validation.arousal_value,
        )
        self._create_edit_rationale(
            new_a, f"Antithesis changed to '{new_a_text}' (HS={a_validation.heuristic_similarity:.2f})"
        )

        return EditPerspectiveResult(
            perspective=self._working_pp,
            is_valid=True,
            changed_positions=[POSITION_A],
            regenerated_positions=list(ASPECT_POSITIONS),
        )

    async def _fill_pp_and_regenerate_aspects(
        self,
        thesis: Statement,
        antithesis: Statement,
        a_hs: float,
        mode_value: Optional[float] = None,
        arousal_value: Optional[float] = None,
    ) -> None:
        """Fill working PP with T, A (via Polarity) and regenerate all aspects."""
        assert self._working_pp is not None
        pp = self._working_pp

        polarity = Polarity()
        polarity.set_t(thesis, heuristic_similarity=1.0)
        polarity.set_a(antithesis, heuristic_similarity=a_hs)
        polarity.commit()
        self._report.node_created(polarity)

        if mode_value is not None or arousal_value is not None:
            manager = EstimationManager()
            if mode_value is not None:
                mode_est = manager.upsert_estimation(
                    antithesis, ModeEstimation, mode_value
                )
                if mode_est:
                    self._report.node_updated(mode_est, patch={"value": mode_value})
            if arousal_value is not None:
                arousal_est = manager.upsert_estimation(
                    antithesis, ArousalEstimation, arousal_value
                )
                if arousal_est:
                    self._report.node_updated(arousal_est, patch={"value": arousal_value})

        pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
        self._report.relationship_created(pp.polarity, pp, polarity)

        # ONE step for all four, because `AspectGeneration` makes ONE provider call
        # when handed all four positions (`_generate_tetrad` — the diagonal pairs are
        # generated together so they genuinely contradict). Four steps here would be
        # four events for one call, which is the fan-out defect inverted.
        #
        # Declared here rather than at the three callers: all of them route through
        # this method, and the label describes the generation, which begins on the
        # next line. `expand_polarities` says the same sentence for the same call.
        expect_progress(1)
        report_progress("Working out how each side helps and how each overreaches")
        generator = AspectGeneration()
        generated_aspects = await generator.resolve(perspective=pp, positions=ASPECT_POSITIONS, text=self.text)
        self._report = self._report.merge(generator.report)

        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for aspect in generated_aspects:
            rel_class = rel_classes[aspect.position]
            manager = pp.get_relationship_manager_by_position(aspect.position)
            manager.connect(
                aspect.component,
                relationship=rel_class(
                    alias=aspect.position,
                    heuristic_similarity=aspect.heuristic_similarity,
                    complementarity_t=aspect.complementarity_t,
                    complementarity_a=aspect.complementarity_a,
                ),
            )
            self._report.relationship_created(
                manager, aspect.component, pp,
                meta={"position": aspect.position},
            )

        pp.commit()
        self._report.node_committed(pp)

    # ─── Tetrad editing (aspect changes only → validate coherence) ───

    async def _handle_tetrad_edit(self, changes: dict[str, str]) -> EditPerspectiveResult:
        """Handle aspect-only changes with full validation pipeline."""
        assert self._working_pp is not None
        assert self._original_pp is not None

        current_t = self._original_pp.get_component(POSITION_T)
        current_a = self._original_pp.get_component(POSITION_A)

        if not current_t or not current_a:
            return EditPerspectiveResult(
                is_valid=False,
                error_message="Perspective must have T and A for aspect editing",
            )

        # Validate all changed aspects
        aspect_validations: dict[str, tuple[Statement, AspectClassificationResult]] = {}
        invalid_aspects: list[str] = []

        # A step per changed part, and here a FRACTION is honest where it was not in
        # the refusal probe above: this loop runs to completion for every valid
        # aspect, and `len(changes)` is the whole of what the person is waiting
        # through in this phase. Same rule as `SourceDigest`'s "Reading part 3 of 4"
        # — a number shown to a person is a promise about the whole, so only a window
        # that knows its whole may make one. Nothing gathers this loop: `edit_perspective`
        # opens one scope per call and keys it by the node, so there is no sibling
        # chain whose count could interleave with this one.
        total_changes = len(changes)
        for index, (aspect_pos, aspect_text) in enumerate(changes.items(), start=1):
            expect_progress(1)
            report_progress(_checking_wording_label(index, total_changes))
            aspect_classifier = AspectClassification()
            aspect_result = await aspect_classifier.resolve(
                thesis=current_t, antithesis=current_a,
                aspect_statement=aspect_text, position=aspect_pos, text=self.text,
            )
            self._report = self._report.merge(aspect_classifier.report)

            if aspect_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                new_aspect = Statement(text=aspect_text, meaning=aspect_result.meaning)
                new_aspect.commit()
                self._report.node_created(new_aspect)
                aspect_validations[aspect_pos] = (new_aspect, aspect_result)
            else:
                suggested = await self._find_better_aspect_position(
                    current_t, current_a, aspect_text, aspect_pos
                )
                if suggested:
                    invalid_aspects.append(
                        f"{aspect_pos}: '{aspect_text}' looks more like {suggested['position']} "
                        f"(HS={suggested['hs']:.2f})"
                    )
                else:
                    invalid_aspects.append(
                        f"{aspect_pos}: '{aspect_text}' doesn't fit any aspect position "
                        f"(HS={aspect_result.heuristic_similarity:.2f})"
                    )

        if invalid_aspects:
            return EditPerspectiveResult(
                is_valid=False,
                error_message="Invalid aspect(s): " + "; ".join(invalid_aspects),
            )

        # Fill working PP with validated aspects
        self._fill_pp_with_aspects(aspect_validations)

        # Validate tetrad coherence
        coherence_errors = await self._validate_tetrad_coherence()
        if coherence_errors:
            return EditPerspectiveResult(
                is_valid=False,
                error_message="Tetrad coherence violated: " + "; ".join(coherence_errors),
            )

        self._working_pp.commit()
        self._report.node_committed(self._working_pp)

        return EditPerspectiveResult(
            perspective=self._working_pp,
            is_valid=True,
            changed_positions=list(changes.keys()),
        )

    def _fill_pp_with_aspects(
        self, aspect_validations: dict[str, tuple[Statement, AspectClassificationResult]]
    ) -> None:
        """Fill working PP with changed aspects, copying unchanged from original."""
        assert self._working_pp is not None
        assert self._original_pp is not None
        pp = self._working_pp

        # Copy Polarity from original if not connected
        if pp.polarity.count() == 0:
            orig_polarity_result = self._original_pp.polarity.get()
            if orig_polarity_result:
                orig_polarity, _ = orig_polarity_result
                pp.polarity.connect(orig_polarity, relationship=HasPolarityRelationship())
                self._report.relationship_created(pp.polarity, pp, orig_polarity)

        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for pos in ASPECT_POSITIONS:
            manager = pp.get_relationship_manager_by_position(pos)
            rel_class = rel_classes[pos]

            if pos in aspect_validations:
                new_aspect, aspect_result = aspect_validations[pos]
                manager.connect(
                    new_aspect,
                    relationship=rel_class(
                        alias=pos,
                        heuristic_similarity=aspect_result.heuristic_similarity,
                        complementarity_t=aspect_result.complementarity_t,
                        complementarity_a=aspect_result.complementarity_a,
                    ),
                )
                self._report.relationship_created(
                    manager, pp, new_aspect, meta={"position": pos}
                )
            else:
                if manager.count() == 0:
                    orig_result = self._original_pp.get_relationship_manager_by_position(pos).get()
                    if orig_result:
                        orig_comp, orig_rel_raw = orig_result
                        orig_rel = cast(PolarityRelationship, orig_rel_raw)
                        manager.connect(
                            orig_comp,
                            relationship=rel_class(
                                alias=pos,
                                heuristic_similarity=orig_rel.heuristic_similarity,
                                complementarity_t=getattr(orig_rel, "complementarity_t", None),
                                complementarity_a=getattr(orig_rel, "complementarity_a", None),
                            ),
                        )
                        self._report.relationship_created(
                            manager, pp, orig_comp, meta={"position": pos}
                        )

    async def _validate_tetrad_coherence(self) -> list[str]:
        """Run diagonal opposition and control statement checks for user-edited tetrads.

        Includes DiagonalContradiction (unlike PerspectiveValidation) because user edits
        bypass the generation prompt that normally enforces diagonal structure.
        """
        assert self._working_pp is not None
        pp = self._working_pp
        errors: list[str] = []

        # Two steps for two checks, not one for the phase. Each concern gathers two
        # provider calls internally, but they are awaited one after the other, so a
        # single label would cover a stretch in which one of them starts, finishes and
        # is replaced — the shape `TestOneLabelNeverCoversAGatheredFanOut` was written
        # for. Each is declared immediately before its own `await`, so a `ValueError`
        # out of the first cannot leave the second's step declared and unreported.
        expect_progress(1)
        report_progress("Checking that opposing sides really do pull apart")
        diag_checker = DiagonalOppositionsCheck()
        try:
            diag_result = await diag_checker.resolve(perspective=pp, text=self.text)
            self._report = self._report.merge(diag_checker.report)

            if not diag_result.is_valid:
                if diag_result.t_plus_vs_a_minus_score < 0.7:
                    errors.append(
                        f"T+ vs A- contradiction too weak "
                        f"(score={diag_result.t_plus_vs_a_minus_score:.2f}, "
                        f"reason: {diag_result.t_plus_vs_a_minus_reasoning})"
                    )
                if diag_result.a_plus_vs_t_minus_score < 0.7:
                    errors.append(
                        f"A+ vs T- contradiction too weak "
                        f"(score={diag_result.a_plus_vs_t_minus_score:.2f}, "
                        f"reason: {diag_result.a_plus_vs_t_minus_reasoning})"
                    )
        except ValueError:
            pass

        expect_progress(1)
        report_progress("Checking that each side's strength needs the other")
        ctrl_checker = ControlStatementsCheck()
        try:
            ctrl_result = await ctrl_checker.resolve(perspective=pp, text=self.text)
            self._report = self._report.merge(ctrl_checker.report)

            if not ctrl_result.is_coherent:
                if ctrl_result.t_plus_without_a_plus_yields_t_minus_score < 0.7:
                    errors.append(
                        f"Control statement '{ctrl_result.t_plus_without_a_plus_yields_t_minus_statement}' "
                        f"not coherent (score={ctrl_result.t_plus_without_a_plus_yields_t_minus_score:.2f}, "
                        f"reason: {ctrl_result.t_plus_without_a_plus_yields_t_minus_reasoning})"
                    )
                if ctrl_result.a_plus_without_t_plus_yields_a_minus_score < 0.7:
                    errors.append(
                        f"Control statement '{ctrl_result.a_plus_without_t_plus_yields_a_minus_statement}' "
                        f"not coherent (score={ctrl_result.a_plus_without_t_plus_yields_a_minus_score:.2f}, "
                        f"reason: {ctrl_result.a_plus_without_t_plus_yields_a_minus_reasoning})"
                    )
        except ValueError:
            pass

        return errors

    async def _find_better_aspect_position(
        self, thesis: Statement, antithesis: Statement, aspect_text: str, exclude_position: str
    ) -> Optional[dict]:
        """Check if aspect fits better in a different position."""
        other_positions = [p for p in ASPECT_POSITIONS if p != exclude_position]
        best_match = None
        best_hs = HS_WRONG_CATEGORY_THRESHOLD

        for pos in other_positions:
            # Three more sequential calls, and the person is already past a failed
            # check when this starts — same reasoning as the antithesis refusal probe.
            # This loop DOES visit every position (a raising call `continue`s rather
            # than breaking), so a fraction would be truthful here; it is left off
            # anyway, because the antithesis probe publishes the same sentence and
            # cannot carry one. One line, one wording.
            expect_progress(1)
            report_progress("Checking where what you wrote fits better")
            try:
                classifier = AspectClassification()
                result = await classifier.resolve(
                    thesis=thesis, antithesis=antithesis,
                    aspect_statement=aspect_text, position=pos, text=self.text,
                )
                if result.heuristic_similarity > best_hs:
                    best_hs = result.heuristic_similarity
                    best_match = {"position": pos, "hs": result.heuristic_similarity}
            except Exception:
                continue

        return best_match

    # ─── Shared helpers ───

    def _discard_working_pp(self) -> None:
        """Delete the uncommitted working PP from the graph."""
        if self._working_pp is None:
            return
        from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository
        repo = PerspectiveRepository()
        repo.discard_uncommitted(self._working_pp)

    def _create_edit_rationale(self, component: Statement, text: str) -> None:
        """Create and attach rationale for the edit."""
        rationale = Rationale(text=f"Edit: {text}")
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)

    @staticmethod
    def _resolve_perspective(pp_hash: str) -> Optional[Perspective]:
        """Resolve hash or prefix to Perspective."""
        repo = NodeRepository()
        try:
            node = repo.find_by_hash(pp_hash)
            if isinstance(node, Perspective):
                return node
        except ValueError:
            pass
        return None

    def _build_report(self, result: EditPerspectiveResult) -> None:
        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["changes"] = self.changes
        self._report.artifacts["was_committed"] = self._was_committed

        if result.perspective and result.perspective.hash:
            self._report.artifacts["perspective_hash"] = result.perspective.hash

        if result.warnings:
            self._report.artifacts["warnings"] = result.warnings

        if result.changed_positions:
            self._report.artifacts["changed_positions"] = result.changed_positions

        if result.regenerated_positions:
            self._report.artifacts["regenerated_positions"] = result.regenerated_positions

        self._report.ok = result.is_valid
        if result.is_valid:
            positions = ", ".join(result.changed_positions) if result.changed_positions else "none"
            self._report.summary = f"Edited {positions}"
            if result.regenerated_positions:
                self._report.summary += f" (regenerated: {', '.join(result.regenerated_positions)})"
        else:
            self._report.summary = f"Edit failed: {result.error_message}"


@llm.tool
async def edit_perspective(
    perspective_hash: Annotated[str, Field(description="Hash of the Perspective to edit")],
    changes: Annotated[dict[str, str], Field(description="Positions to change: {'T': 'new text', 'A+': 'new text', ...}. Valid keys: T, A, T+, T-, A+, A-")],
    text: Annotated[str, Field(description="Optional context for validation and regeneration")] = "",
) -> str:
    """Edit any position(s) of a Perspective. Changing T or A regenerates all aspects automatically. Changing only aspects (T+/T-/A+/A-) validates coherence. Creates a new Perspective linked to the original via CHANGED_TO lineage."""
    # The scope belongs HERE and not in `resolve()`: this is the only entry point
    # that is an action a person took, and `resolve()` must stay composable — an
    # inner scope would defer to whatever installed one anyway, but a tool that
    # opens its own is the difference between events reaching a host and being
    # dropped. Nothing upstream installs one; the Analyst calls this tool directly.
    #
    # Keyed by the NODE, like `deepen`, `generate_synthesis` and
    # `explore_transformations`, rather than by hashed content like `ingest`,
    # `anchor`, `analyze` and `record_decision`. The subject of this tool is a
    # Perspective, and its hash is already an opaque id, so there is no person's
    # text to hide from a host that renders the key. The `changes` values ARE the
    # person's own words and are deliberately NOT folded in — which costs one thing,
    # stated plainly: two DIFFERENT edits of the SAME Perspective in flight at once
    # would share a stream. That is not a shape the Analyst produces (the second
    # edit's target is the new Perspective the first one created), and the
    # alternative was a fifth copy of the sha256 key one-liner.
    #
    # `perspective_hash` is RAW MODEL OUTPUT at this point, so the key goes through
    # `progress_hash_key` like every other hash-keyed tool's — the bracket trap and
    # why only the KEY is sanitised are argued there. What a malformed hash should do
    # to the edit itself stays `_resolve_perspective`'s decision.
    with progress_scope("edit", key=progress_hash_key(perspective_hash)):
        concern = EditPerspective(perspective_hash=perspective_hash, changes=changes, text=text)
        await concern.resolve()
        return str(concern.report)
