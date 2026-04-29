"""
EditTetrad: Skill for editing aspects (T+, T-, A+, A-) of a Perspective.

Handles modifications to aspects with proper validation:
- Validates each aspect against its position
- Suggests correct position if aspect doesn't fit

Editing behavior based on PP state:
- Uncommitted PP -> edit in place, commit it
- Committed PP -> clone (fork with origin_hash), edit the copy, commit it

In both cases, the returned PP is committed with all 6 positions filled.

Use EditPolarity for editing T or A.
Use PerspectiveValidation concern separately for full tetrad validation.

Uses ForkableMixin: forked PP has origin_hash pointing to the original.

Usage:
    editor = EditTetrad(
        perspective_hash="abc123...",
        changes={"T+": "New positive thesis aspect"},
    )
    result = await editor.resolve()

    if result.is_valid:
        pp = result.perspective  # Committed PP with all 6 aspects
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.aspect_classification import \
    AspectClassification
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.polarity import POSITION_A, POSITION_T
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

# Positions that are aspects (not T or A)
ASPECT_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]

# Heuristic Similarity threshold for "wrong category"
HS_WRONG_CATEGORY_THRESHOLD = 0.1


@dataclass
class EditTetradResult:
    """Result of editing aspects in a Perspective.

    Returns a Perspective:
    - If input PP was uncommitted -> edits in place, commits it
    - If input PP was committed -> clones (forks with origin_hash), edits the copy, commits it
    """

    perspective: Optional[Perspective] = None
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    changed_positions: list[str] = field(default_factory=list)
    error_message: str = ""


class EditTetrad(BaseTool, ReasonableConcern[EditTetradResult]):
    """
    Skill for editing aspects (T+, T-, A+, A-) of a Perspective with validation.

    Validates aspect edits and returns PP with updated aspects.
    Does NOT mutate the original committed Perspective (clones it instead).

    For editing T or A, use EditPolarity instead.

    Dual interface:
    - resolve() returns EditTetradResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    perspective_hash: str = Field(description="Hash of the Perspective to edit")
    changes: dict[str, str] = Field(
        description="Dict of {position: new_statement} for aspect changes (T+, T-, A+, A-)"
    )
    text: str = Field(default="", description="Optional context for classification")

    _report: ExecutionReport = PrivateAttr()
    _working_pp: Perspective = PrivateAttr()
    _original_pp: Perspective = PrivateAttr()
    _was_committed: bool = PrivateAttr()
    _changes: dict[str, str] = PrivateAttr()
    _text: str = PrivateAttr()

    @property
    def report(self) -> ExecutionReport:
        """Access the execution report."""
        return self._report

    async def call(self) -> str:
        """Resolve editing and return ExecutionReport as JSON."""
        await self.resolve()
        return str(self._report)

    async def resolve(self) -> EditTetradResult:
        """Resolve the editing operation."""
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Resolve Perspective
        pp = self._resolve_perspective(self.perspective_hash)
        if pp is None:
            result = EditTetradResult(
                is_valid=False,
                error_message=f"Perspective '{self.perspective_hash}' not found",
            )
            self._build_report(result)
            return result

        self._original_pp = pp
        self._text = self.text
        self._was_committed = pp.is_committed

        # Clean up changes dict - only accept aspect positions
        self._changes = {}
        for k, v in self.changes.items():
            if v and v.strip() and k in ASPECT_POSITIONS:
                self._changes[k] = v.strip()

        if not self._changes:
            result = EditTetradResult(
                is_valid=False,
                error_message="Must provide at least one aspect change (T+, T-, A+, A-). For T/A, use EditPolarity.",
            )
            self._build_report(result)
            return result

        # Verify PP has T and A
        current_t = self._original_pp.get_component(POSITION_T)
        current_a = self._original_pp.get_component(POSITION_A)

        if not current_t or not current_a:
            result = EditTetradResult(
                is_valid=False,
                error_message="Perspective must have T and A for aspect editing",
            )
            self._build_report(result)
            return result

        # Prepare working PP
        if self._was_committed:
            self._working_pp = pp.clone()
            self._working_pp.save()
        else:
            self._working_pp = pp
            if not self._working_pp._id:
                self._working_pp.save()

        # Handle aspect changes
        result = await self._handle_aspects_changed(current_t, current_a)

        self._build_report(result)
        return result

    async def _handle_aspects_changed(
        self,
        thesis: Statement,
        antithesis: Statement,
    ) -> EditTetradResult:
        """Handle when aspects are changed."""
        # Validate all changed aspects
        aspect_validations: dict[str, tuple[Statement, object]] = {}
        invalid_aspects: list[str] = []

        for aspect_pos in self._changes:
            aspect_stmt = self._changes[aspect_pos]

            aspect_classifier = AspectClassification()
            aspect_result = await aspect_classifier.resolve(
                thesis=thesis,
                antithesis=antithesis,
                aspect_statement=aspect_stmt,
                position=aspect_pos,
                text=self._text,
            )
            self._report = self._report.merge(aspect_classifier.report)

            if aspect_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                new_aspect = Statement(
                    text=aspect_stmt,
                    meaning=aspect_result.meaning,
                )
                new_aspect.commit()
                self._report.node_created(new_aspect)
                aspect_validations[aspect_pos] = (new_aspect, aspect_result)
            else:
                # Check other positions
                suggested = await self._find_better_aspect_position(
                    thesis, antithesis, aspect_stmt, aspect_pos
                )
                if suggested:
                    invalid_aspects.append(
                        f"{aspect_pos}: '{aspect_stmt}' looks more like {suggested['position']} "
                        f"(HS={suggested['hs']:.2f})"
                    )
                else:
                    invalid_aspects.append(
                        f"{aspect_pos}: '{aspect_stmt}' doesn't fit any aspect position "
                        f"(HS={aspect_result.heuristic_similarity:.2f})"
                    )

        if invalid_aspects:
            return EditTetradResult(
                is_valid=False,
                error_message="Invalid aspect(s): " + "; ".join(invalid_aspects),
            )

        # Fill working PP with validated aspects
        await self._fill_pp_with_aspects(aspect_validations)

        return EditTetradResult(
            perspective=self._working_pp,
            is_valid=True,
            changed_positions=list(self._changes.keys()),
        )

    async def _fill_pp_with_aspects(
        self,
        aspect_validations: dict[str, tuple[Statement, object]],
    ) -> None:
        """Fill working PP with changed aspects, copying unchanged from original."""
        pp = self._working_pp

        # Copy Polarity (T-A pair) from original if not connected
        if pp.polarity.count() == 0:
            orig_polarity_result = self._original_pp.polarity.get()
            if orig_polarity_result:
                orig_polarity, _ = orig_polarity_result
                pp.polarity.connect(
                    orig_polarity, relationship=HasPolarityRelationship()
                )

        # Handle aspects
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
                # Use new aspect
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
            else:
                # Copy from original if not already connected
                if manager.count() == 0:
                    orig_result = (
                        self._original_pp.get_relationship_manager_by_position(
                            pos
                        ).get()
                    )
                    if orig_result:
                        orig_comp, orig_rel = orig_result
                        manager.connect(
                            orig_comp,
                            relationship=rel_class(
                                alias=pos,
                                heuristic_similarity=(
                                    orig_rel.heuristic_similarity if orig_rel else None
                                ),
                                complementarity_t=(
                                    orig_rel.complementarity_t if orig_rel else None
                                ),
                                complementarity_a=(
                                    orig_rel.complementarity_a if orig_rel else None
                                ),
                            ),
                        )

        pp.commit()
        self._report.node_created(pp)

    async def _find_better_aspect_position(
        self,
        thesis: Statement,
        antithesis: Statement,
        aspect_stmt: str,
        exclude_position: str,
    ) -> Optional[dict]:
        """Check if aspect fits better in a different position."""
        other_positions = [p for p in ASPECT_POSITIONS if p != exclude_position]

        best_match = None
        best_hs = HS_WRONG_CATEGORY_THRESHOLD

        for pos in other_positions:
            try:
                classifier = AspectClassification()
                result = await classifier.resolve(
                    thesis=thesis,
                    antithesis=antithesis,
                    aspect_statement=aspect_stmt,
                    position=pos,
                    text=self._text,
                )
                if result.heuristic_similarity > best_hs:
                    best_hs = result.heuristic_similarity
                    best_match = {"position": pos, "hs": result.heuristic_similarity}
            except Exception:
                continue

        return best_match

    def _resolve_perspective(self, pp_hash: str) -> Optional[Perspective]:
        """Resolve hash to Perspective."""
        repo = NodeRepository()
        try:
            node = repo.find_by_hash(pp_hash)
            if isinstance(node, Perspective):
                return node
        except ValueError:
            try:
                node = repo.find_by_prefix(pp_hash)
                if isinstance(node, Perspective):
                    return node
            except ValueError:
                pass
        return None

    def _build_report(self, result: EditTetradResult) -> None:
        """Build execution report from result."""
        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["changes"] = self.changes
        self._report.artifacts["was_committed"] = (
            self._was_committed if hasattr(self, "_was_committed") else None
        )

        if result.perspective:
            if result.perspective.hash:
                self._report.artifacts["perspective_hash"] = result.perspective.hash
            if result.perspective.origin_hash:
                self._report.artifacts["origin_hash"] = result.perspective.origin_hash

        if result.warnings:
            self._report.artifacts["warnings"] = result.warnings

        if result.changed_positions:
            self._report.artifacts["changed_positions"] = result.changed_positions

        self._report.ok = result.is_valid
        if result.is_valid:
            positions = (
                ", ".join(result.changed_positions)
                if result.changed_positions
                else "none"
            )
            action = (
                "Forked and edited"
                if (hasattr(self, "_was_committed") and self._was_committed)
                else "Edited"
            )
            self._report.summary = f"{action} aspects: {positions}"
        else:
            self._report.summary = f"Edit failed: {result.error_message}"
