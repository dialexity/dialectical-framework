"""
ThesisExtraction: Concern for extracting theses from content.

Extracts thesis candidates from source content (Step 1-2), then uses
StatementClassification to classify and anchor each candidate (Step 3-4).

For direct theses (not extracted from content), use StatementClassification directly.

Usage:
    service = ThesisExtraction()
    theses = await service.resolve(text=article_text, count=4)
    for t in theses:
        print(t.text)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.statement_classification import (
    ClassificationResult, StatementClassification)
from dialectical_framework.graph.nodes.statement import \
    Statement
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    pass


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical thesis extractor.

Your task is to extract assertable content from source text and identify thesis candidates.

Extract content that could be theses:
- Claims/Assertions: "The system should...", "We use X because..."
- Values/Principles: "Security is paramount", "User experience first"
- Goals/Objectives: Desired outcomes, success criteria
- Constraints: "Must not exceed...", "Cannot allow..."
- Design Decisions: Architecture choices, trade-offs made
- Assumptions: Implicit or explicit premises

A valid thesis candidate must be:
- ASSERTABLE: Can be evaluated as true/false, good/bad, present/absent
- SUBSTANTIVE: Not trivial or tautological
- ATOMIC: Single concept, not compound (if compound, decompose)

Respond with structured output matching the requested format."""


# --- Step 1 DTOs: Extract Assertable Content ---


class ContentItemDto(BaseModel):
    """A raw content item extracted from source."""

    content: str = Field(description="The raw content item")
    content_type: str = Field(
        description="Type: claim, value, goal, constraint, decision, assumption"
    )


class ExtractedContentDto(BaseModel):
    """Result of Step 1: raw content extraction."""

    items: list[ContentItemDto] = Field(description="List of extracted content items")


# --- Step 2 DTOs: Thesis Candidate Identification ---


class CandidateCheckDto(BaseModel):
    """Result of checking if content is a thesis candidate."""

    is_assertable: bool = Field(description="Can it be true/false, good/bad?")
    is_substantive: bool = Field(description="Is it non-trivial?")
    is_atomic: bool = Field(description="Is it a single concept?")
    atomic_theses: list[str] = Field(
        default_factory=list,
        description="If compound, decomposed atomic theses. If atomic, single item.",
    )


# --- Concern ---


class ThesisExtraction(ReasonableConcern[list[Statement]], SettingsAware):
    """
    Concern for extracting theses from content.

    Steps:
    1. Extract assertable content from source text
    2. Identify and validate thesis candidates
    3. Use StatementClassification to classify and anchor each candidate

    For direct theses (not from content), use StatementClassification directly.

    Returns list of Statement. Access .report for effects.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        text: str,
        count: int = 4,
        focus: str = "",
        domain_hint: str = "",
        not_like_these: Optional[list[str]] = None,
    ) -> list[Statement]:
        """
        Extract theses from content text.

        Args:
            text: Source content to extract from
            count: Maximum number of theses to extract (1-4)
            focus: Filter for extraction (e.g., 'security', 'design decisions')
            domain_hint: Taxonomy domain hint passed to StatementClassification
            not_like_these: Existing statements to avoid

        Returns:
            List of extracted Statement theses
        """

        # Early validation - don't hit LLM for nothing
        text = text.strip() if text else ""
        if not text or count <= 0:
            self._report.ok = True
            self._report.summary = "No extraction needed (empty text or count <= 0)"
            self._report.artifacts["thesis_hashes"] = []
            return []

        self._text = text
        self._count = min(count, 4)
        self._focus = focus
        self._domain_hint = domain_hint
        self._not_like_these = not_like_these or []

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # STEP 1: Extract assertable content
        content_items = await self._step1_extract_content()

        # STEP 2: Identify thesis candidates (parallel validation)
        all_candidates = await self._step2_identify_candidates(content_items)

        if not all_candidates:
            self._report.ok = True
            self._report.summary = "No thesis candidates found in content"
            self._report.artifacts["thesis_hashes"] = []
            return []

        # Limit to requested count
        candidates_to_process = all_candidates[: self._count]

        # STEP 3-4: Classify and anchor each candidate using StatementClassification
        components = await self._classify_candidates(candidates_to_process)

        # Build artifacts
        self._report.artifacts["thesis_hashes"] = [c.hash for c in components]
        self._report.artifacts["candidate_count"] = len(all_candidates)
        self._report.ok = True
        self._report.summary = f"Extracted {len(components)} thesis(es) from content"

        return components

    # --- STEP 1: Extract Assertable Content ---

    async def _step1_extract_content(self) -> list[ContentItemDto]:
        """Extract assertable content from source text."""
        result = await self._conversation.submit(
            response_model=ExtractedContentDto,
            user_content=self._step1_prompt(),
        )
        return result.items

    def _step1_prompt(self) -> str:
        """Build prompt for content extraction."""
        focus_guidance = f"\nFocus on: {self._focus}" if self._focus else ""
        rule_out = ""
        if self._not_like_these:
            rule_out = "\nAvoid items similar to:\n- " + "\n- ".join(
                self._not_like_these
            )

        return f"""<source_text>
{self._text}
</source_text>

