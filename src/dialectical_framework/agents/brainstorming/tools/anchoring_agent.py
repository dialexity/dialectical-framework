"""
AnchoringAgent: Surfaces theses for BrainstormingAgent (Phase 1 of polarity-finder).

Extraction-centric approach:
1. Parse intent → understand requirements
2. Extract fresh theses (with retries on different params)
3. Semantic dedup against existing vocabulary
4. Cleanup redundant extractions (prefer DB versions)
5. Create Ideas with final set
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from mirascope import BaseTool, Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse
from pydantic import BaseModel, Field
from dependency_injector.wiring import inject, Provide

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.dialectical_component_repository import (
    DialecticalComponentRepository,
)
from dialectical_framework.graph.repositories.input_repository import InputRepository
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    from dialectical_framework.protocols.input_resolver import InputResolver


# --- DTOs for LLM structured outputs ---


class ParsedIntentDto(BaseModel):
    """Result of parsing the unstructured intent."""

    count: int = Field(default=4, description="Number of theses to surface (1-10)")
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


class SemanticMatchDto(BaseModel):
    """A single semantic match between extraction and DB component."""

    extraction_hash: str = Field(description="Hash prefix of the extracted component")
    db_hash: Optional[str] = Field(
        default=None,
        description="Hash prefix of semantically equivalent DB component, or null if no match",
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence of the match (0.0-1.0)",
    )


class SemanticDedupDto(BaseModel):
    """Result of batch semantic deduplication."""

    matches: list[SemanticMatchDto] = Field(
        default_factory=list,
        description="List of matches between extractions and DB components",
    )


# --- Main Agent ---


class AnchoringAgent(BaseTool, HasBrain, SettingsAware):
    """
    Surfaces theses for BrainstormingAgent by fulfilling anchoring intent.

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

    async def call(self) -> str:
        """Execute anchoring: extract, dedup, cleanup, create Ideas."""
        # 1. Parse intent
        parsed = await self._parse_intent()

        # 2. Get context
        input_text = await self._get_input_text()
        if not input_text:
            return "No inputs in scope. Add inputs first."

        vocab = self._get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]  # Avoid all existing, including rejected

        # 3. Extraction loop
        extracted_hashes = await self._extraction_loop(
            input_text=input_text,
            parsed=parsed,
            not_like_these=not_like_these,
        )

        if not extracted_hashes:
            return f"No theses extracted. Intent: {self.intent}"

        # 4. Semantic dedup (if we have existing vocabulary)
        final_components: list[DialecticalComponent] = []
        deleted_count = 0

        if vocab:
            dedup_result = await self._semantic_dedup(extracted_hashes, vocab)
            final_components, deleted_count = self._apply_dedup(
                extracted_hashes, dedup_result
            )
        else:
            # No existing vocab - keep all extractions
            final_components = self._resolve_components(extracted_hashes)

        # 5. Create Ideas
        ideas = self._create_ideas(final_components, parsed)

        # 6. Report
        return self._build_report(
            parsed=parsed,
            extracted_count=len(extracted_hashes),
            deleted_count=deleted_count,
            final_components=final_components,
            ideas=ideas,
        )

    # --- Intent Parsing ---

    @prompt_template(
        """
        USER:
        Parse this anchoring intent and extract structured parameters.

        **Intent:** {intent}

        **Available inputs preview:** {input_preview}

        Determine:
        1. count: How many theses to surface (default 4, max 10)
        2. constraints: What to avoid or exclude
        3. preferences: What to prefer (e.g., "prefer existing", "focus on X")
        4. domain_hint: Derive a contextual domain hint from intent and inputs
           (e.g., "software architecture", "team dynamics", "security practices")
        5. focus: Topic/theme to focus extraction on

        If count isn't specified, use 4.
        Derive domain_hint from the intent and input content - don't leave empty
        if there's contextual signal.
        """
    )
    def _parse_intent_prompt(self, input_preview: str) -> Messages.Type:
        return {
            "computed_fields": {
                "intent": self.intent,
                "input_preview": input_preview if input_preview else "No inputs",
            }
        }

    async def _parse_intent(self) -> ParsedIntentDto:
        """Parse unstructured intent into structured parameters."""
        input_previews = await self._get_input_previews()

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=ParsedIntentDto)
        async def _parse():
            return self._parse_intent_prompt(input_previews)

        result = await _parse()
        # Clamp count
        result.count = max(1, min(result.count, 10))
        return result

    # --- Extraction Loop ---

    async def _extraction_loop(
        self,
        input_text: str,
        parsed: ParsedIntentDto,
        not_like_these: list[str],
    ) -> list[str]:
        """
        Extract theses with retries on different parameters.

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
            extract_tool._brain = self._brain
            extract_tool._settings = self._settings

            result = await extract_tool.call()

            # Parse hashes from result
            new_hashes = self._parse_hashes_from_result(result)
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

    def _parse_hashes_from_result(self, result: str) -> list[str]:
        """Extract component hashes from ExtractTheses result."""
        import re

        # Look for "hashes in the graph: hash1, hash2, ..."
        match = re.search(r"hashes in the graph:\s*(.+)", result, re.IGNORECASE)
        if match:
            hashes_str = match.group(1)
            return [h.strip() for h in hashes_str.split(",") if h.strip()]
        return []

    def _get_statement_by_hash(self, hash_prefix: str) -> str:
        """Get statement text for a component by hash prefix."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_prefix(hash_prefix)
            if comp and isinstance(comp, DialecticalComponent):
                return comp.statement
        except ValueError:
            pass
        return ""

    # --- Semantic Deduplication ---

    @prompt_template(
        """
        USER:
        Compare these newly extracted theses against existing vocabulary.
        Find semantic equivalents (same concept, possibly different wording).

        **Newly Extracted:**
        {extractions}

        **Existing Vocabulary:**
        {vocabulary}

        For each extraction, determine if there's a semantically equivalent
        component in the existing vocabulary. Consider:
        - Same core concept (even if worded differently)
        - Same taxonomy branch/meaning
        - Rationale indicates same derivation

        Only match if confidence >= 0.7 (clearly the same concept).
        If no match, set db_hash to null.
        """
    )
    def _semantic_dedup_prompt(
        self, extractions: str, vocabulary: str
    ) -> Messages.Type:
        return {
            "computed_fields": {
                "extractions": extractions,
                "vocabulary": vocabulary,
            }
        }

    async def _semantic_dedup(
        self,
        extracted_hashes: list[str],
        vocab: list[dict],
    ) -> SemanticDedupDto:
        """Batch LLM call to find semantic equivalents."""
        # Build extraction descriptions
        extraction_lines = []
        for h in extracted_hashes:
            comp = self._resolve_component(h)
            if comp:
                extraction_lines.append(
                    f"[{comp.short_hash}] {comp.statement} (meaning: {comp.meaning or 'none'})"
                )

        # Build vocabulary descriptions (include rationale)
        vocab_lines = []
        # TODO: Limit to avoid token explosion?
        for v in vocab[:100]:
            if not v.get("rejected"):
                rationale_hint = f" - {v['rationale'][:80]}..." if v.get("rationale") else ""
                vocab_lines.append(
                    f"[{v['hash'][:7]}] {v['statement']} (meaning: {v.get('meaning', 'none')}){rationale_hint}"
                )

        if not extraction_lines or not vocab_lines:
            return SemanticDedupDto(matches=[])

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=SemanticDedupDto)
        async def _dedup():
            return self._semantic_dedup_prompt(
                extractions="\n".join(extraction_lines),
                vocabulary="\n".join(vocab_lines),
            )

        return await _dedup()

    def _apply_dedup(
        self,
        extracted_hashes: list[str],
        dedup_result: SemanticDedupDto,
    ) -> tuple[list[DialecticalComponent], int]:
        """
        Apply dedup results: delete redundant extractions, keep DB versions.

        Returns (final_components, deleted_count).
        """
        final_components: list[DialecticalComponent] = []
        deleted_count = 0
        repo = DialecticalComponentRepository()

        # Build match lookup
        matches = {m.extraction_hash: m for m in dedup_result.matches}

        for ext_hash in extracted_hashes:
            # Find match for this extraction
            match = None
            for m in dedup_result.matches:
                if ext_hash.startswith(m.extraction_hash) or m.extraction_hash.startswith(ext_hash):
                    match = m
                    break

            if match and match.db_hash and match.confidence >= 0.7:
                # Has equivalent in DB - delete extraction, use DB version
                ext_comp = self._resolve_component(ext_hash)
                if ext_comp:
                    if repo.safe_delete(ext_comp):
                        deleted_count += 1

                # Add DB version to final set
                db_comp = self._resolve_component(match.db_hash)
                if db_comp and db_comp not in final_components:
                    final_components.append(db_comp)
            else:
                # No equivalent - keep extraction
                ext_comp = self._resolve_component(ext_hash)
                if ext_comp and ext_comp not in final_components:
                    final_components.append(ext_comp)

        return final_components, deleted_count

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
            comp = repo.find_by_prefix(hash_prefix)
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
    ) -> str:
        """Build the result report."""
        lines = ["**Anchoring Complete**", ""]

        lines.append(f"**Intent parsed:** {parsed.reasoning}")
        lines.append(f"**Target count:** {parsed.count}")
        if parsed.domain_hint:
            lines.append(f"**Domain:** {parsed.domain_hint}")
        if parsed.focus:
            lines.append(f"**Focus:** {parsed.focus}")

        lines.append("")
        lines.append(f"**Extracted:** {extracted_count} theses")
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
