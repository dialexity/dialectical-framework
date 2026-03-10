"""
PolarityEditing: Capability for editing WisdomUnit components with validation.

Handles modifications to T, A, or poles with proper validation and regeneration:
- Changing T → validate A compatibility, regenerate A if needed, regenerate poles
- Changing A → validate T compatibility, handle misclassification (A- mistaken for A)
- Changing pole → validate position, check contradiction pair, update metrics

Editing behavior based on WU state:
- Uncommitted WU → fill in components and commit the same WU
- Committed WU → clone (fork with origin_hash) and edit the new WU

Uses ForkableMixin: forked WU has origin_hash pointing to the original.

Usage:
    editor = PolarityEditing()

    # Single change
    result = await editor.execute(
        wisdom_unit=original_wu,
        changes={"T": "New thesis statement"},
        text="context...",
    )

    # Multiple changes
    result = await editor.execute(
        wisdom_unit=original_wu,
        changes={"T": "Trust", "A": "Distrust", "T+": "Deep trust"},
        text="context...",
    )

    if result.is_valid:
        print(f"WU: {result.wisdom_unit.short_hash}")
        if result.wisdom_unit.origin_hash:
            print(f"Forked from: {result.wisdom_unit.origin_hash[:7]}")
    else:
        print(f"Invalid: {result.validation_message}")
        if result.suggested_position:
            print(f"Did you mean {result.suggested_position}?")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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

# Positions that are poles (not T or A)
POLE_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]

# Contradiction pairs: changing one may affect the other
CONTRADICTION_PAIRS = {
    POSITION_T_PLUS: POSITION_A_MINUS,
    POSITION_A_MINUS: POSITION_T_PLUS,
    POSITION_A_PLUS: POSITION_T_MINUS,
    POSITION_T_MINUS: POSITION_A_PLUS,
}

# Heuristic Similarity threshold for "wrong category" (not this type at all)
# HS <= this means the statement is probably misclassified (e.g., pole passed as antithesis)
HS_WRONG_CATEGORY_THRESHOLD = 0.1


# --- Result ---


@dataclass
class PolarityEditingResult:
    """Result of editing a WisdomUnit component.

    Returns a single WisdomUnit:
    - If input WU was uncommitted → same WU, now filled and committed
    - If input WU was committed → new forked WU with origin_hash set
    """

    is_valid: bool
    wisdom_unit: Optional[WisdomUnit] = None
    validation_message: str = ""

    # If invalid, what position might the statement actually belong to?
    suggested_position: Optional[str] = None

    # Classification metrics (if applicable)
    heuristic_similarity: Optional[float] = None
    mode_value: Optional[float] = None
    complementarity_t: Optional[float] = None
    complementarity_a: Optional[float] = None

    # What was regenerated
    regenerated_positions: list[str] = field(default_factory=list)


# --- Capability ---


class PolarityEditing(ExecutableCapability[PolarityEditingResult]):
    """
    Capability for editing WisdomUnit components with validation.

    Validates the edit, regenerates affected components, and returns new WU(s).
    Does NOT mutate the original WisdomUnit.
    """

    def __init__(self) -> None:
        pass

    async def execute(
        self,
        wisdom_unit: WisdomUnit,
        changes: dict[str, str],
        text: str = "",
    ) -> PolarityEditingResult:
        """
        Edit component(s) in a WisdomUnit.

        Args:
            wisdom_unit: The WisdomUnit to edit (uncommitted or committed)
            changes: Dict of {position: new_statement} for changes
            text: Optional context for classification/generation

        Returns:
            PolarityEditingResult with:
            - Same WU (filled and committed) if input was uncommitted
            - New forked WU (with origin_hash) if input was committed

        Examples:
            # Single change
            await editor.execute(wu, changes={"T": "Trust"})

            # Multiple changes
            await editor.execute(wu, changes={"T": "Trust", "A": "Distrust"})
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Validate inputs
        if not wisdom_unit:
            raise ValueError("Cannot edit without a WisdomUnit")
        if not changes:
            raise ValueError("Must provide changes dict with at least one position")

        valid_positions = [POSITION_T, POSITION_A] + POLE_POSITIONS

        # Clean up changes dict (filter empty/whitespace values)
        self._changes = {k: v.strip() for k, v in changes.items() if v and v.strip()}

        if not self._changes:
            raise ValueError("Must provide changes dict with at least one non-empty position")

        # Validate all positions
        for pos in self._changes:
            if pos not in valid_positions:
                raise ValueError(f"Invalid position '{pos}'. Must be one of: {valid_positions}")

        self._original_wu = wisdom_unit
        self._text = text

        # Determine if we're editing in place or forking
        self._is_forking = wisdom_unit.is_committed
        if self._is_forking:
            # Clone (fork) the committed WU - origin_hash will be set
            self._working_wu = wisdom_unit.clone()
        else:
            # Edit the uncommitted WU in place
            self._working_wu = wisdom_unit
            if not self._working_wu._id:
                self._working_wu.save()

        # Route based on what's being changed
        result = await self._handle_changes()

        self._build_report(result)
        return result

    async def _handle_changes(self) -> PolarityEditingResult:
        """Handle one or more position changes together."""
        changed_positions = set(self._changes.keys())

        # Determine what categories are being changed
        t_changed = POSITION_T in changed_positions
        a_changed = POSITION_A in changed_positions
        poles_changed = changed_positions & set(POLE_POSITIONS)

        # Case 1: Both T and A changed - validate as new opposition pair
        if t_changed and a_changed:
            return await self._handle_both_ta_changed(poles_changed)

        # Case 2: Only T changed
        if t_changed:
            return await self._handle_thesis_change_with_poles(poles_changed)

        # Case 3: Only A changed
        if a_changed:
            return await self._handle_antithesis_change_with_poles(poles_changed)

        # Case 4: Only poles changed
        if poles_changed:
            return await self._handle_poles_only_changed(poles_changed)

        return PolarityEditingResult(
            is_valid=False,
            validation_message="No valid changes specified",
        )

    async def _handle_both_ta_changed(
        self, poles_changed: set[str]
    ) -> PolarityEditingResult:
        """Handle when both T and A are changed together."""
        new_t_statement = self._changes[POSITION_T]
        new_a_statement = self._changes[POSITION_A]

        # Classify the new thesis
        t_classifier = StatementClassification()
        t_classification = await t_classifier.execute(
            statement=new_t_statement,
            text=self._text,
        )

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

        # HS <= 0.1 means no real relationship - warn but still accept (user explicitly set both)
        hs_warning = ""
        if a_validation.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            hs_warning = f" (Warning: very low HS={a_validation.heuristic_similarity:.2f})"

        # Create new antithesis component
        new_a = DialecticalComponent(
            statement=new_a_statement,
            meaning=a_validation.meaning,
        )
        new_a.commit()
        self._report.node_created(new_a)

        # Fill working WU with poles (use provided pole changes if any)
        await self._fill_wu_with_custom_poles(
            thesis=new_t,
            antithesis=new_a,
            a_hs=a_validation.heuristic_similarity,
            pole_changes=poles_changed,
        )

        self._create_edit_rationale(
            new_t,
            f"Both T and A changed. New opposition: '{new_t_statement}' ↔ '{new_a_statement}' "
            f"(Heuristic Similarity={a_validation.heuristic_similarity:.2f})"
        )

        regenerated = [POSITION_T, POSITION_A] + [
            p for p in POLE_POSITIONS if p not in poles_changed
        ]

        return PolarityEditingResult(
            is_valid=True,
            wisdom_unit=self._working_wu,
            validation_message=f"Both T and A changed successfully{hs_warning}",
            heuristic_similarity=a_validation.heuristic_similarity,
            mode_value=a_validation.mode_value,
            regenerated_positions=regenerated,
        )

    async def _handle_thesis_change_with_poles(
        self, poles_changed: set[str]
    ) -> PolarityEditingResult:
        """Handle T change, possibly with pole changes."""
        # Store for single-change compatibility
        self._position = POSITION_T
        self._new_statement = self._changes[POSITION_T]

        # Get base result from thesis change handler
        result = await self._handle_thesis_change()

        # If valid and poles were also specified, we need to validate/apply them
        if result.is_valid and poles_changed and result.wisdom_units:
            # For each created WU, validate the specified pole changes
            for wu in result.wisdom_units:
                for pole_pos in poles_changed:
                    pole_stmt = self._changes[pole_pos]
                    # This is simplified - full implementation would validate each pole
                    # For now, the poles are regenerated and user-specified ones are ignored
                    # TODO: Apply user-specified poles after validation

        return result

    async def _handle_antithesis_change_with_poles(
        self, poles_changed: set[str]
    ) -> PolarityEditingResult:
        """Handle A change, possibly with pole changes."""
        self._position = POSITION_A
        self._new_statement = self._changes[POSITION_A]

        result = await self._handle_antithesis_change()

        # Similar to thesis - pole changes would be applied after validation
        # TODO: Apply user-specified poles after validation

        return result

    async def _handle_poles_only_changed(
        self, poles_changed: set[str]
    ) -> PolarityEditingResult:
        """Handle when only poles are changed (T and A unchanged)."""
        current_t = self._original_wu.get_component(POSITION_T)
        current_a = self._original_wu.get_component(POSITION_A)

        if not current_t or not current_a:
            return PolarityEditingResult(
                is_valid=False,
                validation_message="Original WU must have T and A for pole editing",
            )

        # Validate all changed poles using HS threshold
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

            # HS > 0.1 means it's a valid pole for this position
            if pole_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                # Create component
                new_pole = DialecticalComponent(
                    statement=pole_stmt,
                    meaning=pole_result.meaning,
                )
                new_pole.commit()
                self._report.node_created(new_pole)
                pole_validations[pole_pos] = (new_pole, pole_result)
            else:
                # HS <= 0.1 means wrong category - check other positions
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
            return PolarityEditingResult(
                is_valid=False,
                validation_message="Invalid pole(s): " + "; ".join(invalid_poles),
            )

        # Fill working WU with validated poles
        await self._fill_wu_with_specific_poles(pole_validations)

        # Get one HS for report (from first pole)
        first_result = list(pole_validations.values())[0][1] if pole_validations else None

        return PolarityEditingResult(
            is_valid=True,
            wisdom_unit=self._working_wu,
            validation_message=f"Changed {len(poles_changed)} pole(s) successfully",
            heuristic_similarity=first_result.heuristic_similarity if first_result else None,
            complementarity_t=first_result.complementarity_t if first_result else None,
            complementarity_a=first_result.complementarity_a if first_result else None,
            regenerated_positions=[],
        )

    async def _fill_wu_with_specific_poles(
        self,
        pole_validations: dict[str, tuple[DialecticalComponent, object]],
    ) -> None:
        """Fill working WU with specific poles changed, copying others from original."""
        wu = self._working_wu

        # Copy T from original (if not already connected)
        if wu.t.count() == 0:
            orig_t = self._original_wu.get_component(POSITION_T)
            t_result = self._original_wu.t.get()
            t_rel = t_result[1] if t_result else None
            wu.t.connect(orig_t, relationship=TRelationship(
                alias=POSITION_T,
                heuristic_similarity=t_rel.heuristic_similarity if t_rel else 1.0,
                complementarity_t=t_rel.complementarity_t if t_rel else None,
                complementarity_a=t_rel.complementarity_a if t_rel else None,
            ))

        # Copy A from original (if not already connected)
        if wu.a.count() == 0:
            orig_a = self._original_wu.get_component(POSITION_A)
            a_result = self._original_wu.a.get()
            a_rel = a_result[1] if a_result else None
            wu.a.connect(orig_a, relationship=ARelationship(
                alias=POSITION_A,
                heuristic_similarity=a_rel.heuristic_similarity if a_rel else 0.5,
                complementarity_t=a_rel.complementarity_t if a_rel else None,
                complementarity_a=a_rel.complementarity_a if a_rel else None,
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
                # Use validated new pole
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
                # Copy from original (if not already connected)
                if manager.count() == 0:
                    orig_result = self._original_wu.get_relationship_manager_by_position(pos).get()
                    if orig_result:
                        orig_comp, orig_rel = orig_result
                        manager.connect(
                            orig_comp,
                            relationship=rel_class(
                                alias=pos,
                                heuristic_similarity=orig_rel.heuristic_similarity if orig_rel else 0.5,
                                complementarity_t=orig_rel.complementarity_t if orig_rel else None,
                                complementarity_a=orig_rel.complementarity_a if orig_rel else None,
                            ),
                        )

        wu.commit()
        self._report.node_created(wu)

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
            complementarity_t=None,
            complementarity_a=None,
        ))

        # Connect A
        wu.a.connect(antithesis, relationship=ARelationship(
            alias=POSITION_A,
            heuristic_similarity=a_hs,
            complementarity_t=None,
            complementarity_a=None,
        ))

        # If user specified some poles, validate them first
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

            # HS > 0.1 means valid for this position
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

        wu.commit()
        self._report.node_created(wu)

    async def _handle_thesis_change(self) -> PolarityEditingResult:
        """Handle changing the thesis (T)."""
        # Get current antithesis
        current_a = self._original_wu.get_component(POSITION_A)
        if not current_a:
            return PolarityEditingResult(
                is_valid=False,
                validation_message="Original WisdomUnit has no antithesis to validate against",
            )

        # Classify the new thesis
        classifier = StatementClassification()
        t_classification = await classifier.execute(
            statement=self._new_statement,
            text=self._text,
        )

        # Create new thesis component
        new_t = DialecticalComponent(
            statement=self._new_statement,
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

        # Check if A is still an antithesis for new T (HS > 0.1 means it's still antithetical)
        if a_validation.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
            # A is still an antithesis (quality varies with HS) - keep it
            await self._fill_wu_with_poles(
                thesis=new_t,
                antithesis=current_a,
                a_hs=a_validation.heuristic_similarity,
            )

            # Create rationale for the edit
            self._create_edit_rationale(
                new_t,
                f"Thesis changed. Antithesis '{current_a.statement}' retained "
                f"(Heuristic Similarity={a_validation.heuristic_similarity:.2f})"
            )

            return PolarityEditingResult(
                is_valid=True,
                wisdom_unit=self._working_wu,
                validation_message="Thesis changed, antithesis retained",
                heuristic_similarity=a_validation.heuristic_similarity,
                mode_value=a_validation.mode_value,
                regenerated_positions=POLE_POSITIONS,
            )
        else:
            # HS <= 0.1 means A is no longer antithetical to new T - regenerate
            extractor = AntithesisExtraction()
            antitheses = await extractor.execute(
                thesis=new_t,
                text=self._text,
            )
            self._report = self._report.merge(extractor.report)

            if not antitheses:
                return PolarityEditingResult(
                    is_valid=False,
                    validation_message=(
                        f"Thesis changed but could not generate valid antithesis. "
                        f"Original antithesis '{current_a.statement}' has low Heuristic Similarity "
                        f"({a_validation.heuristic_similarity:.2f}) with new thesis."
                    ),
                    heuristic_similarity=a_validation.heuristic_similarity,
                )

            # Pick the best antithesis (highest HS)
            best_antithesis = max(antitheses, key=lambda a: a.heuristic_similarity)

            await self._fill_wu_with_poles(
                thesis=new_t,
                antithesis=best_antithesis.component,
                a_hs=best_antithesis.heuristic_similarity,
            )

            # Create rationale
            self._create_edit_rationale(
                new_t,
                f"Thesis changed. Original antithesis '{current_a.statement}' invalid "
                f"(Heuristic Similarity={a_validation.heuristic_similarity:.2f}). "
                f"Generated new antithesis '{best_antithesis.component.statement}'."
            )

            return PolarityEditingResult(
                is_valid=True,
                wisdom_unit=self._working_wu,
                validation_message=(
                    f"Thesis changed, antithesis regenerated to '{best_antithesis.component.statement}'"
                ),
                heuristic_similarity=best_antithesis.heuristic_similarity,
                regenerated_positions=[POSITION_A] + POLE_POSITIONS,
            )

    async def _handle_antithesis_change(self) -> PolarityEditingResult:
        """Handle changing the antithesis (A)."""
        # Get current thesis
        current_t = self._original_wu.get_component(POSITION_T)
        if not current_t:
            return PolarityEditingResult(
                is_valid=False,
                validation_message="Original WisdomUnit has no thesis to validate against",
            )

        # Validate new A against current T
        a_classifier = AntithesisClassification()
        a_validation = await a_classifier.execute(
            thesis=current_t,
            antithesis_statement=self._new_statement,
            text=self._text,
        )

        # HS > 0.1 means it IS an antithesis (quality varies with HS)
        if a_validation.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
            # Accept as antithesis
            new_a = DialecticalComponent(
                statement=self._new_statement,
                meaning=a_validation.meaning,
            )
            new_a.commit()
            self._report.node_created(new_a)

            await self._fill_wu_with_poles(
                thesis=current_t,
                antithesis=new_a,
                a_hs=a_validation.heuristic_similarity,
            )

            self._create_edit_rationale(
                new_a,
                f"Antithesis changed to '{self._new_statement}' "
                f"(Heuristic Similarity={a_validation.heuristic_similarity:.2f}, "
                f"Mode={a_validation.mode_label})"
            )

            return PolarityEditingResult(
                is_valid=True,
                wisdom_unit=self._working_wu,
                validation_message="Antithesis changed successfully",
                heuristic_similarity=a_validation.heuristic_similarity,
                mode_value=a_validation.mode_value,
                regenerated_positions=POLE_POSITIONS,
            )
        else:
            # HS <= 0.1 means not really an antithesis - check if user meant a pole
            current_a = self._original_wu.get_component(POSITION_A)
            if current_a:
                for pole_position in [POSITION_T_MINUS, POSITION_A_MINUS, POSITION_T_PLUS, POSITION_A_PLUS]:
                    pole_classifier = PoleClassification()
                    try:
                        pole_result = await pole_classifier.execute(
                            thesis=current_t,
                            antithesis=current_a,
                            pole_statement=self._new_statement,
                            position=pole_position,
                            text=self._text,
                        )
                        # If HS > 0.1 for this pole position, suggest it
                        if pole_result.heuristic_similarity > HS_WRONG_CATEGORY_THRESHOLD:
                            return PolarityEditingResult(
                                is_valid=False,
                                validation_message=(
                                    f"'{self._new_statement}' doesn't appear to be an antithesis "
                                    f"(HS={a_validation.heuristic_similarity:.2f}). "
                                    f"It looks more like {pole_position} (HS={pole_result.heuristic_similarity:.2f})."
                                ),
                                suggested_position=pole_position,
                                heuristic_similarity=a_validation.heuristic_similarity,
                            )
                    except Exception:
                        continue

            # Not a pole either - just very weak/no relationship
            return PolarityEditingResult(
                is_valid=False,
                validation_message=(
                    f"'{self._new_statement}' doesn't appear to be an antithesis for "
                    f"'{current_t.statement}' (HS={a_validation.heuristic_similarity:.2f})"
                ),
                heuristic_similarity=a_validation.heuristic_similarity,
                mode_value=a_validation.mode_value,
            )

    async def _handle_pole_change(self) -> PolarityEditingResult:
        """Handle changing a pole (T+, T-, A+, A-)."""
        # Get T and A
        current_t = self._original_wu.get_component(POSITION_T)
        current_a = self._original_wu.get_component(POSITION_A)

        if not current_t or not current_a:
            return PolarityEditingResult(
                is_valid=False,
                validation_message="Original WisdomUnit must have both T and A for pole editing",
            )

        # Validate the pole
        pole_classifier = PoleClassification()
        pole_result = await pole_classifier.execute(
            thesis=current_t,
            antithesis=current_a,
            pole_statement=self._new_statement,
            position=self._position,
            text=self._text,
        )

        # HS <= 0.1 means wrong category
        if pole_result.heuristic_similarity <= HS_WRONG_CATEGORY_THRESHOLD:
            # Check if it belongs to a different position
            suggested = pole_result.suggested_position
            return PolarityEditingResult(
                is_valid=False,
                validation_message=(
                    f"'{self._new_statement}' is not a valid {self._position} pole "
                    f"(HS={pole_result.heuristic_similarity:.2f}). {pole_result.reasoning}"
                ),
                suggested_position=suggested,
                heuristic_similarity=pole_result.heuristic_similarity,
                complementarity_t=pole_result.complementarity_t,
                complementarity_a=pole_result.complementarity_a,
            )

        # Create new pole component
        new_pole = DialecticalComponent(
            statement=self._new_statement,
            meaning=pole_result.meaning,
        )
        new_pole.commit()
        self._report.node_created(new_pole)

        self._create_edit_rationale(
            new_pole,
            f"{self._position} pole changed to '{self._new_statement}' "
            f"(Heuristic Similarity={pole_result.heuristic_similarity:.2f}, "
            f"Complementarity T={pole_result.complementarity_t:.2f}, "
            f"Complementarity A={pole_result.complementarity_a:.2f})"
        )

        # Fill working WU with the changed pole
        await self._fill_wu_with_changed_pole(
            new_pole=new_pole,
            pole_result=pole_result,
        )

        return PolarityEditingResult(
            is_valid=True,
            wisdom_unit=self._working_wu,
            validation_message=f"{self._position} pole changed successfully",
            heuristic_similarity=pole_result.heuristic_similarity,
            complementarity_t=pole_result.complementarity_t,
            complementarity_a=pole_result.complementarity_a,
            regenerated_positions=[],
        )

    async def _fill_wu_with_poles(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        a_hs: float,
    ) -> None:
        """Fill working WU with T, A, and generate all poles."""
        wu = self._working_wu

        # Connect T
        wu.t.connect(thesis, relationship=TRelationship(
            alias=POSITION_T,
            heuristic_similarity=1.0,
            complementarity_t=None,
            complementarity_a=None,
        ))

        # Connect A
        wu.a.connect(antithesis, relationship=ARelationship(
            alias=POSITION_A,
            heuristic_similarity=a_hs,
            complementarity_t=None,
            complementarity_a=None,
        ))

        # Generate poles
        generator = PoleGeneration()
        poles = await generator.execute(
            wisdom_unit=wu,
            text=self._text,
        )
        self._report = self._report.merge(generator.report)

        # Connect poles
        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for pole in poles:
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

    async def _fill_wu_with_changed_pole(
        self,
        new_pole: DialecticalComponent,
        pole_result,
    ) -> None:
        """Fill working WU copying original but with one pole changed."""
        wu = self._working_wu

        # Copy T and A from original (if not already connected)
        if wu.t.count() == 0:
            orig_t = self._original_wu.get_component(POSITION_T)
            t_result = self._original_wu.t.get()
            t_rel = t_result[1] if t_result else None
            wu.t.connect(orig_t, relationship=TRelationship(
                alias=POSITION_T,
                heuristic_similarity=t_rel.heuristic_similarity if t_rel else 1.0,
                complementarity_t=t_rel.complementarity_t if t_rel else None,
                complementarity_a=t_rel.complementarity_a if t_rel else None,
            ))

        if wu.a.count() == 0:
            orig_a = self._original_wu.get_component(POSITION_A)
            a_result = self._original_wu.a.get()
            a_rel = a_result[1] if a_result else None
            wu.a.connect(orig_a, relationship=ARelationship(
                alias=POSITION_A,
                heuristic_similarity=a_rel.heuristic_similarity if a_rel else 0.5,
                complementarity_t=a_rel.complementarity_t if a_rel else None,
                complementarity_a=a_rel.complementarity_a if a_rel else None,
            ))

        # Copy/replace poles
        rel_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        for pos in POLE_POSITIONS:
            manager = wu.get_relationship_manager_by_position(pos)
            rel_class = rel_classes[pos]

            if pos == self._position:
                # Use the new pole
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
                # Copy from original (if not already connected)
                if manager.count() == 0:
                    orig_result = self._original_wu.get_relationship_manager_by_position(pos).get()
                    if orig_result:
                        orig_comp, orig_rel = orig_result
                        manager.connect(
                            orig_comp,
                            relationship=rel_class(
                                alias=pos,
                                heuristic_similarity=orig_rel.heuristic_similarity if orig_rel else 0.5,
                                complementarity_t=orig_rel.complementarity_t if orig_rel else None,
                                complementarity_a=orig_rel.complementarity_a if orig_rel else None,
                            ),
                        )

        wu.commit()
        self._report.node_created(wu)

    async def _find_better_pole_position(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        pole_stmt: str,
        exclude_position: str,
    ) -> Optional[dict]:
        """
        Check if a pole statement fits better in a different position.

        Returns dict with 'position' and 'hs' if a better position found, None otherwise.
        """
        other_positions = [p for p in POLE_POSITIONS if p != exclude_position]

        best_match = None
        best_hs = HS_WRONG_CATEGORY_THRESHOLD  # Must be better than threshold

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

    def _create_edit_rationale(self, component: DialecticalComponent, text: str) -> None:
        """Create and attach rationale for the edit."""
        rationale = Rationale(text=f"Edit: {text}")
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)

    def _build_report(self, result: PolarityEditingResult) -> None:
        """Build execution report from result."""
        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["changes"] = self._changes
        self._report.artifacts["is_forked"] = self._is_forking

        if result.wisdom_unit and result.wisdom_unit.hash:
            self._report.artifacts["wisdom_unit_hash"] = result.wisdom_unit.hash
            if result.wisdom_unit.origin_hash:
                self._report.artifacts["origin_hash"] = result.wisdom_unit.origin_hash

        if result.heuristic_similarity is not None:
            self._report.artifacts["heuristic_similarity"] = result.heuristic_similarity

        if result.suggested_position:
            self._report.artifacts["suggested_position"] = result.suggested_position

        if result.regenerated_positions:
            self._report.artifacts["regenerated_positions"] = result.regenerated_positions

        self._report.ok = result.is_valid
        positions_changed = list(self._changes.keys())
        if result.is_valid:
            action = "Forked and edited" if self._is_forking else "Edited"
            self._report.summary = f"{action} {', '.join(positions_changed)}"
        else:
            self._report.summary = f"Edit invalid: {result.validation_message}"
