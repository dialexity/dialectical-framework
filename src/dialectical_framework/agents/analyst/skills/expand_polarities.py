"""
ExpandPolarities: Orchestrator for creating Perspectives from Polarities.

Takes a T-A Polarity and creates Perspectives by adding aspects (T+, T-, A+, A-).
If no Polarity exists for the T-A pair, creates one using AntithesisClassification.

Flow:
    FindPolarities → Polarity nodes (T-A pairs with HS)
           ↓
    ExpandPolarities → Perspectives (Polarity + aspects T+, T-, A+, A-)

Usage:
    # From FindPolarities output
    polarity_agent = FindPolarities(thesis_hashes=[...])
    ideas = await polarity_agent.resolve()

    # Get polarity data from artifacts
    for polarity_data in polarity_agent.report.artifacts["polarity_data"]:
        perspective_agent = ExpandPolarities(
            thesis_hash=tension["thesis_hash"],
            antithesis_hash=tension["antithesis_hash"],
        )
        pps = await perspective_agent.resolve()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import Field, PrivateAttr

from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.antithesis_classification import \
    AntithesisClassification
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              AspectResult)
from dialectical_framework.concerns.statement_deduplication import \
    StatementDeduplication
from dialectical_framework.graph.nodes.dialectical_component import \
    DialecticalComponent
from dialectical_framework.graph.nodes.polarity import (POSITION_A, POSITION_T,
                                                        Polarity)
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, ARelationship,
    HasPolarityRelationship, TMinusRelationship, TPlusRelationship,
    TRelationship)
from dialectical_framework.graph.repositories.dialectical_component_repository import \
    DialecticalComponentRepository
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.polarity_repository import \
    PolarityRepository
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class ExpandPolarities(BaseTool, ReasonableConcern[list[Perspective]]):
    """
    Orchestrate Perspective creation for a single T-A tension.

    Creates Perspectives from a Polarity by generating and connecting aspects
    (T+, T-, A+, A-). If no Polarity exists for the T-A pair, creates one first.

    Flow:
    1. Look up or create Polarity for this T-A pair
    2. Look up existing Perspectives for this Polarity
    3. If none exist, create a new Perspective
    4. Complete all partial PPs by generating aspects
    5. Return list of completed Perspectives

    Dual interface:
    - resolve() returns list[Perspective] for programmatic use
    - call() returns JSON string for LLM tool use
    """

    thesis_hash: str = Field(description="Hash of the thesis component")
    antithesis_hash: str = Field(description="Hash of the antithesis component")
    positions: Optional[list[str]] = Field(
        default=None,
        description="Which aspects to generate (T+, T-, A+, A-). If None, generates all 4.",
    )

    _report: ExecutionReport = PrivateAttr()

    @property
    def report(self) -> ExecutionReport:
        """Access the execution report."""
        return self._report

    async def call(self) -> str:
        """Resolve Perspective creation and return ExecutionReport as JSON."""
        await self.resolve()
        return str(self._report)

    async def resolve(self) -> list[Perspective]:
        """
        Resolve Perspective creation for a single T-A tension.

        If no Polarity exists for the T-A pair, creates one using AntithesisClassification.
        Then creates/completes Perspectives for that Polarity.

        Returns:
            List of complete, committed Perspectives
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

        # Get input text for context (needed for classification and aspect generation)
        input_text = await self._get_input_text()

        # Step 1: Look up or create Polarity for this T-A pair
        polarity = await self._get_or_create_polarity(thesis, antithesis, input_text)

        # Step 2: Look up existing Perspectives for this Polarity
        pp_repo = PerspectiveRepository()
        existing_pps = pp_repo.find_by_polarity(polarity)

        if not existing_pps:
            # No PP exists - create one referencing the Polarity
            pp = self._create_perspective_for_polarity(polarity)
            existing_pps = [pp]

        complete_pps = [pp for pp in existing_pps if pp.is_complete()]
        partial_pps = [pp for pp in existing_pps if not pp.is_complete()]

        if not partial_pps:
            # All PPs are already complete - nothing to do
            self._report.ok = True
            self._report.summary = (
                f"{len(complete_pps)} complete Perspective(s), no partial PPs to expand"
            )
            self._report.artifacts["perspective_hashes"] = [
                pp.hash for pp in complete_pps if pp.hash
            ]
            self._report.artifacts["total_count"] = len(complete_pps)
            self._report.artifacts["existing_count"] = len(complete_pps)
            self._report.artifacts["new_count"] = 0
            return complete_pps

        # Step 3: Complete all partial PPs
        completed_pps: list[Perspective] = []

        for pp in partial_pps:
            # Use complete PPs + already completed in this run as not_like_these
            not_like_these = complete_pps + completed_pps

            generator = AspectGeneration()
            aspects = await generator.resolve(
                perspective=pp,
                positions=self.positions,
                text=input_text,
                not_like_these=not_like_these,
            )
            self._report = self._report.merge(generator.report)

            # Deduplicate aspects against vocabulary (within same branch)
            aspects = await self._deduplicate_aspects(aspects, input_text)

            # Connect aspects to Perspective
            for aspect in aspects:
                self._connect_aspect(pp, aspect)

            # Check if PP (after deduplication) is identical to an existing complete PP
            duplicate_of = self._find_duplicate(pp, complete_pps + completed_pps)
            if duplicate_of:
                # Discard the duplicate - delete uncommitted PP
                pp_repo.safe_delete(pp)
                self._report.artifacts.setdefault("duplicates_discarded", []).append(
                    {
                        "discarded": pp.short_hash if pp.hash else "uncommitted",
                        "duplicate_of": duplicate_of.short_hash,
                    }
                )
                continue

            # Only commit complete PPs (Polarity + 4 aspects)
            # If specific positions were requested, PP may remain incomplete
            if not pp.is_complete():
                self._report.artifacts.setdefault("incomplete_pps", []).append(
                    {
                        "status": "kept_uncommitted",
                        "reason": "missing positions",
                    }
                )
                continue

            # Commit Perspective
            pp.commit()
            self._report.node_created(pp)
            completed_pps.append(pp)

        # Return all PPs: existing complete + newly completed
        all_pps = complete_pps + completed_pps

        # Build summary
        self._report.ok = True
        self._report.artifacts["perspective_hashes"] = [
            pp.hash for pp in all_pps if pp.hash
        ]
        self._report.artifacts["total_count"] = len(all_pps)
        self._report.artifacts["existing_count"] = len(complete_pps)
        self._report.artifacts["new_count"] = len(completed_pps)

        self._report.summary = f"{len(all_pps)} Perspective(s) ({len(complete_pps)} existing, {len(completed_pps)} new)"

        return all_pps

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
        classification = await classifier.resolve(
            thesis=thesis,
            antithesis_statement=antithesis.statement,
            text=text,
        )
        self._report = self._report.merge(classifier.report)

        # Create Polarity (atomic creation)
        polarity = Polarity()
        polarity.set_t(thesis, heuristic_similarity=1.0)
        polarity.set_a(
            antithesis, heuristic_similarity=classification.heuristic_similarity
        )
        polarity.commit()

        self._report.node_created(polarity)
        self._report.artifacts["polarity_source"] = "created"
        self._report.artifacts["polarity_hash"] = polarity.hash

        return polarity

    def _create_perspective_for_polarity(self, polarity: Polarity) -> Perspective:
        """
        Create a partial Perspective referencing a Polarity.

        Args:
            polarity: The Polarity (T-A pair) for this Perspective

        Returns:
            A partial Perspective (Polarity connected, no aspects yet)
        """
        pp = Perspective()
        pp.save()

        # Connect to Polarity
        pp.polarity.connect(polarity, relationship=HasPolarityRelationship())

        self._report.node_created(pp)
        return pp

    def _connect_aspect(self, pp: Perspective, aspect: AspectResult) -> None:
        """Connect a generated aspect to the Perspective."""
        relationship_classes = {
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        rel_class = relationship_classes[aspect.position]
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
            manager,
            pp,
            aspect.component,
            meta={
                "position": aspect.position,
                "hs": aspect.heuristic_similarity,
                "k_t": aspect.complementarity_t,
                "k_a": aspect.complementarity_a,
            },
        )

    async def _deduplicate_aspects(
        self, aspects: list[AspectResult], text: str
    ) -> list[AspectResult]:
        """
        Deduplicate generated aspects against vocabulary (within same branch).

        If a generated aspect matches an existing component in the same taxonomy branch,
        replace the generated component with the existing one.
        """
        if not aspects:
            return aspects

        # Get vocabulary
        repo = DialecticalComponentRepository()
        vocab = repo.get_vocabulary_with_rationales()
        if not vocab:
            return aspects

        # Collect generated hashes
        generated_hashes = [a.component.hash for a in aspects if a.component.hash]
        if not generated_hashes:
            return aspects

        # Run deduplication (branch filtering happens inside StatementDeduplication)
        deduplicator = StatementDeduplication()
        dedup_result = await deduplicator.resolve(
            extracted_hashes=generated_hashes,
            vocabulary=vocab,
            text=text,
        )
        self._report = self._report.merge(deduplicator.report)

        # If no replacements, return original aspects
        if not dedup_result.replacements:
            return aspects

        # Update aspects with replaced components
        updated_aspects: list[AspectResult] = []
        for aspect in aspects:
            if aspect.component.hash in dedup_result.replacements:
                # Replace with existing component (keeps original meaning)
                replacement = dedup_result.replacements[aspect.component.hash]
                updated_aspects.append(
                    AspectResult(
                        component=replacement,
                        position=aspect.position,
                        apex_concept=aspect.apex_concept,
                        heuristic_similarity=aspect.heuristic_similarity,
                        complementarity_t=aspect.complementarity_t,
                        complementarity_a=aspect.complementarity_a,
                    )
                )
                self._report.artifacts.setdefault("deduped_aspects", []).append(
                    {
                        "position": aspect.position,
                        "original": aspect.component.short_hash,
                        "replaced_with": replacement.short_hash,
                    }
                )
            else:
                updated_aspects.append(aspect)

        return updated_aspects

    def _find_duplicate(
        self, pp: Perspective, existing_pps: list[Perspective]
    ) -> Optional[Perspective]:
        """
        Find an existing committed PP that has the same components as the given PP.

        Uses Perspective.is_same which handles T-A symmetry.
        Only considers committed PPs as valid duplicates.

        Args:
            pp: The Perspective to check
            existing_pps: List of existing Perspectives to compare against

        Returns:
            The matching committed PP if found, None otherwise
        """
        for existing in existing_pps:
            if existing.is_committed and pp.is_same(existing):
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
FindPolarities = ExpandPolarities
