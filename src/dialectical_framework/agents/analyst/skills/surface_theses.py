"""
SurfaceTheses: Surfaces theses for AnalystAgent (Phase 1 of polarity-finder).

Uses conversational pattern: all steps share context through conversation history,
enabling prompt caching.

Extraction-centric approach:
1. Parse intent → understand requirements
2. Extract fresh theses via ThesisExtraction (with retries on different params)
3. Semantic dedup against existing vocabulary
4. Cleanup redundant extractions (prefer DB versions)
5. Create Ideas with final set

Usage:
    # Programmatic (web app)
    agent = SurfaceTheses(intent="extract theses about trust")
    theses = await agent.resolve()
    for t in theses:
        print(t.text)
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.concerns.statement_classification import (
    ClassificationResult, StatementClassification)
from dialectical_framework.concerns.statement_deduplication import \
    StatementDeduplication
from dialectical_framework.concerns.thesis_extraction import ThesisExtraction
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.statement import Statement
from dialectical_framework.graph.repositories.input_repository import \
    InputRepository
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository
from dialectical_framework.graph.repositories.statement_repository import \
    StatementRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- System Prompt ---

SYSTEM_PROMPT = """You are an anchoring agent for dialectical analysis.

Your task is to parse unstructured intent into structured parameters for thesis extraction.

When parsing intent:
- Look for direct thesis mentions (e.g., "anchor thesis Trust", "Love", single concepts)
- Extract count, focus, constraints, domain hints
- If no inputs available and intent mentions a topic, treat it as direct thesis"""


# --- DTOs for LLM structured outputs ---


class ParsedIntentDto(BaseModel):
    """Result of parsing the unstructured intent."""

    count: int = Field(default=3, description="Number of theses to surface (1-10)")
    direct_theses: list[str] = Field(
        default_factory=list,
        description="Direct theses explicitly specified in intent (e.g., 'anchor thesis Trust' → ['Trust'])",
    )
    constraints: list[str] = Field(
        default_factory=list,
        description="Things to avoid (e.g., 'not about security', 'exclude X')",
    )
    preferences: list[str] = Field(
        default_factory=list,
        description="Preferences (e.g., 'prefer existing', 'focus on Y')",
    )
    domain_hint: str = Field(
        default="",
        description="Contextual domain hint derived from intent/inputs (e.g., 'software architecture', 'interpersonal relationships', 'organizational dynamics')",
    )
    focus: str = Field(
        default="",
        description="Topic focus for extraction",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of how intent was interpreted",
    )


# --- Main Agent ---


class SurfaceTheses(ReasonableConcern[Optional[Ideas]]):
    """
    Surfaces theses for AnalystAgent by fulfilling anchoring intent.

    Uses conversational pattern where all steps share context through
    conversation history, enabling prompt caching.

    Receives unstructured intent from AnalystAgent and:
    1. Parses intent to understand requirements (count, constraints, focus)
    2. Extracts fresh theses via ThesisExtraction (with retries)
    3. Deduplicates against existing vocabulary (prefers DB versions)
    4. Cleans up redundant extractions
    5. Creates Ideas node with final component set

    This is Phase 1 of the polarity-finder algorithm (Steps 1-4).
    """

    def __init__(self, intent: str, input_hashes: list[str] | None = None) -> None:
        self.intent = intent
        self.input_hashes = input_hashes
        self._conversation: Optional[ConversationFacilitator] = None

    async def resolve(self) -> Optional[Ideas]:
        """Resolve anchoring: extract, dedup, cleanup, create Ideas. Returns Ideas container."""
        # Reset report on each execution (allows instance reuse)

        # Initialize conversation (lazy init for Mirascope tool compatibility)
        self._conversation = ConversationFacilitator()
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # 1. Parse intent
        parsed = await self._parse_intent()

        # 2. Get context
        input_text = await self._get_input_text()
        comp_repo = StatementRepository()
        vocab = comp_repo.get_vocabulary_with_rationales()
        not_like_these = [
            c["statement"] for c in vocab
        ]  # Avoid all existing, including rejected

        # 3. Handle direct theses if specified in intent
        direct_components: list[Statement] = []
        if parsed.direct_theses:
            direct_components, direct_reports = await self._anchor_direct_theses(
                parsed.direct_theses, parsed, text=input_text
            )
            for r in direct_reports:
                self._report = self._report.merge(r)

        # 4. Extraction loop (if we have inputs and need more theses)
        extracted_components: list[Statement] = []
        remaining_count = parsed.count - len(direct_components)

        if remaining_count > 0 and input_text:
            # Add direct thesis statements to not_like_these to avoid duplicates
            for comp in direct_components:
                if comp.text not in not_like_these:
                    not_like_these.append(comp.text)

            extracted_components, extraction_reports = await self._extraction_loop(
                input_text=input_text,
                parsed=parsed,
                target_count=remaining_count,
                not_like_these=not_like_these,
            )
            for r in extraction_reports:
                self._report = self._report.merge(r)

        # Check if we have anything
        if not direct_components and not extracted_components:
            self._report.ok = True
            self._report.summary = "No theses extracted"
            if not input_text and not parsed.direct_theses:
                self._report.summary = (
                    "No inputs in scope and no direct theses in intent"
                )
            self._report.artifacts["thesis_hashes"] = []
            return None

        # 5. Semantic dedup ONLY for extracted components (not direct theses)
        # Direct theses represent explicit user intent and should be preserved as-is.
        # They already get hash-based dedup via commit (upsert behavior).
        deduped_extracted: list[Statement] = []
        deleted_count = 0

        if vocab and extracted_components:
            extracted_hashes = [c.hash for c in extracted_components]
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.resolve(
                extracted_hashes=extracted_hashes,
                vocabulary=vocab,
                text=input_text,
            )
            deleted_count = dedup_result.deleted_count
            deduped_extracted = dedup_result.components
        else:
            # No existing vocab or no extracted - keep extracted as-is
            deduped_extracted = extracted_components

        # Combine: direct theses first (user intent wins), then deduped extracted
        final_components = direct_components + deduped_extracted

        # 6. Create Ideas
        ideas = self._create_ideas(final_components, parsed)

        # 7. Build final artifacts
        self._report.artifacts["thesis_hashes"] = [c.hash for c in final_components]
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["theses_count_found_in_intent"] = len(direct_components)
        self._report.artifacts["extracted_theses_count"] = len(extracted_components)
        self._report.artifacts["duplicates_found_and_deleted"] = deleted_count
        self._report.summary = f"Anchored {len(final_components)} thesis(es)"

        return ideas

    # --- Intent Parsing ---

    def _parse_intent_prompt(self, input_preview: str) -> str:
        """Build user prompt for parsing intent."""
        return f"""Parse this anchoring intent of the user, understand it and extract structured parameters.

