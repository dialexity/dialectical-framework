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

ALL_POSITIONS = {POSITION_T, POSITION_A, POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS}
POLARITY_POSITIONS = {POSITION_T, POSITION_A}
ASPECT_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]

HS_WRONG_CATEGORY_THRESHOLD = 0.1


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

        t_classifier = StatementClassification()
        t_classification = await t_classifier.resolve(statement=new_t_text, text=self.text)
        self._report = self._report.merge(t_classifier.report)

        new_t = Statement(text=new_t_text, meaning=t_classification.meaning)
        new_t.commit()
        self._report.node_created(new_t)

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

        t_classifier = StatementClassification()
        t_classification = await t_classifier.resolve(statement=new_t_text, text=self.text)
        self._report = self._report.merge(t_classifier.report)

        new_t = Statement(text=new_t_text, meaning=t_classification.meaning)
        new_t.commit()
        self._report.node_created(new_t)

        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.resolve(thesis=new_t, antithesis_statement=current_a.text, text=self.text)
        self._report = self._report.merge(a_classifier.report)

        warnings: list[str] = []
        antithesis_to_use = current_a
        a_hs = a_validation.heuristic_similarity
        regenerated: list[str] = []

        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
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

        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.resolve(thesis=current_t, antithesis_statement=new_a_text, text=self.text)
        self._report = self._report.merge(a_classifier.report)

        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            current_a = self._original_pp.get_component(POSITION_A)
            if current_a:
                for aspect_pos in ASPECT_POSITIONS:
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

        for aspect_pos, aspect_text in changes.items():
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
    concern = EditPerspective(perspective_hash=perspective_hash, changes=changes, text=text)
    await concern.resolve()
    return str(concern.report)