STEP 1: Extract Assertable Content

From this text, extract content items that could be theses.
{focus_guidance}
Extract up to {self._count + 2} most important content items.
{rule_out}"""

    # --- STEP 2: Identify Thesis Candidates ---

    async def _step2_identify_candidates(
        self, content_items: list[ContentItemDto]
    ) -> list[str]:
        """Validate and decompose content items into thesis candidates."""
        if not content_items:
            return []

        # Process all items in parallel
        tasks = [
            self._conversation.isolate().submit(
                response_model=CandidateCheckDto,
                user_content=self._step2_prompt(item.content, item.content_type),
            )
            for item in content_items
        ]
        check_results = await asyncio.gather(*tasks)

        # Collect valid candidates
        candidates: list[str] = []
        for result in check_results:
            if result.is_assertable and result.is_substantive:
                candidates.extend(result.atomic_theses)

        # Deduplicate while preserving order
        return list(dict.fromkeys(candidates))

    def _step2_prompt(self, content: str, content_type: str) -> str:
        """Build prompt for candidate validation."""
        max_words = self.settings.component_length
        return f"""STEP 2: Thesis Candidate Identification

Content item: "{content}"
Type: {content_type}

Check if this is a valid thesis candidate:
1. Is it ASSERTABLE? (Can be evaluated as true/false, good/bad, present/absent)
2. Is it SUBSTANTIVE? (Not trivial or tautological)
3. Is it ATOMIC? (Single concept, not compound)

If compound (multiple concepts joined), decompose into atomic theses.
Each atomic thesis should be 1-{max_words} words.

Return:
- is_assertable: true/false
- is_substantive: true/false
- is_atomic: true/false
- atomic_theses: list of atomic thesis statements"""

    # --- STEP 3-4: Classify using StatementClassification ---

    async def _classify_candidates(
        self, candidates: list[str]
    ) -> list[Statement]:
        """Classify each candidate and create components."""
        # Create classifiers and run in parallel
        classifiers = [StatementClassification() for _ in candidates]
        tasks = [
            classifier.resolve(
                statement=statement,
                text=self._text,
                domain_hint=self._domain_hint,
            )
            for classifier, statement in zip(classifiers, candidates)
        ]

        results: list[ClassificationResult] = await asyncio.gather(*tasks)

        # Merge reports from each classification
        for classifier in classifiers:
            self._report = self._report.merge(classifier.report)

        # Create components from classification results
        components: list[Statement] = []
        for result in results:
            component = self._create_component(result)
            components.append(component)

        return components

    def _create_component(self, result: ClassificationResult) -> Statement:
        """Create component and rationale from classification result."""
        component = Statement(
            text=result.statement, meaning=result.meaning
        )
        component.commit()

        classification_label = "SIMPLE" if result.is_simple else "COMPLEX"
        self._report.node_created(
            component,
            patch={"meaning": result.meaning, "text": result.statement},
            meta={"classification": classification_label},
        )

        # Add rationale
        rationale_text = (
            f"Classification: {classification_label}. {result.classification_reasoning}"
        )
        if result.taxonomy_reasoning:
            rationale_text += f" {result.taxonomy_reasoning}"

        rationale = Rationale(text=rationale_text)
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)
        self._report.relationship_created(rationale.explains, rationale, component)

        return component