**Intent:** {self.intent}

**Available inputs preview:** {input_preview if input_preview else "No inputs"}

Determine:

1. **direct_theses** - CRITICAL: Identify if the intent IS, CONTAINS, or implies direct theses.

   The intent might BE the thesis itself (single word or short phrase):
   - "Sugar" → direct_theses: ["Sugar"]
   - "Love" → direct_theses: ["Love"]
   - "Remote work" → direct_theses: ["Remote work"]
   - "Trust, Integrity" → direct_theses: ["Trust", "Integrity"]

   The intent might express a TENSION between two concepts:
   - "Spirituality vs Money" → direct_theses: ["Spirituality", "Money"]
   - "Stay married or get divorced" → direct_theses: ["Stay married", "Get divorced"]
   - "Freedom versus Security" → direct_theses: ["Freedom", "Security"]
   - "torn between X and Y" → direct_theses: ["X", "Y"]

   Or it might explicitly name theses to anchor:
   - "anchor thesis 'Trust'" → direct_theses: ["Trust"]
   - "add Love as thesis" → direct_theses: ["Love"]

   Or it might ask ABOUT a topic (especially when no inputs are available):
   - "give me the main idea about love" → direct_theses: ["Love"]
   - "what about trust?" → direct_theses: ["Trust"]
   - "explore data consistency" → direct_theses: ["Data Consistency"]

   **IMPORTANT**: If no inputs are available (input_preview says "No inputs"),
   and the intent mentions a topic/concept, extract that topic as a direct thesis.
   The user wants to explore that concept even without source material.

   **IMPORTANT**: Single words and short phrases ARE direct theses. Don't try to
   "extract from inputs" when the intent itself IS the concept to explore.

   Only leave direct_theses empty if:
   - Inputs ARE available, AND
   - Intent explicitly asks to "extract", "find", "surface" theses FROM those inputs

