"""
AnchoringAgent: Surfaces theses for BrainstormingAgent (Phase 1 of polarity-finder).

Uses conversational pattern: all steps share context through conversation history,
enabling prompt caching. Forks conversation for child ExtractTheses tool.

Extraction-centric approach:
1. Parse intent → understand requirements
2. Extract fresh theses (with retries on different params)
3. Semantic dedup against existing vocabulary
4. Cleanup redundant extractions (prefer DB versions)
5. Create Ideas with final set
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import BaseTool
from pydantic import BaseModel, Field, PrivateAttr

from dialectical_framework.agents.brainstorming.capabilities.statement_deduplication import (
    StatementDeduplication,
)
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.node_repository import NodeRepository

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- System Prompt ---

SYSTEM_PROMPT = """You are an anchoring agent for dialectical brainstorming.

Your task is to:
1. Parse unstructured intent into structured parameters
2. Identify direct theses from intent or determine what to extract
3. Perform semantic deduplication against existing vocabulary

When parsing intent:
- Look for direct thesis mentions (e.g., "anchor thesis Trust", "Love", single concepts)
- Extract count, focus, constraints, domain hints
- If no inputs available and intent mentions a topic, treat it as direct thesis

For semantic deduplication:
- Compare newly extracted statements against existing vocabulary
- Only match if confidence >= 0.7 (clearly the same concept)
- Consider same core concept even if worded differently"""


# --- DTOs for LLM structured outputs ---


class ParsedIntentDto(BaseModel):
    """Result of parsing the unstructured intent."""

    count: int = Field(default=4, description="Number of theses to surface (1-10)")
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


class ExtractedThesesDto(BaseModel):
    """Result of extracting thesis data from tool output."""

    thesis_hashes: list[str] = Field(
        default_factory=list,
        description="List of thesis hash prefixes (7-8 character hex strings)",
    )
    has_error: bool = Field(
        default=False,
        description="True if the tool output indicates an error",
    )
    error_message: str = Field(
        default="",
        description="Error message if has_error is True",
    )


# --- Main Agent ---


class AnchoringAgent(BaseTool):
    """
    Surfaces theses for BrainstormingAgent by fulfilling anchoring intent.

    Uses conversational pattern where all steps share context through
    conversation history, enabling prompt caching.

    Receives unstructured intent from BrainstormingAgent and:
    1. Parses intent to understand requirements (count, constraints, focus)
    2. Extracts fresh theses via ExtractTheses (with retries)
    3. Deduplicates against existing vocabulary (prefers DB versions)
    4. Cleans up redundant extractions
    5. Creates Ideas node with final component set

    This is Phase 1 of the polarity-finder algorithm (Steps 1-4).
    """

    intent: str = Field(
        description=(
            "Unstructured intent from BrainstormingAgent describing what theses to surface. "
            "Examples: 'extract 5 theses about trust and integrity', "
            "'find theses from inputs, prefer existing ones if suitable', "
            "'surface 3 new theses about security, avoid anything about performance'"
        )
    )

    _conversation: ConversationFacilitator = PrivateAttr(default_factory=ConversationFacilitator)

    async def call(self) -> str:
        """Execute anchoring: extract, dedup, cleanup, create Ideas."""
        # Initialize conversation with system prompt
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # 1. Parse intent
        parsed = await self._parse_intent()

        # 2. Get context
        input_text = await self._get_input_text()
        vocab = self._get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]  # Avoid all existing, including rejected

        # 3. Handle direct theses if specified in intent
        direct_hashes: list[str] = []
        if parsed.direct_theses:
            direct_hashes = await self._anchor_direct_theses(parsed.direct_theses, parsed)

        # 4. Extraction loop (if we have inputs and need more theses)
        extracted_hashes: list[str] = []
        remaining_count = parsed.count - len(direct_hashes)

        if remaining_count > 0 and input_text:
            # Add direct thesis statements to not_like_these to avoid duplicates
            for h in direct_hashes:
                stmt = self._get_statement_by_hash(h)
                if stmt and stmt not in not_like_these:
                    not_like_these.append(stmt)

            extracted_hashes = await self._extraction_loop(
                input_text=input_text,
                parsed=parsed,
                not_like_these=not_like_these,
            )

        # Combine direct and extracted
        all_hashes = direct_hashes + extracted_hashes

        if not all_hashes:
            if not input_text and not parsed.direct_theses:
                return "No inputs in scope and no direct theses in intent. Add inputs or specify theses directly."
            return f"No theses extracted. Intent: {self.intent}"

        # 5. Semantic dedup (if we have existing vocabulary)
        final_components: list[DialecticalComponent] = []
        deleted_count = 0

        if vocab and extracted_hashes:
            # Only dedup extracted (not direct theses - those are intentional)
            deduplicator = StatementDeduplication()
            dedup_result = await deduplicator.deduplicate(
                extracted_hashes=extracted_hashes,
                vocabulary=vocab,
            )
            deleted_count = dedup_result.deleted_count

            # Resolve kept + replacement components
            deduped_components = self._resolve_components(dedup_result.kept_hashes)
            for db_hash in dedup_result.replacements.values():
                comp = self._resolve_component(db_hash)
                if comp and comp not in deduped_components:
                    deduped_components.append(comp)

            # Add direct thesis components first
            final_components = self._resolve_components(direct_hashes) + deduped_components
        else:
            # No existing vocab or no extractions - keep all
            final_components = self._resolve_components(all_hashes)

        # 6. Create Ideas
        ideas = self._create_ideas(final_components, parsed)

        # 7. Report
        return self._build_report(
            parsed=parsed,
            extracted_count=len(extracted_hashes),
            direct_count=len(direct_hashes),
            deleted_count=deleted_count,
            final_components=final_components,
            ideas=ideas,
        )

    # --- Intent Parsing ---

    def _parse_intent_prompt(self, input_preview: str) -> str:
        """Build user prompt for parsing intent."""
        return f"""Parse this anchoring intent and extract structured parameters.

