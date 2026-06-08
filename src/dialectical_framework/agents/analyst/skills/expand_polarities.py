"""
ExpandPolarity: Orchestrator for creating Perspectives from a Polarity.

Takes a Polarity (T-A pair) and creates Perspectives by adding aspects (T+, T-, A+, A-).

Usage:
    agent = ExpandPolarity(polarity_hash="abc123...")
    pps = await agent.resolve()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI
from dialectical_framework.concerns.aspect_generation import (AspectGeneration,
                                                              AspectResult)
from dialectical_framework.concerns.statement_deduplication import \
    StatementDeduplication
from dialectical_framework.graph.nodes.polarity import Polarity
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS,
                                                           Perspective)
from dialectical_framework.graph.relationships.polarity_relationship import (
    AMinusRelationship, APlusRelationship, HasPolarityRelationship,
    TMinusRelationship, TPlusRelationship)
from dialectical_framework.graph.repositories.statement_repository import \
    StatementRepository
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.perspective_repository import \
    PerspectiveRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


class ExpandPolarity(ReasonableConcern[list[Perspective]]):
    """
    Orchestrate Perspective creation for a single Polarity (T-A tension).

    Creates Perspectives from a Polarity by generating and connecting aspects
    (T+, T-, A+, A-).

    Flow:
    1. Resolve Polarity by hash
    2. Look up existing Perspectives for this Polarity
    3. If none exist, create a new Perspective
    4. Complete all partial PPs by generating aspects
    5. Return list of completed Perspectives
    """

    def __init__(self, polarity_hash: str) -> None:
        self.polarity_hash = polarity_hash

    async def resolve(self) -> list[Perspective]:
        """
        Resolve Perspective creation for a single Polarity.

        Returns:
            List of complete, committed Perspectives
        """

        # Resolve Polarity
        polarity = self._resolve_polarity()
        if polarity is None:
            return []

        # Get input text for context
        input_text = await self._get_input_text()

        # Look up existing Perspectives for this Polarity
        pp_repo = PerspectiveRepository()
        existing_pps = pp_repo.find_by_polarity(polarity)

        if not existing_pps:
            # No PP exists - create one referencing the Polarity
            pp = self._create_perspective_for_polarity(polarity)
            existing_pps = [pp]

        complete_pps = [pp for pp in existing_pps if pp.is_complete()]
        partial_pps = [pp for pp in existing_pps if not pp.is_complete()]

        if not partial_pps:
            # All existing perspectives are complete — create a new one
            pp = self._create_perspective_for_polarity(polarity)
            partial_pps = [pp]

        # Complete all partial PPs
        completed_pps: list[Perspective] = []

        for pp in partial_pps:
            not_like_these = complete_pps + completed_pps

            generator = AspectGeneration()
            aspects = await generator.resolve(
                perspective=pp,
                text=input_text,
                not_like_these=not_like_these,
            )
            self._report = self._report.merge(generator.report)

            # Deduplicate aspects against vocabulary
            aspects = await self._deduplicate_aspects(aspects, input_text)

            # Connect aspects to Perspective
            for aspect in aspects:
                self._connect_aspect(pp, aspect)

            # Check if PP is identical to an existing complete PP
            duplicate_of = self._find_duplicate(pp, complete_pps + completed_pps)
            if duplicate_of:
                pp_repo.discard_uncommitted(pp)
                self._report.artifacts.setdefault("duplicates_discarded", []).append(
                    {
                        "discarded": pp.short_hash if pp.hash else "uncommitted",
                        "duplicate_of": duplicate_of.short_hash,
                    }
                )
                continue

            pp.commit()
            self._report.node_created(pp)
            completed_pps.append(pp)

        # Return all PPs: existing complete + newly completed
        all_pps = complete_pps + completed_pps

        self._report.ok = True
        self._report.artifacts["perspective_hashes"] = [
            pp.hash for pp in all_pps if pp.hash
        ]
        self._report.artifacts["total_count"] = len(all_pps)
        self._report.artifacts["existing_count"] = len(complete_pps)
        self._report.artifacts["new_count"] = len(completed_pps)
        self._report.artifacts["perspectives"] = [
            self._perspective_final_state(pp) for pp in all_pps
        ]

        self._report.summary = f"{len(all_pps)} Perspective(s) ({len(complete_pps)} existing, {len(completed_pps)} new)"

        return all_pps

    def _resolve_polarity(self) -> Optional[Polarity]:
        """Resolve Polarity by hash."""
        repo = NodeRepository()
        node = repo.find_by_hash(self.polarity_hash, node_type=Polarity)
        if node is None:
            self._report.ok = False
            self._report.summary = f"Polarity '{self.polarity_hash}' not found"
            return None
        return node

    def _create_perspective_for_polarity(self, polarity: Polarity) -> Perspective:
        """Create a partial Perspective referencing a Polarity."""
        pp = Perspective()
        pp.save()
        pp.polarity.connect(polarity, relationship=HasPolarityRelationship())
        self._report.node_created(pp)
        self._report.relationship_created(pp.polarity, pp, polarity)
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

    def _perspective_final_state(self, pp: Perspective) -> dict[str, str | None]:
        """Build a dict with the final post-dedup text at each position."""
        positions = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]
        state: dict[str, str | None] = {"hash": pp.short_hash}
        for pos in positions:
            manager = pp.get_relationship_manager_by_position(pos)
            pairs = manager.all()
            if pairs:
                node, _rel = pairs[0]
                state[pos] = node.text
            else:
                state[pos] = None
        return state

    async def _deduplicate_aspects(
        self, aspects: list[AspectResult], text: str
    ) -> list[AspectResult]:
        """Deduplicate generated aspects against vocabulary."""
        if not aspects:
            return aspects

        repo = StatementRepository()
        vocab = repo.get_vocabulary_with_rationales()
        if not vocab:
            return aspects

        generated_hashes = [a.component.hash for a in aspects if a.component.hash]
        if not generated_hashes:
            return aspects

        deduplicator = StatementDeduplication()
        dedup_result = await deduplicator.resolve(
            extracted_hashes=generated_hashes,
            vocabulary=vocab,
            text=text,
        )
        self._report = self._report.merge(deduplicator.report)

        if not dedup_result.replacements:
            return aspects

        updated_aspects: list[AspectResult] = []
        for aspect in aspects:
            if aspect.component.hash in dedup_result.replacements:
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
        """Find an existing committed PP with same components."""
        for existing in existing_pps:
            if existing.is_committed and pp.is_same(existing):
                return existing
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


@llm.tool
async def expand_polarities(
    polarity_hashes: Annotated[list[str], Field(description="Hashes of Polarities to expand into full Perspectives")],
) -> str:
    """Build complete Perspectives from Polarities by generating evaluative aspects (T+, T-, A+, A-) for each. Runs in parallel. The Polarities must already exist in the graph."""
    import asyncio

    async def _expand_one(h: str) -> str:
        concern = ExpandPolarity(polarity_hash=h)
        await concern.resolve()
        return str(concern.report)

    results = await asyncio.gather(*[_expand_one(h) for h in polarity_hashes])
    return "\n---\n".join(results)
