"""
AntithesisExtraction: Capability for generating antitheses for a thesis.

Generates "ideal" antitheses at mode=1.0, HS=1.0.
For classifying arbitrary user-provided antitheses, use AntithesisClassification.

Usage:
    service = AntithesisExtraction()
    antitheses = await service.execute(thesis=thesis, text=text)
    for a in antitheses:
        print(a.statement)
    # Access report if needed:
    print(service.report.heuristic_similarity_by_hash)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.brainstorming.capabilities.antithesis_classification import (
    SYSTEM_PROMPT,
    ContextualizedTaxonomyDto,
    arousal_label_to_value,
    contextualize_taxonomy,
)
from dialectical_framework.agents.brainstorming.capabilities.statement_classification import (
    StatementClassification,
)
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.estimation import ArousalEstimation, ModeEstimation
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

    statement: str = Field(description="Antithesis candidate statement (similar length to thesis)")
    heuristic_similarity: float = Field(
        ge=0.0, le=1.0,
        description="Heuristic Similarity to apex concept (0.0-1.0)"
    )
    arousal_label: str = Field(
        description="Arousal level: dormant/latent/low/mild/moderate/elevated/high/intense/active"
    )
    explanation: str = Field(description="Combined reasoning for statement, HS, and arousal")


class SimpleNegationDto(BaseModel):
    """Result of generating negation for a simple thesis."""

    negation: str = Field(description="Direct negation statement (similar length to thesis)")
    arousal_label: str = Field(description="dormant/latent/low/mild/moderate/elevated/high/intense/active")
    arousal_explanation: str = Field(description="Reasoning for arousal level")


# --- Result Container ---


@dataclass
class AntithesisProcessed:
    """Container for an antithesis with its metadata."""

    component: DialecticalComponent
    mode_value: float
    arousal_value: float
    heuristic_similarity: float


# --- Service ---


class AntithesisExtraction(ExecutableCapability[list[AntithesisProcessed]], SettingsAware):
    """
    Capability for extracting antitheses for a thesis.

    Handles both simple and complex theses:
    - Simple: Direct negation with HS=1.0, Mode=1.0
    - Complex: Contextualized taxonomy with candidates at key Mode points

    Returns list of DialecticalComponent. Access .report for effects.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def execute(
        self,
        thesis: DialecticalComponent,
        text: str = "",
        not_like_these: Optional[list[str]] = None,
    ) -> list[AntithesisProcessed]:
        """
        Extract antitheses for a thesis.

        Args:
            thesis: The thesis component to generate antitheses for
            text: Optional source content context
            not_like_these: Statements to avoid (for dedup)

        Returns:
            List of AntithesisResult containing component and metadata (mode, arousal, HS)
        """
        # Reset report on each execution (allows instance reuse)
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Early validation
        if not thesis or not thesis.statement:
            raise ValueError("Cannot extract antitheses for a missing thesis")

        self._text = text
        self._not_like_these = not_like_these or []

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # TODO: we need to extract several samples per category, now we're extracting only one
        # TODO: we need to be able to hint (intent?) what to extract
        # TODO: we need to be able to extract variation of a given antithesis, meaning a variation on the statement+mode?
        # Process based on complexity
        if thesis.is_simple:
            results = await self._process_simple_thesis(thesis)
            taxonomy = None
        else:
            taxonomy = await self._contextualize_taxonomy(thesis)
            results = await self._process_complex_thesis(thesis, taxonomy)

        # Build artifacts
        self._report.artifacts["thesis_hash"] = thesis.hash
        self._report.artifacts["antithesis_hashes"] = [r.component.hash for r in results]
        self._report.artifacts["heuristic_similarity_by_hash"] = {
            r.component.hash: r.heuristic_similarity for r in results
        }
        if taxonomy:
            self._report.artifacts["apex_antithesis"] = taxonomy.apex

        # Summary
        thesis_type = "simple" if thesis.is_simple else "complex"
        self._report.summary = (
            f"Extracted {len(results)} antithesis(es) for {thesis_type} thesis "
            f"'{thesis.statement[:50]}...'" if len(thesis.statement) > 50
            else f"Extracted {len(results)} antithesis(es) for {thesis_type} thesis '{thesis.statement}'"
        )

        return results

    # --- Simple Thesis Processing ---

    async def _process_simple_thesis(self, thesis: DialecticalComponent) -> list[AntithesisProcessed]:
        """Process a simple thesis: generate direct negation."""
        result = await self._conversation.submit(
            response_model=SimpleNegationDto,
            user_content=self._simple_negation_prompt(thesis.statement),
        )

        # Skip if matches not_like_these
        if result.negation in self._not_like_these:
            return []

        # Create antithesis component
        antithesis = DialecticalComponent(
            statement=result.negation,
            meaning="dx://taxonomy/Simple",
        )
        antithesis.commit()
        self._report.node_created(antithesis, meta={"mode": 1.0, "type": "simple_negation"})

        # Connect OPPOSITE_OF
        thesis.oppositions.connect(antithesis)
        self._report.relationship_created(
            thesis.oppositions, thesis, antithesis,
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
        mode_est = manager.upsert_estimation(antithesis, ModeEstimation, 1.0, provider=rationale)
        arousal_est = manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value, provider=rationale)
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
        context_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        return f"""{context_section}Generate a direct negation for this simple thesis.

Thesis: "{thesis}"

Generate:
1. A direct negation statement that is the logical opposite (similar length to thesis)
2. Assess the arousal level using the scale from the system prompt
3. Explain your arousal assessment"""

    # --- Complex Thesis Processing ---

    async def _contextualize_taxonomy(
        self, thesis: DialecticalComponent
    ) -> ContextualizedTaxonomyDto:
        """Contextualize universal taxonomy for a complex thesis."""
        return await contextualize_taxonomy(
            thesis_statement=thesis.statement,
            thesis_meaning=thesis.meaning or "",
            text=self._text,
            conversation=self._conversation,
        )

    async def _process_complex_thesis(
        self,
        thesis: DialecticalComponent,
        taxonomy: ContextualizedTaxonomyDto,
    ) -> list[AntithesisProcessed]:
        """Generate antithesis candidates using contextualized taxonomy (parallel)."""
        # Collect mode points to process
        mode_points: list[tuple[str, float, str]] = []
        for field_name, mode_value in ContextualizedTaxonomyDto.MODE_FIELDS.items():
            branch_context = getattr(taxonomy, field_name, "")
            if branch_context:
                mode_points.append((field_name, mode_value, branch_context))

        if not mode_points:
            return []

        # Generate all candidates in parallel using isolated calls
        tasks = [
            self._conversation.isolate().submit(
                response_model=ModePointResultDto,
                user_content=self._mode_point_prompt(
                    thesis.statement,
                    taxonomy.apex,
                    field_name.capitalize(),
                    branch_context,
                    mode_value,
                ),
            )
            for field_name, mode_value, branch_context in mode_points
        ]
        mode_results = await asyncio.gather(*tasks)

        # Process results
        results: list[AntithesisProcessed] = []
        manager = EstimationManager()
        antithesis_meaning = StatementClassification.lookup_antithesis_meaning(thesis)

        for (field_name, mode_value, _), mode_result in zip(mode_points, mode_results):
            # Skip if matches not_like_these
            if mode_result.statement in self._not_like_these:
                continue

            arousal_value = arousal_label_to_value(mode_result.arousal_label)

            # Create antithesis component
            antithesis = DialecticalComponent(
                statement=mode_result.statement,
                meaning=antithesis_meaning,
            )
            antithesis.commit()
            self._report.node_created(
                antithesis,
                meta={"mode": mode_value, "branch": field_name, "heuristic_similarity": mode_result.heuristic_similarity}
            )

            # Connect OPPOSITE_OF
            thesis.oppositions.connect(antithesis)
            self._report.relationship_created(
                thesis.oppositions, thesis, antithesis,
            )

            # Add rationale (created first so it can be provider for estimations)
            mode_name = field_name.capitalize()
            rationale = Rationale(
                text=(
                    f"Generated at {mode_name} (Mode={mode_value:.1f}) branch. "
                    f"Heuristic Similarity={mode_result.heuristic_similarity:.2f}, Arousal={mode_result.arousal_label}. "
                    f"{mode_result.explanation}"
                )
            )
            rationale.set_explanation_target(antithesis)
            rationale.commit()
            self._report.node_created(rationale)

            # Store estimations with rationale as provider
            mode_est = manager.upsert_estimation(antithesis, ModeEstimation, mode_value, provider=rationale)
            arousal_est = manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value, provider=rationale)
            if mode_est:
                self._report.node_updated(mode_est, patch={"value": mode_value})
            if arousal_est:
                self._report.node_updated(arousal_est, patch={"value": arousal_value})

            results.append(
                AntithesisProcessed(
                    component=antithesis,
                    mode_value=mode_value,
                    arousal_value=arousal_value,
                    heuristic_similarity=mode_result.heuristic_similarity,
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