**Intent:** {self.intent}

**Available inputs preview:** {input_preview if input_preview else "No inputs"}

Determine:

1. **direct_theses** - CRITICAL: Identify if the intent IS, CONTAINS, or implies direct theses.

   The intent might BE the thesis itself:
   - "Sugar" → direct_theses: ["Sugar"]
   - "Love" → direct_theses: ["Love"]
   - "Trust, Integrity" → direct_theses: ["Trust", "Integrity"]

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

   Only leave direct_theses empty if:
   - Inputs ARE available, AND
   - Intent explicitly asks to "extract", "find", "surface" theses FROM those inputs

2. count: How many theses to surface (default 4, max 10)
3. constraints: What to avoid or exclude
4. preferences: What to prefer (e.g., "prefer existing", "focus on X")
5. domain_hint: Derive a contextual domain hint from intent
6. focus: Topic/theme to focus extraction on (only if extracting from inputs)

If direct_theses are found, count = len(direct_theses).
If no direct_theses and count isn't specified, use 4."""

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
    ) -> list[str]:
        """
        Anchor direct theses specified in intent.

        Uses ExtractTheses with each thesis as direct input (short text mode).
        Forks conversation to pass context to child tool.
        Returns list of component hashes.
        """
        from dialectical_framework.agents.brainstorming.tools.extract_theses import (
            ExtractTheses,
        )

        hashes: list[str] = []
        for thesis in theses:
            extract_tool = ExtractTheses(
                text=thesis,
                count=1,
                domain_hint=parsed.domain_hint,
            )
            result = await extract_tool.call()
            new_hashes = await self._parse_hashes_from_result(result)
            hashes.extend(new_hashes)

        return hashes

    # --- Extraction Loop ---

    async def _extraction_loop(
        self,
        input_text: str,
        parsed: ParsedIntentDto,
        not_like_these: list[str],
    ) -> list[str]:
        """
        Extract theses with retries on different parameters.

        Forks conversation for each ExtractTheses call.
        Returns list of extracted component hash prefixes.
        """
        from dialectical_framework.agents.brainstorming.tools.extract_theses import (
            ExtractTheses,
        )

        extracted_hashes: list[str] = []
        max_attempts = 4

        # Build parameter variations to try
        param_variations = self._build_param_variations(parsed)

        for attempt, params in enumerate(param_variations[:max_attempts]):
            if len(extracted_hashes) >= parsed.count:
                break

            # How many more do we need?
            remaining = parsed.count - len(extracted_hashes)

            extract_tool = ExtractTheses(
                text=input_text,
                count=remaining,
                focus=params.get("focus", ""),
                domain_hint=params.get("domain_hint", ""),
                not_like_these=not_like_these + [
                    self._get_statement_by_hash(h) for h in extracted_hashes
                ],
            )

            result = await extract_tool.call()

            # Parse hashes from result
            new_hashes = await self._parse_hashes_from_result(result)
            extracted_hashes.extend(new_hashes)

            # Update not_like_these for next iteration
            for h in new_hashes:
                stmt = self._get_statement_by_hash(h)
                if stmt and stmt not in not_like_these:
                    not_like_these.append(stmt)

        return extracted_hashes[:parsed.count]

    def _build_param_variations(self, parsed: ParsedIntentDto) -> list[dict]:
        """Build list of parameter variations to try."""
        variations = []

        # First: use parsed parameters
        variations.append({
            "domain_hint": parsed.domain_hint,
            "focus": parsed.focus,
        })

        # Second: try without focus (broader extraction)
        if parsed.focus:
            variations.append({
                "domain_hint": parsed.domain_hint,
                "focus": "",
            })

        # Third: try without domain hint
        if parsed.domain_hint:
            variations.append({
                "domain_hint": "",
                "focus": parsed.focus,
            })

        # Fourth: no hints at all (broadest)
        variations.append({
            "domain_hint": "",
            "focus": "",
        })

        return variations

    async def _parse_hashes_from_result(self, result: str) -> list[str]:
        """
        Extract thesis hashes from ExtractTheses tool output using LLM.

        The tool output format may vary (JSON, error messages, etc.), so we use
        an LLM to robustly extract the relevant information.
        """
        extracted = await self._conversation.submit(
            response_model=ExtractedThesesDto,
            user_content=f"""Extract thesis hash prefixes from this tool output.

Look for hash prefixes (7-8 character hex strings) that identify created thesis components.

If the output indicates an error or failure, set has_error=True.

**Tool Output:**
{result}""",
        )

        if extracted.has_error:
            return []

        return extracted.thesis_hashes

    def _get_statement_by_hash(self, hash_prefix: str) -> str:
        """Get statement text for a component by hash prefix."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash_prefix)
            if comp and isinstance(comp, DialecticalComponent):
                return comp.statement
        except ValueError:
            pass
        return ""

    # --- Helpers ---

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

    @inject
    async def _get_input_previews(
        self,
        input_resolver: InputResolver = Provide[DI.input_resolver],
    ) -> str:
        """Get preview (first 500 chars) of each input in scope."""
        repo = InputRepository()
        inputs = repo.get_all()

        if not inputs:
            return "No inputs"

        previews = []
        for i, input_node in enumerate(inputs, 1):
            resolved = await input_resolver.resolve(input_node)
            preview = resolved[:500] + "..." if len(resolved) > 500 else resolved
            previews.append(f"[Input {i}]\n{preview}")

        return "\n\n".join(previews)

    def _get_vocabulary_with_rationales(self) -> list[dict]:
        """Get vocabulary components with their rationales."""
        repo = DialecticalComponentRepository()
        vocab = list(repo.get_vocabulary())

        result = []
        for comp in vocab:
            # Get rationale if exists
            rationale_text = ""
            for rat, _ in comp.rationales.all():
                rationale_text = rat.text
                break  # Just use first rationale

            result.append({
                "hash": comp.hash or "",
                "statement": comp.statement,
                "meaning": comp.meaning,
                "rejected": comp.rejected,
                "rationale": rationale_text,
            })

        return result

    def _resolve_component(self, hash_prefix: str) -> Optional[DialecticalComponent]:
        """Resolve hash prefix to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(hash_prefix)
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None

    def _resolve_components(self, hashes: list[str]) -> list[DialecticalComponent]:
        """Resolve list of hash prefixes to components."""
        return [c for h in hashes if (c := self._resolve_component(h))]

    def _create_ideas(
        self,
        components: list[DialecticalComponent],
        parsed: ParsedIntentDto,
    ) -> Optional[Ideas]:
        """Create Ideas node and wire to components and inputs."""
        if not components:
            return None

        ideas = Ideas(intent=self.intent)
        ideas.save()

        # Connect to inputs in scope
        input_repo = InputRepository()
        for input_node in input_repo.get_all():
            ideas.inputs.connect(input_node)

        # Connect to components
        for comp in components:
            ideas.statements.connect(comp)

        ideas.commit()

        # Attach rationale explaining how intent was interpreted
        if parsed.reasoning:
            rationale = Rationale(text=parsed.reasoning)
            rationale.set_explanation_target(ideas)
            rationale.commit()

        return ideas

    def _build_report(
        self,
        parsed: ParsedIntentDto,
        extracted_count: int,
        deleted_count: int,
        final_components: list[DialecticalComponent],
        ideas: Optional[Ideas],
        direct_count: int = 0,
    ) -> str:
        """Build the result report."""
        lines = ["**Anchoring Complete**", ""]

        lines.append(f"**Intent parsed:** {parsed.reasoning}")
        lines.append(f"**Target count:** {parsed.count}")
        if parsed.domain_hint:
            lines.append(f"**Domain:** {parsed.domain_hint}")
        if parsed.focus:
            lines.append(f"**Focus:** {parsed.focus}")
        if parsed.direct_theses:
            lines.append(f"**Direct theses:** {', '.join(parsed.direct_theses)}")

        lines.append("")
        if direct_count > 0:
            lines.append(f"**Direct theses anchored:** {direct_count}")
        if extracted_count > 0:
            lines.append(f"**Extracted from inputs:** {extracted_count} theses")
        if deleted_count > 0:
            lines.append(f"**Deduplicated:** {deleted_count} (preferred existing DB versions)")

        lines.append("")
        lines.append(f"**Final theses ({len(final_components)}):**")
        for comp in final_components:
            lines.append(f"  [{comp.short_hash}] {comp.statement}")

        if ideas:
            lines.append("")
            lines.append(f"**Ideas:** {ideas.short_hash}")

        return "\n".join(lines)
