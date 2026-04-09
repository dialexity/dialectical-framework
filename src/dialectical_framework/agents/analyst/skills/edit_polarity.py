"""
EditPolarity: Skill for editing T or A components of a WisdomUnit.

Handles modifications to T or A with proper validation and regeneration:
- Changing T -> validate A compatibility, regenerate A if needed, regenerate poles
- Changing A -> validate T compatibility, handle misclassification
- Changing both T and A together

Editing behavior based on WU state:
- Uncommitted WU -> edit in place, commit it
- Committed WU -> clone (fork with origin_hash), edit the copy, commit it

In both cases, the returned WU is committed with all 6 poles set.

Use EditTetrad for editing poles (T+, T-, A+, A-).
Use WisdomUnitValidation capability separately for full tetrad validation.

Uses ForkableMixin: forked WU has origin_hash pointing to the original.

Usage:
    editor = EditPolarity(
        wisdom_unit_hash="abc123...",
        changes={"T": "New thesis statement"},
    )
    result = await editor.execute()

    if result.is_valid:
        wu = result.wisdom_unit  # Committed WU with all 6 poles
        if result.warnings:
            print("Edit-time warnings:", result.warnings)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.executable_capability import \
    ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.features.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.features.antithesis_extraction import \
    AntithesisExtraction
from dialectical_framework.features.pole_classification import \
    PoleClassification
from dialectical_framework.features.pole_generation import PoleGeneration
from dialectical_framework.features.statement_classification import \
    StatementClassification
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.polarity import (POSITION_A, POSITION_T,
                                                        Polarity)
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wisdom_unit import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           WisdomUnit)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

# Positions that are poles (not T or A)
POLE_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]

# Heuristic Similarity threshold for "wrong category"
HS_WRONG_CATEGORY_THRESHOLD = 0.1


@dataclass
class EditPolarityResult:
    """Result of editing T or A in a WisdomUnit.

    Returns a WisdomUnit:
    - If input WU was uncommitted -> edits in place, commits it
    - If input WU was committed -> clones (forks with origin_hash), edits the copy, commits it

    Use WisdomUnitValidation capability separately if full validation is needed.
    """

    wisdom_unit: Optional[WisdomUnit] = None
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    changed_positions: list[str] = field(default_factory=list)
    regenerated_positions: list[str] = field(default_factory=list)
    error_message: str = ""


class EditPolarity(BaseTool, ExecutableCapability[EditPolarityResult]):
    """
    Skill for editing T or A components of a WisdomUnit with validation.

    Validates edits, regenerates affected components (including poles), and returns WU.
    Does NOT mutate the original committed WisdomUnit (clones it instead).

    For editing poles (T+, T-, A+, A-), use EditTetrad instead.

    Dual interface:
    - execute() returns EditPolarityResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    wisdom_unit_hash: str = Field(description="Hash of the WisdomUnit to edit")
    changes: dict[str, str] = Field(
        description="Dict of {position: new_statement} for T and/or A changes"
    )
    text: str = Field(
        default="", description="Optional context for classification/generation"
    )

    _report: ExecutionReport = PrivateAttr()
    _working_wu: WisdomUnit = PrivateAttr()
    _original_wu: WisdomUnit = PrivateAttr()
    _was_committed: bool = PrivateAttr()
    _changes: dict[str, str] = PrivateAttr()
    _text: str = PrivateAttr()

    @property
    def report(self) -> ExecutionReport:
        """Access the execution report."""
        return self._report

    async def call(self) -> str:
        """Execute editing and return ExecutionReport as JSON."""
        await self.execute()
        return str(self._report)

    async def execute(self) -> EditPolarityResult:
        """Execute the editing operation."""
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Resolve WisdomUnit
        wu = self._resolve_wisdom_unit(self.wisdom_unit_hash)
        if wu is None:
            result = EditPolarityResult(
                is_valid=False,
                error_message=f"WisdomUnit '{self.wisdom_unit_hash}' not found",
            )
            self._build_report(result)
            return result

        self._original_wu = wu
        self._text = self.text
        self._was_committed = wu.is_committed

        # Clean up changes dict - only accept T and A
        self._changes = {}
        for k, v in self.changes.items():
            if v and v.strip() and k in [POSITION_T, POSITION_A]:
                self._changes[k] = v.strip()

        if not self._changes:
            result = EditPolarityResult(
                is_valid=False,
                error_message="Must provide T and/or A change. For poles, use EditTetrad.",
            )
            self._build_report(result)
            return result

        # Prepare working WU
        if self._was_committed:
            self._working_wu = wu.clone()
            self._working_wu.save()
        else:
            self._working_wu = wu
            if not self._working_wu._id:
                self._working_wu.save()

        # Route based on what's being changed
        result = await self._route_changes()

        self._build_report(result)
        return result

    async def _route_changes(self) -> EditPolarityResult:
        """Route changes to appropriate handler."""
        t_changed = POSITION_T in self._changes
        a_changed = POSITION_A in self._changes

        if t_changed and a_changed:
            return await self._handle_both_ta_changed()
        if t_changed:
            return await self._handle_thesis_change()
        if a_changed:
            return await self._handle_antithesis_change()

        return EditPolarityResult(
            is_valid=False,
            error_message="No valid changes specified",
        )

    async def _handle_both_ta_changed(self) -> EditPolarityResult:
        """Handle when both T and A are changed together."""
        new_t_statement = self._changes[POSITION_T]
        new_a_statement = self._changes[POSITION_A]

        # Classify the new thesis
        t_classifier = StatementClassification()
        t_classification = await t_classifier.execute(
            statement=new_t_statement,
            text=self._text,
        )
        self._report = self._report.merge(t_classifier.report)

        # Create new thesis component
        new_t = DialecticalComponent(
            statement=new_t_statement,
            meaning=t_classification.meaning,
        )
        new_t.commit()
        self._report.node_created(new_t)

        # Validate new A against new T
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.execute(
            thesis=new_t,
            antithesis_statement=new_a_statement,
            text=self._text,
        )
        self._report = self._report.merge(a_classifier.report)

        warnings: list[str] = []
        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            warnings.append(
                f"Very low HS={a_validation.heuristic_similarity:.2f} between T and A"
            )

        # Create new antithesis component
        new_a = DialecticalComponent(
            statement=new_a_statement,
            meaning=a_validation.meaning,
        )
        new_a.commit()
        self._report.node_created(new_a)

        # Fill working WU with new T/A and regenerate all poles
        await self._fill_wu_and_regenerate_poles(
            thesis=new_t,
            antithesis=new_a,
            a_hs=a_validation.heuristic_similarity,
        )

        self._create_edit_rationale(
            new_t,
            f"Both T and A changed. New opposition: '{new_t_statement}' <-> '{new_a_statement}' "
            f"(HS={a_validation.heuristic_similarity:.2f})",
        )

        return EditPolarityResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            warnings=warnings,
            changed_positions=[POSITION_T, POSITION_A],
            regenerated_positions=POLE_POSITIONS.copy(),
        )

    async def _handle_thesis_change(self) -> EditPolarityResult:
        """Handle T change."""
        new_t_statement = self._changes[POSITION_T]

        # Get current antithesis
        current_a = self._original_wu.get_component(POSITION_A)
        if not current_a:
            return EditPolarityResult(
                is_valid=False,
                error_message="Original WisdomUnit has no antithesis",
            )

        # Classify the new thesis
        t_classifier = StatementClassification()
        t_classification = await t_classifier.execute(
            statement=new_t_statement,
            text=self._text,
        )
        self._report = self._report.merge(t_classifier.report)

        # Create new thesis component
        new_t = DialecticalComponent(
            statement=new_t_statement,
            meaning=t_classification.meaning,
        )
        new_t.commit()
        self._report.node_created(new_t)

        # Validate current A against new T
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.execute(
            thesis=new_t,
            antithesis_statement=current_a.statement,
            text=self._text,
        )
        self._report = self._report.merge(a_classifier.report)

        warnings: list[str] = []
        antithesis_to_use = current_a
        a_hs = a_validation.heuristic_similarity
        regenerated = []

        # Check if A is still valid for new T
        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            # A is no longer valid - regenerate
            extractor = AntithesisExtraction()
            antitheses = await extractor.execute(
                thesis=new_t,
                text=self._text,
            )
            self._report = self._report.merge(extractor.report)

            if not antitheses:
                return EditPolarityResult(
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
            warnings.append(
                f"Antithesis regenerated (original had HS={a_validation.heuristic_similarity:.2f})"
            )

        # Fill working WU
        await self._fill_wu_and_regenerate_poles(
            thesis=new_t,
            antithesis=antithesis_to_use,
            a_hs=a_hs,
        )

        self._create_edit_rationale(
            new_t, f"Thesis changed to '{new_t_statement}' (HS={a_hs:.2f})"
        )

        regenerated.extend(POLE_POSITIONS)

        return EditPolarityResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            warnings=warnings,
            changed_positions=[POSITION_T],
            regenerated_positions=regenerated,
        )

    async def _handle_antithesis_change(self) -> EditPolarityResult:
        """Handle A change."""
        new_a_statement = self._changes[POSITION_A]

        # Get current thesis
        current_t = self._original_wu.get_component(POSITION_T)
        if not current_t:
            return EditPolarityResult(
                is_valid=False,
                error_message="Original WisdomUnit has no thesis",
            )

        # Validate new A against current T
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.execute(
            thesis=current_t,
            antithesis_statement=new_a_statement,
            text=self._text,
        )
        self._report = self._report.merge(a_classifier.report)

        # Check if new A is valid
        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            # Check if it might be a pole
            current_a = self._original_wu.get_component(POSITION_A)
            if current_a:
                for pole_pos in POLE_POSITIONS:
                    pole_classifier = PoleClassification()
                    try:
                        pole_result = await pole_classifier.execute(
                            thesis=current_t,
                            antithesis=current_a,
                            pole_statement=new_a_statement,
                            position=pole_pos,
                            text=self._text,
                        )
                        if (
                            pole_result.heuristic_similarity
                            > HS_WRONG_CATEGORY_THRESHOLD
                        ):
                            return EditPolarityResult(
                                is_valid=False,
                                error_message=(
                                    f"'{new_a_statement}' looks more like {pole_pos} "
                                    f"(HS={pole_result.heuristic_similarity:.2f}) than an antithesis. "
                                    f"Use EditTetrad for pole edits."
                                ),
                            )
                    except Exception:
                        continue

            return EditPolarityResult(
                is_valid=False,
                error_message=(
                    f"'{new_a_statement}' is not a valid antithesis for '{current_t.statement}' "
                    f"(HS={a_validation.heuristic_similarity:.2f})"
                ),
            )

        # Create new antithesis
        new_a = DialecticalComponent(
            statement=new_a_statement,
            meaning=a_validation.meaning,
        )
        new_a.commit()
        self._report.node_created(new_a)

        # Fill working WU
        await self._fill_wu_and_regenerate_poles(
            thesis=current_t,
            antithesis=new_a,
            a_hs=a_validation.heuristic_similarity,
        )

        self._create_edit_rationale(
            new_a,
            f"Antithesis changed to '{new_a_statement}' (HS={a_validation.heuristic_similarity:.2f})",
        )

        return EditPolarityResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            changed_positions=[POSITION_A],
            regenerated_positions=POLE_POSITIONS.copy(),
        )

    async def _fill_wu_and_regenerate_poles(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        a_hs: float,
    ) -> None:
        """Fill working WU with T, A (via Polarity) and regenerate all poles."""
        wu = self._working_wu

        # Create Polarity for T-A pair
        polarity = Polarity()
        polarity.set_t(thesis, heuristic_similarity=1.0)
        polarity.set_a(antithesis, heuristic_similarity=a_hs)
        polarity.commit()
        self._report.node_created(polarity)

        # Connect WU to Polarity
        wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

        # Generate all poles
        generator = PoleGeneration()
        generated_poles = await generator.execute(
            wisdom_unit=wu,
            positions=POLE_POSITIONS,
            text=self._text,
        )
        self._report = self._report.merge(generator.report)

        # Connect generated poles
        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for pole in generated_poles:
            rel_class = rel_classes[pole.position]
            manager = wu.get_relationship_manager_by_position(pole.position)
            manager.connect(
                pole.component,
                relationship=rel_class(
                    alias=pole.position,
                    heuristic_similarity=pole.heuristic_similarity,
                    complementarity_t=pole.complementarity_t,
                    complementarity_a=pole.complementarity_a,
                ),
            )

        wu.commit()
        self._report.node_created(wu)

    def _resolve_wisdom_unit(self, wu_hash: str) -> Optional[WisdomUnit]:
        """Resolve hash to WisdomUnit."""
        repo = NodeRepository()
        try:
            node = repo.find_by_hash(wu_hash)
            if isinstance(node, WisdomUnit):
                return node
        except ValueError:
            try:
                node = repo.find_by_prefix(wu_hash)
                if isinstance(node, WisdomUnit):
                    return node
            except ValueError:
                pass
        return None

    def _create_edit_rationale(
        self, component: DialecticalComponent, text: str
    ) -> None:
        """Create and attach rationale for the edit."""
        rationale = Rationale(text=f"Edit: {text}")
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)

    def _build_report(self, result: EditPolarityResult) -> None:
        """Build execution report from result."""
        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["changes"] = self.changes
        self._report.artifacts["was_committed"] = (
            self._was_committed if hasattr(self, "_was_committed") else None
        )

        if result.wisdom_unit:
            if result.wisdom_unit.hash:
                self._report.artifacts["wisdom_unit_hash"] = result.wisdom_unit.hash
            if result.wisdom_unit.origin_hash:
                self._report.artifacts["origin_hash"] = result.wisdom_unit.origin_hash

        if result.warnings:
            self._report.artifacts["warnings"] = result.warnings

        if result.changed_positions:
            self._report.artifacts["changed_positions"] = result.changed_positions

        if result.regenerated_positions:
            self._report.artifacts["regenerated_positions"] = (
                result.regenerated_positions
            )

        self._report.ok = result.is_valid
        if result.is_valid:
            positions = (
                ", ".join(result.changed_positions)
                if result.changed_positions
                else "none"
            )
            warning_count = len(result.warnings)
            action = (
                "Forked and edited"
                if (hasattr(self, "_was_committed") and self._was_committed)
                else "Edited"
            )
            self._report.summary = f"{action} {positions}"
            if warning_count > 0:
                self._report.summary += f" ({warning_count} warning(s))"
        else:
            self._report.summary = f"Edit failed: {result.error_message}"
