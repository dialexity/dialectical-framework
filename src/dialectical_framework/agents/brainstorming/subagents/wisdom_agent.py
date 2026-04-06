"""
WisdomAgent: Orchestrator for creating WisdomUnits from Polarities.

Takes a T-A Polarity and creates WisdomUnits by adding poles (T+, T-, A+, A-).
If no Polarity exists for the T-A pair, creates one using AntithesisClassification.

Flow:
    PolarityAgent → Polarity nodes (T-A pairs with HS)
           ↓
    WisdomAgent → WisdomUnits (Polarity + T+, T-, A+, A-)

Usage:
    # From PolarityAgent output
    polarity_agent = PolarityAgent(thesis_hashes=[...])
    ideas = await polarity_agent.execute()

    # Get polarity data from artifacts
    for polarity_data in polarity_agent.report.artifacts["polarity_data"]:
        wisdom_agent = WisdomAgent(
            thesis_hash=tension["thesis_hash"],
            antithesis_hash=tension["antithesis_hash"],
        )
        wus = await wisdom_agent.execute()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.brainstorming.capabilities.antithesis_classification import (
    AntithesisClassification,
)
from dialectical_framework.agents.brainstorming.capabilities.pole_generation import (
    PoleGeneration,
    PoleResult,
)
from dialectical_framework.agents.brainstorming.capabilities.statement_deduplication import (
    StatementDeduplication,
)
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.polarity import POSITION_A, POSITION_T, Polarity
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
    WisdomUnit,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    ARelationship,
    APlusRelationship,
    AMinusRelationship,
    HasPolarityRelationship,
    TRelationship,
    TPlusRelationship,
    TMinusRelationship,
)
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.graph.repositories.polarity_repository import PolarityRepository
from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class WisdomAgent(BaseTool, ExecutableCapability[list[WisdomUnit]]):
    """
    Orchestrate WisdomUnit creation for a single T-A tension.

    Creates WisdomUnits from a Polarity by generating and connecting poles
    (T+, T-, A+, A-). If no Polarity exists for the T-A pair, creates one first.

    Flow:
    1. Look up or create Polarity for this T-A pair
    2. Look up existing WisdomUnits for this Polarity
    3. If none exist, create a new WisdomUnit
    4. Complete all partial WUs by generating poles
    5. Return list of completed WisdomUnits

    Dual interface:
    - execute() returns list[WisdomUnit] for programmatic use
    - call() returns JSON string for LLM tool use
    """

    thesis_hash: str = Field(
        description="Hash of the thesis component"
    )
    antithesis_hash: str = Field(
        description="Hash of the antithesis component"
    )
    positions: Optional[list[str]] = Field(
        default=None,
        description="Which poles to generate (T+, T-, A+, A-). If None, generates all 4."
    )

    _report: ExecutionReport = PrivateAttr()

    @property
    def report(self) -> ExecutionReport:
        """Access the execution report."""
        return self._report

    async def call(self) -> str:
        """Execute WisdomUnit creation and return ExecutionReport as JSON."""
        await self.execute()
        return str(self._report)

    async def execute(self) -> list[WisdomUnit]:
        """
        Execute WisdomUnit creation for a single T-A tension.

        If no Polarity exists for the T-A pair, creates one using AntithesisClassification.
        Then creates/completes WisdomUnits for that Polarity.

        Returns:
            List of complete, committed WisdomUnits
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Resolve components
        thesis = self._resolve_component(self.thesis_hash)
        if thesis is None:
            self._report.ok = False
            self._report.summary = f"Thesis '{self.thesis_hash}' not found"
            return []

        antithesis = self._resolve_component(self.antithesis_hash)
        if antithesis is None:
            self._report.ok = False
            self._report.summary = f"Antithesis '{self.antithesis_hash}' not found"
            return []

        # Get input text for context (needed for classification and pole generation)
        input_text = await self._get_input_text()

        # Step 1: Look up or create Polarity for this T-A pair
        polarity = await self._get_or_create_polarity(thesis, antithesis, input_text)

        # Step 2: Look up existing WisdomUnits for this Polarity
        wu_repo = WisdomUnitRepository()
        existing_wus = wu_repo.find_by_polarity(polarity)

        if not existing_wus:
            # No WU exists - create one referencing the Polarity
            wu = self._create_wisdom_unit_for_polarity(polarity)
            existing_wus = [wu]

        complete_wus = [wu for wu in existing_wus if wu.is_complete()]
        partial_wus = [wu for wu in existing_wus if not wu.is_complete()]

        if not partial_wus:
            # All WUs are already complete - nothing to do
            self._report.ok = True
            self._report.summary = f"{len(complete_wus)} complete WisdomUnit(s), no partial WUs to expand"
            self._report.artifacts["wisdom_unit_hashes"] = [
                wu.hash for wu in complete_wus if wu.hash
            ]
            self._report.artifacts["total_count"] = len(complete_wus)
            self._report.artifacts["existing_count"] = len(complete_wus)
            self._report.artifacts["new_count"] = 0
            return complete_wus

        # Step 3: Complete all partial WUs
        completed_wus: list[WisdomUnit] = []

        for wu in partial_wus:
            # Use complete WUs + already completed in this run as not_like_these
            not_like_these = complete_wus + completed_wus

            generator = PoleGeneration()
            poles = await generator.execute(
                wisdom_unit=wu,
                positions=self.positions,
                text=input_text,
                not_like_these=not_like_these,
            )
            self._report = self._report.merge(generator.report)

            # Deduplicate poles against vocabulary (within same branch)
            poles = await self._deduplicate_poles(poles, input_text)

            # Connect poles to WisdomUnit
            for pole in poles:
                self._connect_pole(wu, pole)

            # Check if WU (after deduplication) is identical to an existing complete WU
            duplicate_of = self._find_duplicate(wu, complete_wus + completed_wus)
            if duplicate_of:
                # Discard the duplicate - delete uncommitted WU
                wu_repo.safe_delete(wu)
                self._report.artifacts.setdefault("duplicates_discarded", []).append({
                    "discarded": wu.short_hash if wu.hash else "uncommitted",
                    "duplicate_of": duplicate_of.short_hash,
                })
                continue

            # Only commit complete WUs (Polarity + 4 poles)
            # If specific positions were requested, WU may remain incomplete
            if not wu.is_complete():
                self._report.artifacts.setdefault("incomplete_wus", []).append({
                    "status": "kept_uncommitted",
                    "reason": "missing positions",
                })
                continue

            # Commit WisdomUnit
            wu.commit()
            self._report.node_created(wu)
            completed_wus.append(wu)

        # Return all WUs: existing complete + newly completed
        all_wus = complete_wus + completed_wus

        # Build summary
        self._report.ok = True
        self._report.artifacts["wisdom_unit_hashes"] = [
            wu.hash for wu in all_wus if wu.hash
        ]
        self._report.artifacts["total_count"] = len(all_wus)
        self._report.artifacts["existing_count"] = len(complete_wus)
        self._report.artifacts["new_count"] = len(completed_wus)

        self._report.summary = (
            f"{len(all_wus)} WisdomUnit(s) ({len(complete_wus)} existing, {len(completed_wus)} new)"
        )

        return all_wus

    async def _get_or_create_polarity(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        text: str,
    ) -> Polarity:
        """
        Get existing Polarity for T-A pair, or create one.

        If no Polarity exists, uses AntithesisClassification to get the
        heuristic_similarity value.
        """
        pol_repo = PolarityRepository()
        existing_pols = pol_repo.find_by_tension(thesis, antithesis)

        if existing_pols:
            self._report.artifacts["polarity_source"] = "existing"
            return existing_pols[0]

        # No Polarity exists - classify the antithesis and create one
        classifier = AntithesisClassification()
        classification = await classifier.execute(
            thesis=thesis,
            antithesis_statement=antithesis.statement,
            text=text,
        )
        self._report = self._report.merge(classifier.report)

        # Create Polarity (atomic creation)
        polarity = Polarity()
        polarity.set_t(thesis, heuristic_similarity=1.0)
        polarity.set_a(antithesis, heuristic_similarity=classification.heuristic_similarity)
        polarity.commit()

        self._report.node_created(polarity)
        self._report.artifacts["polarity_source"] = "created"
        self._report.artifacts["polarity_hash"] = polarity.hash

        return polarity

    def _create_wisdom_unit_for_polarity(self, polarity: Polarity) -> WisdomUnit:
        """
        Create a partial WisdomUnit referencing a Polarity.

        Args:
            polarity: The Polarity (T-A pair) for this WisdomUnit

        Returns:
            A partial WisdomUnit (Polarity connected, no poles yet)
        """
        wu = WisdomUnit()
        wu.save()

        # Connect to Polarity
        wu.polarity.connect(polarity, relationship=HasPolarityRelationship())

        self._report.node_created(wu)
        return wu

    def _connect_pole(self, wu: WisdomUnit, pole: PoleResult) -> None:
        """Connect a generated pole to the WisdomUnit."""
        relationship_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        rel_class = relationship_classes[pole.position]
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

        self._report.relationship_created(
            manager,
            wu,
            pole.component,
            meta={
                "position": pole.position,
                "hs": pole.heuristic_similarity,
                "k_t": pole.complementarity_t,
                "k_a": pole.complementarity_a,
            },
        )

    async def _deduplicate_poles(
        self, poles: list[PoleResult], text: str
    ) -> list[PoleResult]:
        """
        Deduplicate generated poles against vocabulary (within same branch).

        If a generated pole matches an existing component in the same taxonomy branch,
        replace the generated component with the existing one.
        """
        if not poles:
            return poles

        # Get vocabulary
        repo = DialecticalComponentRepository()
        vocab = repo.get_vocabulary_with_rationales()
        if not vocab:
            return poles

        # Collect generated hashes
        generated_hashes = [p.component.hash for p in poles if p.component.hash]
        if not generated_hashes:
            return poles

        # Run deduplication (branch filtering happens inside StatementDeduplication)
        deduplicator = StatementDeduplication()
        dedup_result = await deduplicator.execute(
            extracted_hashes=generated_hashes,
            vocabulary=vocab,
            text=text,
        )
        self._report = self._report.merge(deduplicator.report)

        # If no replacements, return original poles
        if not dedup_result.replacements:
            return poles

        # Update poles with replaced components
        updated_poles: list[PoleResult] = []
        for pole in poles:
            if pole.component.hash in dedup_result.replacements:
                # Replace with existing component (keeps original meaning)
                replacement = dedup_result.replacements[pole.component.hash]
                updated_poles.append(PoleResult(
                    component=replacement,
                    position=pole.position,
                    apex_concept=pole.apex_concept,
                    heuristic_similarity=pole.heuristic_similarity,
                    complementarity_t=pole.complementarity_t,
                    complementarity_a=pole.complementarity_a,
                ))
                self._report.artifacts.setdefault("deduped_poles", []).append({
                    "position": pole.position,
                    "original": pole.component.short_hash,
                    "replaced_with": replacement.short_hash,
                })
            else:
                updated_poles.append(pole)

        return updated_poles

    def _find_duplicate(
        self, wu: WisdomUnit, existing_wus: list[WisdomUnit]
    ) -> Optional[WisdomUnit]:
        """
        Find an existing committed WU that has the same components as the given WU.

        Uses WisdomUnit.is_same which handles T-A symmetry.
        Only considers committed WUs as valid duplicates.

        Args:
            wu: The WisdomUnit to check
            existing_wus: List of existing WisdomUnits to compare against

        Returns:
            The matching committed WU if found, None otherwise
        """
        for existing in existing_wus:
            if existing.is_committed and wu.is_same(existing):
                return existing
        return None

    def _resolve_component(self, component_hash: str) -> Optional[DialecticalComponent]:
        """Resolve hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(component_hash)
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get concatenated text from all inputs in scope."""
        repo = InputRepository()
        inputs = repo.get_all()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)


# Backward compatibility alias
PolarityAgent = WisdomAgent
