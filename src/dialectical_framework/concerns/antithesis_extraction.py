"""
AntithesisExtraction: Concern for generating antitheses for a thesis.

Generates "ideal" antitheses at mode=1.0, HS=1.0.
For classifying arbitrary user-provided antitheses, use AntithesisClassification.

Truncation algorithm (round-robin by branch coverage):
    1. Group candidates by taxonomy branch
    2. Sort each group by HS descending
    3. Round 1: take best item from each branch (ensures breadth)
    4. Round 2+: fill remaining slots with highest HS across all remaining items

Usage:
    service = AntithesisExtraction()
    antitheses = await service.resolve(thesis=thesis, text=text, count=3)
    for a in antitheses:
        print(a.text)
    # Access report if needed:
    print(service.report.heuristic_similarity_by_hash)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.concerns.antithesis_classification import (
    SYSTEM_PROMPT, ContextualizedTaxonomyDto, arousal_label_to_value,
    contextualize_taxonomy)
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.estimation import (ArousalEstimation,
                                                          ModeEstimation)
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    pass


# --- Extraction-specific DTOs ---


class ModePointResultDto(BaseModel):
    """
    Composite result for antithesis generation at a Mode point.

    Combines candidate generation, HS estimation, and arousal estimation
    into a single LLM call to reduce API calls from 3 to 1 per mode point.
    """

    statement: str = Field(
        description="Antithesis candidate statement (similar length to thesis)"
    )
    heuristic_similarity: float = Field(
        ge=0.0, le=1.0, description="Heuristic Similarity to apex concept (0.0-1.0)"
    )
    arousal_label: str = Field(
        description="Arousal level: dormant/latent/low/mild/moderate/elevated/high/intense/active"
    )
    explanation: str = Field(
        description="Combined reasoning for statement, HS, and arousal"
    )


class ModePointBatchResultDto(BaseModel):
    """Multiple antithesis candidates for a single mode point."""

    candidates: list[ModePointResultDto] = Field(
        description="List of antithesis candidates for this branch"
    )


class SimpleNegationDto(BaseModel):
    """Result of generating negation for a simple thesis."""

    negation: str = Field(
        description="Direct negation statement (similar length to thesis)"
    )
    arousal_label: str = Field(
        description="dormant/latent/low/mild/moderate/elevated/high/intense/active"
    )
    arousal_explanation: str = Field(description="Reasoning for arousal level")


# --- Result Containers ---


@dataclass
class AntithesisCandidate:
    """Pre-persistence candidate (DTO only, no DB writes yet)."""

    statement_text: str
    branch: str
    mode_value: float
    arousal_value: float
    heuristic_similarity: float
    explanation: str


@dataclass
class AntithesisProcessed:
    """Container for an antithesis with its metadata (persisted to DB)."""

    component: Statement
    mode_value: float
    arousal_value: float
    heuristic_similarity: float


# --- Service ---


class AntithesisExtraction(
    ReasonableConcern[list[AntithesisProcessed]], SettingsAware
):
    """
    Concern for extracting antitheses for a thesis.

    Handles both simple and complex theses:
    - Simple: Direct negation with HS=1.0, Mode=1.0
    - Complex: Contextualized taxonomy with candidates at key Mode points

    Returns list of Statement. Access .report for effects.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        thesis: Statement,
        text: str = "",
        not_like_these: Optional[list[str]] = None,
        count: int = 5,
    ) -> list[AntithesisProcessed]:
        """
        Extract antitheses for a thesis.

        Args:
            thesis: The thesis component to generate antitheses for
            text: Optional source content context
            not_like_these: Statements to avoid (for dedup)
            count: Number of antitheses to keep (truncated by round-robin coverage)

        Returns:
            List of AntithesisProcessed containing component and metadata (mode, arousal, HS)
        """
        if not thesis or not thesis.text:
            raise ValueError("Cannot extract antitheses for a missing thesis")

        self._text = text
        self._not_like_these = not_like_these or []
        self._count = max(1, count)

        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        if thesis.is_simple:
            results = await self._process_simple_thesis(thesis)
            taxonomy = None
        else:
            taxonomy = await self._contextualize_taxonomy(thesis)
            candidates = await self._extract_candidates(thesis, taxonomy)
            selected = self._truncate_candidates(candidates)
            results = await self._persist_candidates(thesis, selected)

        # Build artifacts
        self._report.artifacts["thesis_hash"] = thesis.hash
        self._report.artifacts["antithesis_hashes"] = [
            r.component.hash for r in results
        ]
        self._report.artifacts["heuristic_similarity_by_hash"] = {
            r.component.hash: r.heuristic_similarity for r in results
        }
        if taxonomy:
            self._report.artifacts["apex_antithesis"] = taxonomy.apex

        # Summary
        thesis_type = "simple" if thesis.is_simple else "complex"
        self._report.summary = (
            f"Extracted {len(results)} antithesis(es) for {thesis_type} thesis "
            f"'{thesis.text[:50]}...'"
            if len(thesis.text) > 50
            else f"Extracted {len(results)} antithesis(es) for {thesis_type} thesis '{thesis.text}'"
        )

        return results

    # --- Simple Thesis Processing ---

    async def _process_simple_thesis(
        self, thesis: Statement
    ) -> list[AntithesisProcessed]:
        """Process a simple thesis: generate direct negation."""
        result = await self._conversation.submit(
            response_model=SimpleNegationDto,
            user_content=self._simple_negation_prompt(thesis.text),
        )

        # Skip if matches not_like_these
        if result.negation in self._not_like_these:
            return []

        # Create antithesis component
        antithesis = Statement(
            text=result.negation,
            meaning="dx://taxonomy/Simple",
        )
        antithesis.commit()
        self._report.node_created(
            antithesis, meta={"mode": 1.0, "type": "simple_negation"}
        )

        # Connect OPPOSITE_OF
        thesis.oppositions.connect(antithesis)
        self._report.relationship_created(
            thesis.oppositions,
            thesis,
            antithesis,
        )

        # Add rationale (created first so it can be provider for estimations)
        arousal_value = arousal_label_to_value(result.arousal_label)
        rationale = Rationale(
            text=f"Direct negation of simple thesis. Arousal: {result.arousal_label} - {result.arousal_explanation}"
        )
        rationale.set_explanation_target(antithesis)
        rationale.commit()
        self._report.node_created(rationale)

        # Store estimations with rationale as provider
        manager = EstimationManager()
        mode_est = manager.upsert_estimation(
            antithesis, ModeEstimation, 1.0, provider=rationale
        )
        arousal_est = manager.upsert_estimation(
            antithesis, ArousalEstimation, arousal_value, provider=rationale
        )
        if mode_est:
            self._report.node_updated(mode_est, patch={"value": 1.0})
        if arousal_est:
            self._report.node_updated(arousal_est, patch={"value": arousal_value})

        return [
            AntithesisProcessed(
                component=antithesis,
                mode_value=1.0,
                arousal_value=arousal_value,
                heuristic_similarity=1.0,
            )
        ]

    def _simple_negation_prompt(self, thesis: str) -> str:
        """Build user prompt for simple thesis negation."""
        context_section = (
            f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        )
        return f"""{context_section}Generate a direct negation for this simple thesis.

Thesis: "{thesis}"

Generate:
1. A direct negation statement that is the logical opposite (similar length to thesis)
2. Assess the arousal level using the scale from the system prompt
3. Explain your arousal assessment"""

    # --- Complex Thesis Processing ---

    async def _contextualize_taxonomy(
        self, thesis: Statement
    ) -> ContextualizedTaxonomyDto:
        """Contextualize universal taxonomy for a complex thesis."""
        return await contextualize_taxonomy(
            thesis_statement=thesis.text,
            thesis_meaning=thesis.meaning or "",
            text=self._text,
            conversation=self._conversation,
        )

    async def _extract_candidates(
        self,
        thesis: Statement,
        taxonomy: ContextualizedTaxonomyDto,
    ) -> list[AntithesisCandidate]:
        """Extract raw candidates from LLM (no DB writes)."""
        mode_points: list[tuple[str, float, str]] = []
        for field_name, mode_value in ContextualizedTaxonomyDto.MODE_FIELDS.items():
            branch_context = getattr(taxonomy, field_name, "")
            if branch_context:
                mode_points.append((field_name, mode_value, branch_context))

        if not mode_points:
            return []

        # Decide how many candidates per branch
        per_branch = self._candidates_per_branch(len(mode_points))

        # Generate all candidates in parallel using isolated calls
        if per_branch == 1:
            tasks = [
                self._conversation.isolate().submit(
                    response_model=ModePointResultDto,
                    user_content=self._mode_point_prompt(
                        thesis.text,
                        taxonomy.apex,
                        field_name.capitalize(),
                        branch_context,
                        mode_value,
                    ),
                )
                for field_name, mode_value, branch_context in mode_points
            ]
            raw_results = await asyncio.gather(*tasks)
            # Wrap single results into lists for uniform handling
            batch_results: list[list[ModePointResultDto]] = [
                [r] for r in raw_results
            ]
        else:
            tasks = [
                self._conversation.isolate().submit(
                    response_model=ModePointBatchResultDto,
                    user_content=self._mode_point_batch_prompt(
                        thesis.text,
                        taxonomy.apex,
                        field_name.capitalize(),
                        branch_context,
                        mode_value,
                        per_branch,
                    ),
                )
                for field_name, mode_value, branch_context in mode_points
            ]
            raw_batch_results = await asyncio.gather(*tasks)
            batch_results = [r.candidates for r in raw_batch_results]

        # Convert to candidates, filtering not_like_these
        candidates: list[AntithesisCandidate] = []
        for (field_name, mode_value, _), results in zip(mode_points, batch_results):
            for dto in results:
                if dto.statement in self._not_like_these:
                    continue
                candidates.append(
                    AntithesisCandidate(
                        statement_text=dto.statement,
                        branch=field_name,
                        mode_value=mode_value,
                        arousal_value=arousal_label_to_value(dto.arousal_label),
                        heuristic_similarity=dto.heuristic_similarity,
                        explanation=dto.explanation,
                    )
                )

        return candidates

    def _candidates_per_branch(self, num_branches: int) -> int:
        """Determine how many candidates to request per branch.

        We need enough raw material to fill `self._count` after truncation.
        Request at least ceil(count / branches) per branch, minimum 1.
        """
        import math
        return max(1, math.ceil(self._count / num_branches))

    def _truncate_candidates(
        self, candidates: list[AntithesisCandidate]
    ) -> list[AntithesisCandidate]:
        """Round-robin truncation: maximize branch coverage, then fill by highest HS.

        Algorithm:
        1. Group by branch, sort each group by HS descending
        2. Round 1: take top item from each branch (breadth)
        3. Round 2+: from remaining items across all branches, take highest HS
        4. Stop when we have `self._count` items
        """
        if len(candidates) <= self._count:
            return candidates

        # Group by branch, sort by HS descending within each group
        from collections import defaultdict
        groups: dict[str, list[AntithesisCandidate]] = defaultdict(list)
        for c in candidates:
            groups[c.branch].append(c)
        for branch in groups:
            groups[branch].sort(key=lambda c: c.heuristic_similarity, reverse=True)

        selected: list[AntithesisCandidate] = []

        # Round 1: one from each branch (highest HS), sorted by HS for deterministic ordering
        first_picks = []
        for branch in groups:
            if groups[branch]:
                first_picks.append(groups[branch].pop(0))
        first_picks.sort(key=lambda c: c.heuristic_similarity, reverse=True)

        for pick in first_picks:
            if len(selected) >= self._count:
                break
            selected.append(pick)

        # Round 2+: fill remaining slots from all leftover items by highest HS
        if len(selected) < self._count:
            remaining = []
            for branch in groups:
                remaining.extend(groups[branch])
            remaining.sort(key=lambda c: c.heuristic_similarity, reverse=True)

            for item in remaining:
                if len(selected) >= self._count:
                    break
                selected.append(item)

        return selected

    async def _persist_candidates(
        self,
        thesis: Statement,
        candidates: list[AntithesisCandidate],
    ) -> list[AntithesisProcessed]:
        """Persist selected candidates to the graph."""
        results: list[AntithesisProcessed] = []
        manager = EstimationManager()
        antithesis_meaning = StatementClassification.lookup_antithesis_meaning(thesis)

        for candidate in candidates:
            antithesis = Statement(
                text=candidate.statement_text,
                meaning=antithesis_meaning,
            )
            antithesis.commit()
            self._report.node_created(
                antithesis,
                meta={
                    "mode": candidate.mode_value,
                    "branch": candidate.branch,
                    "heuristic_similarity": candidate.heuristic_similarity,
                },
            )

            thesis.oppositions.connect(antithesis)
            self._report.relationship_created(
                thesis.oppositions, thesis, antithesis,
            )

            mode_name = candidate.branch.capitalize()
            rationale = Rationale(
                text=(
                    f"Generated at {mode_name} (Mode={candidate.mode_value:.1f}) branch. "
                    f"Heuristic Similarity={candidate.heuristic_similarity:.2f}. "
                    f"{candidate.explanation}"
                )
            )
            rationale.set_explanation_target(antithesis)
            rationale.commit()
            self._report.node_created(rationale)

            mode_est = manager.upsert_estimation(
                antithesis, ModeEstimation, candidate.mode_value, provider=rationale
            )
            arousal_est = manager.upsert_estimation(
                antithesis, ArousalEstimation, candidate.arousal_value, provider=rationale
            )
            if mode_est:
                self._report.node_updated(mode_est, patch={"value": candidate.mode_value})
            if arousal_est:
                self._report.node_updated(arousal_est, patch={"value": candidate.arousal_value})

            results.append(
                AntithesisProcessed(
                    component=antithesis,
                    mode_value=candidate.mode_value,
                    arousal_value=candidate.arousal_value,
                    heuristic_similarity=candidate.heuristic_similarity,
                )
            )

        return results

    def _mode_point_prompt(
        self,
        thesis: str,
        apex: str,
        branch_name: str,
        branch_context: str,
        mode_value: float,
    ) -> str:
        """Build user prompt for generating antithesis at a mode point."""
        max_words = self.settings.component_length
        return f"""Generate an antithesis candidate for this thesis at Mode {mode_value:.1f} ({branch_name}).

Thesis: "{thesis}"
Apex ({apex}): represents complete [T]-lessness
Target branch ({branch_name}): {branch_context}

Generate:
1. An antithesis that represents {branch_name} of the thesis (1-{max_words} words, no explanations in the statement)
2. Rate its HS (Heuristic Similarity) to the apex concept using the scale from the system prompt
3. Assess the arousal level of this T↔A tension using the arousal scale from the system prompt
4. Provide combined reasoning for your choices"""

    def _mode_point_batch_prompt(
        self,
        thesis: str,
        apex: str,
        branch_name: str,
        branch_context: str,
        mode_value: float,
        count: int,
    ) -> str:
        """Build user prompt for generating multiple antithesis candidates at a mode point."""
        max_words = self.settings.component_length
        return f"""Generate {count} distinct antithesis candidates for this thesis at Mode {mode_value:.1f} ({branch_name}).

Thesis: "{thesis}"
Apex ({apex}): represents complete [T]-lessness
Target branch ({branch_name}): {branch_context}

For each candidate, generate:
1. An antithesis that represents {branch_name} of the thesis (1-{max_words} words, no explanations in the statement)
2. Rate its HS (Heuristic Similarity) to the apex concept using the scale from the system prompt
3. Assess the arousal level of this T↔A tension using the arousal scale from the system prompt
4. Provide combined reasoning for your choices

Each candidate must be meaningfully different from the others — explore different angles within this branch."""