2. **count**: Extract the number if specified in intent (e.g., "3 theses" → count: 3).
   - If direct_theses found, count = len(direct_theses)
   - If a number is specified in intent, use that number
   - If nothing specified, default to 3
3. constraints: What to avoid or exclude
4. preferences: What to prefer (e.g., "prefer existing", "focus on X")
5. domain_hint: Derive a contextual domain hint from intent
6. focus: Topic/theme to focus extraction on (only if extracting from inputs)"""

    async def _parse_intent(self) -> ParsedIntentDto:
        """Parse unstructured intent into structured parameters."""
        input_previews = await self._get_input_previews()

        result = await self._conversation.submit(
            response_model=ParsedIntentDto,
            user_content=self._parse_intent_prompt(input_previews),
        )

        # Clamp count
        result.count = max(1, min(result.count, 10))

        # If direct theses specified, adjust count
        if result.direct_theses:
            result.count = max(result.count, len(result.direct_theses))
        return result

    # --- Direct Thesis Anchoring ---

    async def _anchor_direct_theses(
        self,
        theses: list[str],
        parsed: ParsedIntentDto,
        text: str = "",
    ) -> tuple[list[Statement], list[ExecutionReport]]:
        """
        Anchor direct theses specified in intent.

        Uses StatementClassification to classify each thesis, then creates components.
        Returns tuple of (components, reports).
        """
        # Create classifiers and run in parallel
        classifiers = [StatementClassification() for _ in theses]
        tasks = [
            classifier.resolve(
                statement=thesis,
                text=text,
                domain_hint=parsed.domain_hint,
            )
            for classifier, thesis in zip(classifiers, theses)
        ]

        results: list[ClassificationResult] = await asyncio.gather(*tasks)
        reports = [classifier.report for classifier in classifiers]

        # Create components from classification results
        components: list[Statement] = []
        for result in results:
            component = self._create_component_from_classification(result)
            components.append(component)

        return components, reports

    def _create_component_from_classification(
        self, result: ClassificationResult
    ) -> Statement:
        """Create component and rationale from classification result."""
        component = Statement(text=result.statement, meaning=result.meaning)
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

    # --- Extraction Loop ---

    async def _extraction_loop(
        self,
        input_text: str,
        parsed: ParsedIntentDto,
        target_count: int,
        not_like_these: list[str],
    ) -> tuple[list[Statement], list[ExecutionReport]]:
        """
        Extract theses with retries on different parameters.

        Args:
            input_text: Text to extract from
            parsed: Parsed intent (for focus, domain_hint)
            target_count: Number of theses to extract (accounts for direct theses already added)
            not_like_these: Statements to avoid

        Returns tuple of (extracted components, reports).
        """
        extracted_components: list[Statement] = []
        reports: list[ExecutionReport] = []
        max_attempts = 4

        # Build parameter variations to try
        param_variations = self._build_param_variations(parsed)

        for attempt, params in enumerate(param_variations[:max_attempts]):
            if len(extracted_components) >= target_count:
                break

            # How many more do we need?
            remaining = target_count - len(extracted_components)

            service = ThesisExtraction()
            new_components = await service.resolve(
                text=input_text,
                count=remaining,
                focus=params.get("focus", ""),
                domain_hint=params.get("domain_hint", ""),
                not_like_these=not_like_these + [c.text for c in extracted_components],
            )
            reports.append(service.report)

            extracted_components.extend(new_components)

            # Update not_like_these for next iteration
            for comp in new_components:
                if comp.text not in not_like_these:
                    not_like_these.append(comp.text)

        return extracted_components[:target_count], reports

    def _build_param_variations(self, parsed: ParsedIntentDto) -> list[dict]:
        """Build list of parameter variations to try."""
        variations = []

        # First: use parsed parameters
        variations.append(
            {
                "domain_hint": parsed.domain_hint,
                "focus": parsed.focus,
            }
        )

        # Second: try without focus (broader extraction)
        if parsed.focus:
            variations.append(
                {
                    "domain_hint": parsed.domain_hint,
                    "focus": "",
                }
            )

        # Third: try without domain hint
        if parsed.domain_hint:
            variations.append(
                {
                    "domain_hint": "",
                    "focus": parsed.focus,
                }
            )

        # Fourth: no hints at all (broadest)
        variations.append(
            {
                "domain_hint": "",
                "focus": "",
            }
        )

        return variations

    def _get_statement_by_hash(self, hash: str) -> str:
        """Get statement text for a component by hash."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash)
            if comp and isinstance(comp, Statement):
                return comp.text
        except ValueError:
            pass
        return ""

    # --- Helpers ---

    def _get_inputs(self) -> list:
        """Get inputs: filtered by input_hashes if provided, otherwise all in scope."""
        if self.input_hashes:
            from dialectical_framework.graph.nodes.input import Input

            repo = NodeRepository()
            return repo.find_by_hashes(self.input_hashes, node_type=Input)
        return InputRepository().get_all()

    @inject
    async def _get_input_text(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get concatenated text from inputs (filtered by input_hashes if provided)."""
        inputs = self._get_inputs()

        if not inputs:
            return ""

        texts = []
        for input_node in inputs:
            resolved = await input_resolver.resolve(input_node)
            texts.append(resolved)

        return "\n\n---\n\n".join(texts)

    @inject
    async def _get_input_previews(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get preview (first 500 chars) of each input."""
        inputs = self._get_inputs()

        if not inputs:
            return "No inputs"

        previews = []
        for i, input_node in enumerate(inputs, 1):
            resolved = await input_resolver.resolve(input_node)
            preview = resolved[:500] + "..." if len(resolved) > 500 else resolved
            previews.append(f"[Input {i}]\n{preview}")

        return "\n\n".join(previews)

    def _resolve_component(self, hash: str) -> Optional[Statement]:
        """Resolve hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash)
            if isinstance(comp, Statement):
                return comp
        except ValueError:
            pass
        return None

    def _resolve_components(self, hashes: list[str]) -> list[Statement]:
        """Resolve list of hashes to components."""
        return [c for h in hashes if (c := self._resolve_component(h))]

    def _create_ideas(
        self,
        components: list[Statement],
        parsed: ParsedIntentDto,
    ) -> Optional[Ideas]:
        """Create Ideas node and wire to components and inputs. Records effects in self._report."""
        if not components:
            return None

        ideas = Ideas(intent=self.intent)
        ideas.save()

        # Connect to inputs (filtered or all)
        for input_node in self._get_inputs():
            ideas.inputs.connect(input_node)
            self._report.relationship_created(ideas.inputs, ideas, input_node)

        # Connect to components
        for comp in components:
            ideas.statements.connect(comp)
            self._report.relationship_created(ideas.statements, ideas, comp)

        ideas.commit()
        self._report.node_created(ideas)

        # Attach rationale explaining how intent was interpreted
        if parsed.reasoning:
            rationale = Rationale(text=parsed.reasoning)
            rationale.set_explanation_target(ideas)
            rationale.commit()
            self._report.node_created(rationale)
            self._report.relationship_created(
                rationale.explains,
                rationale,
                ideas,
            )

        return ideas


@llm.tool
async def surface_theses(
    intent: Annotated[str, Field(description="What theses to find — e.g. 'extract 3 theses about trust', 'Love', 'find tensions in the situation'")],
    input_hashes: Annotated[list[str] | None, Field(description="Optional list of input hashes to process selectively. If None, processes all inputs in scope.")] = None,
) -> str:
    """Surfaces theses for dialectical analysis by fulfilling anchoring intent.

    Receives unstructured intent and extracts theses from inputs,
    deduplicates against existing vocabulary, and creates Ideas node.

    Examples: 'extract 5 theses about trust and integrity',
    'find theses from inputs, prefer existing ones if suitable',
    'surface 3 new theses about security, avoid anything about performance'
    """
    concern = SurfaceTheses(intent=intent, input_hashes=input_hashes)
    await concern.resolve()
    return str(concern.report)
