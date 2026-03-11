"""
PolarityEditor: Agent for editing WisdomUnit components.

Handles modifications to T, A, or poles with proper validation and regeneration:
- Changing T -> validate A compatibility, regenerate A if needed, regenerate poles
- Changing A -> validate T compatibility, handle misclassification
- Changing pole -> validate position fit

Editing behavior based on WU state:
- Uncommitted WU -> edit in place, commit it
- Committed WU -> clone (fork with origin_hash), edit the copy, commit it

In both cases, the returned WU is committed with all 6 poles set.

Use WisdomUnitValidation capability separately for full tetrad validation.

Uses ForkableMixin: forked WU has origin_hash pointing to the original.

Usage:
    editor = PolarityEditor(
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
from typing import Optional

from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.brainstorming.capabilities.antithesis_classification import (
    AntithesisClassification,
)
from dialectical_framework.agents.brainstorming.capabilities.antithesis_extraction import (
    AntithesisExtraction,
)
from dialectical_framework.agents.brainstorming.capabilities.pole_classification import (
    PoleClassification,
)
from dialectical_framework.agents.brainstorming.capabilities.pole_generation import (
    PoleGeneration,
)
from dialectical_framework.agents.brainstorming.capabilities.statement_classification import (
    StatementClassification,
)
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_A,
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    WisdomUnit,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship,
    APlusRelationship,
    ARelationship,
    TMinusRelationship,
    TPlusRelationship,
    TRelationship,
)
from dialectical_framework.graph.repositories.node_repository import NodeRepository


# Positions that are poles (not T or A)
POLE_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]

# Heuristic Similarity threshold for "wrong category"
HS_WRONG_CATEGORY_THRESHOLD = 0.1


# --- Result ---


@dataclass
class PolarityEditorResult:
    """Result of editing a WisdomUnit.

    Returns a WisdomUnit:
    - If input WU was uncommitted -> edits in place, commits it
    - If input WU was committed -> clones (forks with origin_hash), edits the copy, commits it

    Use WisdomUnitValidation capability separately if full validation is needed.
    """

    wisdom_unit: Optional[WisdomUnit] = None
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)  # Edit-time warnings (e.g., low HS)
    changed_positions: list[str] = field(default_factory=list)
    regenerated_positions: list[str] = field(default_factory=list)

    # Error message if is_valid is False
    error_message: str = ""


# --- Agent ---


class PolarityEditor(BaseTool, ExecutableCapability[PolarityEditorResult]):
    """
    Agent for editing WisdomUnit components with validation.

    Validates edits, regenerates affected components, and returns WU with warnings.
    Does NOT mutate the original committed WisdomUnit (clones it instead).

    Dual interface:
    - execute() returns PolarityEditorResult for programmatic use
    - call() returns JSON string for LLM tool use
    """

    wisdom_unit_hash: str = Field(
        description="Hash of the WisdomUnit to edit"
    )
    changes: dict[str, str] = Field(
        description="Dict of {position: new_statement} for changes (T, A, T+, T-, A+, A-)"
    )
    text: str = Field(
        default="",
        description="Optional context for classification/generation"
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

    async def execute(self) -> PolarityEditorResult:
        """
        Execute the editing operation.

        Returns:
            PolarityEditorResult with WU and validation warnings
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Resolve WisdomUnit
        wu = self._resolve_wisdom_unit(self.wisdom_unit_hash)
        if wu is None:
            result = PolarityEditorResult(
                is_valid=False,
                error_message=f"WisdomUnit '{self.wisdom_unit_hash}' not found",
            )
            self._build_report(result)
            return result

        self._original_wu = wu
        self._text = self.text
        self._was_committed = wu.is_committed

        # Clean up changes dict
        self._changes = {k: v.strip() for k, v in self.changes.items() if v and v.strip()}

        if not self._changes:
            result = PolarityEditorResult(
                is_valid=False,
                error_message="Must provide at least one non-empty change",
            )
            self._build_report(result)
            return result

        # Validate positions
        valid_positions = [POSITION_T, POSITION_A] + POLE_POSITIONS
        for pos in self._changes:
            if pos not in valid_positions:
                result = PolarityEditorResult(
                    is_valid=False,
                    error_message=f"Invalid position '{pos}'. Must be one of: {valid_positions}",
                )
                self._build_report(result)
                return result

        # Prepare working WU
        if self._was_committed:
            self._working_wu = wu.clone()
        else:
            self._working_wu = wu
            if not self._working_wu._id:
                self._working_wu.save()

        # Route based on what's being changed
        result = await self._route_changes()

        self._build_report(result)
        return result

    async def _route_changes(self) -> PolarityEditorResult:
        """Route changes to appropriate handler."""
        t_changed = POSITION_T in self._changes
        a_changed = POSITION_A in self._changes
        poles_changed = set(self._changes.keys()) & set(POLE_POSITIONS)

        if t_changed and a_changed:
            return await self._handle_both_ta_changed(poles_changed)
        if t_changed:
            return await self._handle_thesis_change(poles_changed)
        if a_changed:
            return await self._handle_antithesis_change(poles_changed)
        if poles_changed:
            return await self._handle_poles_changed(poles_changed)

        return PolarityEditorResult(
            is_valid=False,
            error_message="No valid changes specified",
        )

    async def _handle_both_ta_changed(
        self, poles_changed: set[str]
    ) -> PolarityEditorResult:
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

        # Fill working WU
        await self._fill_wu_with_custom_poles(
            thesis=new_t,
            antithesis=new_a,
            a_hs=a_validation.heuristic_similarity,
            pole_changes=poles_changed,
        )

        self._create_edit_rationale(
            new_t,
            f"Both T and A changed. New opposition: '{new_t_statement}' <-> '{new_a_statement}' "
            f"(HS={a_validation.heuristic_similarity:.2f})"
        )

        regenerated = [p for p in POLE_POSITIONS if p not in poles_changed]

        return PolarityEditorResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            changed_positions=[POSITION_T, POSITION_A] + list(poles_changed),
            regenerated_positions=regenerated,
        )

    async def _handle_thesis_change(
        self, poles_changed: set[str]
    ) -> PolarityEditorResult:
        """Handle T change, possibly with pole changes."""
        new_t_statement = self._changes[POSITION_T]

        # Get current antithesis
        current_a = self._original_wu.get_component(POSITION_A)
        if not current_a:
            return PolarityEditorResult(
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
        regenerated = list(poles_changed)

        # Check if A is still valid for new T
        if a_validation.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
            # A is still valid - keep it
            pass
        else:
            # A is no longer valid - regenerate
            extractor = AntithesisExtraction()
            antitheses = await extractor.execute(
                thesis=new_t,
                text=self._text,
            )
            self._report = self._report.merge(extractor.report)

            if not antitheses:
                return PolarityEditorResult(
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
        await self._fill_wu_with_custom_poles(
            thesis=new_t,
            antithesis=antithesis_to_use,
            a_hs=a_hs,
            pole_changes=poles_changed,
        )

        self._create_edit_rationale(
            new_t,
            f"Thesis changed to '{new_t_statement}' (HS={a_hs:.2f})"
        )

        regenerated.extend([p for p in POLE_POSITIONS if p not in poles_changed])

        return PolarityEditorResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            warnings=warnings,
            changed_positions=[POSITION_T] + list(poles_changed),
            regenerated_positions=list(set(regenerated)),
        )

    async def _handle_antithesis_change(
        self, poles_changed: set[str]
    ) -> PolarityEditorResult:
        """Handle A change, possibly with pole changes."""
        new_a_statement = self._changes[POSITION_A]

        # Get current thesis
        current_t = self._original_wu.get_component(POSITION_T)
        if not current_t:
            return PolarityEditorResult(
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

        warnings: list[str] = []

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
                        if pole_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                            return PolarityEditorResult(
                                is_valid=False,
                                error_message=(
                                    f"'{new_a_statement}' looks more like {pole_pos} "
                                    f"(HS={pole_result.heuristic_similarity:.2f}) than an antithesis"
                                ),
                            )
                    except Exception:
                        continue

            return PolarityEditorResult(
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
        await self._fill_wu_with_custom_poles(
            thesis=current_t,
            antithesis=new_a,
            a_hs=a_validation.heuristic_similarity,
            pole_changes=poles_changed,
        )

        self._create_edit_rationale(
            new_a,
            f"Antithesis changed to '{new_a_statement}' (HS={a_validation.heuristic_similarity:.2f})"
        )

        regenerated = [p for p in POLE_POSITIONS if p not in poles_changed]

        return PolarityEditorResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            warnings=warnings,
            changed_positions=[POSITION_A] + list(poles_changed),
            regenerated_positions=regenerated,
        )

    async def _handle_poles_changed(
        self, poles_changed: set[str]
    ) -> PolarityEditorResult:
        """Handle when only poles are changed (T and A unchanged)."""
        current_t = self._original_wu.get_component(POSITION_T)
        current_a = self._original_wu.get_component(POSITION_A)

        if not current_t or not current_a:
            return PolarityEditorResult(
                is_valid=False,
                error_message="Original WU must have T and A for pole editing",
            )

        # Validate all changed poles
        pole_validations: dict[str, tuple[DialecticalComponent, object]] = {}
        invalid_poles: list[str] = []

        for pole_pos in poles_changed:
            pole_stmt = self._changes[pole_pos]

            pole_classifier = PoleClassification()
            pole_result = await pole_classifier.execute(
                thesis=current_t,
                antithesis=current_a,
                pole_statement=pole_stmt,
                position=pole_pos,
                text=self._text,
            )
            self._report = self._report.merge(pole_classifier.report)

            if pole_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                new_pole = DialecticalComponent(
                    statement=pole_stmt,
                    meaning=pole_result.meaning,
                )
                new_pole.commit()
                self._report.node_created(new_pole)
                pole_validations[pole_pos] = (new_pole, pole_result)
            else:
                # Check other positions
                suggested = await self._find_better_pole_position(
                    current_t, current_a, pole_stmt, pole_pos
                )
                if suggested:
                    invalid_poles.append(
                        f"{pole_pos}: '{pole_stmt}' looks more like {suggested['position']} "
                        f"(HS={suggested['hs']:.2f})"
                    )
                else:
                    invalid_poles.append(
                        f"{pole_pos}: '{pole_stmt}' doesn't fit any pole position "
                        f"(HS={pole_result.heuristic_similarity:.2f})"
                    )

        if invalid_poles:
            return PolarityEditorResult(
                is_valid=False,
                error_message="Invalid pole(s): " + "; ".join(invalid_poles),
            )

        # Fill working WU with validated poles
        await self._fill_wu_with_specific_poles(pole_validations)

        return PolarityEditorResult(
            wisdom_unit=self._working_wu,
            is_valid=True,
            changed_positions=list(poles_changed),
            regenerated_positions=[],
        )

    async def _fill_wu_with_custom_poles(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        a_hs: float,
        pole_changes: set[str],
    ) -> None:
        """Fill working WU with T, A and handle custom pole changes."""
        wu = self._working_wu

        # Connect T
        wu.t.connect(thesis, relationship=TRelationship(
            alias=POSITION_T,
            heuristic_similarity=1.0,
        ))

        # Connect A
        wu.a.connect(antithesis, relationship=ARelationship(
            alias=POSITION_A,
            heuristic_similarity=a_hs,
        ))

        # Validate user-specified poles first
        user_poles: dict[str, tuple[DialecticalComponent, object]] = {}
        for pole_pos in pole_changes:
            pole_stmt = self._changes[pole_pos]

            pole_classifier = PoleClassification()
            pole_result = await pole_classifier.execute(
                thesis=thesis,
                antithesis=antithesis,
                pole_statement=pole_stmt,
                position=pole_pos,
                text=self._text,
            )
            self._report = self._report.merge(pole_classifier.report)

            if pole_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                new_pole = DialecticalComponent(
                    statement=pole_stmt,
                    meaning=pole_result.meaning,
                )
                new_pole.commit()
                self._report.node_created(new_pole)
                user_poles[pole_pos] = (new_pole, pole_result)

        # Generate remaining poles
        positions_to_generate = [p for p in POLE_POSITIONS if p not in user_poles]
        if positions_to_generate:
            generator = PoleGeneration()
            generated_poles = await generator.execute(
                wisdom_unit=wu,
                positions=positions_to_generate,
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

        # Connect user-specified poles
        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for pole_pos, (pole_comp, pole_result) in user_poles.items():
            rel_class = rel_classes[pole_pos]
            manager = wu.get_relationship_manager_by_position(pole_pos)
            manager.connect(
                pole_comp,
                relationship=rel_class(
                    alias=pole_pos,
                    heuristic_similarity=pole_result.heuristic_similarity,
                    complementarity_t=pole_result.complementarity_t,
                    complementarity_a=pole_result.complementarity_a,
                ),
            )

        # Always commit - PolarityEditor sets all 6 poles, so WU is complete
        wu.commit()
        self._report.node_created(wu)

    async def _fill_wu_with_specific_poles(
        self,
        pole_validations: dict[str, tuple[DialecticalComponent, object]],
    ) -> None:
        """Fill working WU with specific poles changed, copying others from original."""
        wu = self._working_wu

        # Copy T from original
        if wu.t.count() == 0:
            orig_t = self._original_wu.get_component(POSITION_T)
            t_result = self._original_wu.t.get()
            t_rel = t_result[1] if t_result else None
            wu.t.connect(orig_t, relationship=TRelationship(
                alias=POSITION_T,
                heuristic_similarity=t_rel.heuristic_similarity if t_rel else 1.0,
            ))

        # Copy A from original
        if wu.a.count() == 0:
            orig_a = self._original_wu.get_component(POSITION_A)
            a_result = self._original_wu.a.get()
            a_rel = a_result[1] if a_result else None
            wu.a.connect(orig_a, relationship=ARelationship(
                alias=POSITION_A,
                heuristic_similarity=a_rel.heuristic_similarity if a_rel else None,
            ))

        # Handle poles
        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for pos in POLE_POSITIONS:
            manager = wu.get_relationship_manager_by_position(pos)
            rel_class = rel_classes[pos]

            if pos in pole_validations:
                new_pole, pole_result = pole_validations[pos]
                manager.connect(
                    new_pole,
                    relationship=rel_class(
                        alias=pos,
                        heuristic_similarity=pole_result.heuristic_similarity,
                        complementarity_t=pole_result.complementarity_t,
                        complementarity_a=pole_result.complementarity_a,
                    ),
                )
            else:
                if manager.count() == 0:
                    orig_result = self._original_wu.get_relationship_manager_by_position(pos).get()
                    if orig_result:
                        orig_comp, orig_rel = orig_result
                        manager.connect(
                            orig_comp,
                            relationship=rel_class(
                                alias=pos,
                                heuristic_similarity=orig_rel.heuristic_similarity if orig_rel else None,
                                complementarity_t=orig_rel.complementarity_t if orig_rel else None,
                                complementarity_a=orig_rel.complementarity_a if orig_rel else None,
                            ),
                        )

        # Always commit - PolarityEditor sets all 6 poles, so WU is complete
        wu.commit()
        self._report.node_created(wu)

    async def _find_better_pole_position(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        pole_stmt: str,
        exclude_position: str,
    ) -> Optional[dict]:
        """Check if pole fits better in a different position."""
        other_positions = [p for p in POLE_POSITIONS if p != exclude_position]

        best_match = None
        best_hs = HS_WRONG_CATEGORY_THRESHOLD

        for pos in other_positions:
            try:
                classifier = PoleClassification()
                result = await classifier.execute(
                    thesis=thesis,
                    antithesis=antithesis,
                    pole_statement=pole_stmt,
                    position=pos,
                    text=self._text,
                )
                if result.heuristic_similarity > best_hs:
                    best_hs = result.heuristic_similarity
                    best_match = {"position": pos, "hs": result.heuristic_similarity}
            except Exception:
                continue

        return best_match

    def _resolve_wisdom_unit(self, wu_hash: str) -> Optional[WisdomUnit]:
        """Resolve hash to WisdomUnit."""
        repo = NodeRepository()
        try:
            node = repo.find_by_hash(wu_hash)
            if isinstance(node, WisdomUnit):
                return node
        except ValueError:
            # Try prefix match
            try:
                node = repo.find_by_prefix(wu_hash)
                if isinstance(node, WisdomUnit):
                    return node
            except ValueError:
                pass
        return None

    def _create_edit_rationale(self, component: DialecticalComponent, text: str) -> None:
        """Create and attach rationale for the edit."""
        rationale = Rationale(text=f"Edit: {text}")
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)

    def _build_report(self, result: PolarityEditorResult) -> None:
        """Build execution report from result."""
        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["changes"] = self.changes
        self._report.artifacts["was_committed"] = self._was_committed if hasattr(self, "_was_committed") else None

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
            self._report.artifacts["regenerated_positions"] = result.regenerated_positions

        self._report.ok = result.is_valid
        if result.is_valid:
            positions = ", ".join(result.changed_positions) if result.changed_positions else "none"
            warning_count = len(result.warnings)
            action = "Forked and edited" if (hasattr(self, "_was_committed") and self._was_committed) else "Edited"
            self._report.summary = f"{action} {positions}"
            if warning_count > 0:
                self._report.summary += f" ({warning_count} warning(s))"
        else:
            self._report.summary = f"Edit failed: {result.error_message}"
