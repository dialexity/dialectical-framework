"""
SurfaceTheses: Extracts theses from inputs for AnalystAgent (Phase 1 of polarity-finder).

Extraction-only — does NOT anchor literal concepts (use AnchorTheses for that).

Flow:
1. Get input text (required — returns None if no inputs)
2. Parse intent → extraction parameters (count, focus, domain_hint)
3. Extract fresh theses via ThesisExtraction (with retries on different params)
4. Semantic dedup against existing vocabulary
5. Create Ideas with final set

Usage:
    skill = SurfaceTheses(intent="extract 3 theses about trust")
    ideas = await skill.resolve()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Optional

from dependency_injector.wiring import Provide, inject
from mirascope import llm
from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.reasonable_concern import ReasonableConcern
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

SYSTEM_PROMPT = """You are an extraction agent for dialectical analysis.

Your task is to parse extraction instructions into structured parameters for thesis extraction from inputs.

When parsing intent:
- Extract count, focus, constraints, domain hints
- The intent describes WHAT to extract from the available inputs
- Do not treat the intent itself as a thesis — it is extraction guidance"""


# --- DTOs for LLM structured outputs ---


class ParsedIntentDto(BaseModel):
    """Result of parsing the extraction intent."""

    count: int = Field(default=3, description="Number of theses to extract (1-10)")
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
    Extracts theses from inputs for AnalystAgent.

    Requires inputs in scope — returns None if no inputs available.
    For anchoring literal concepts, use AnchorTheses instead.

    Flow:
    1. Gets input text (required)
    2. Parses extraction intent (count, focus, domain_hint, constraints)
    3. Extracts fresh theses via ThesisExtraction (with retries)
    4. Deduplicates against existing vocabulary (prefers DB versions)
    5. Creates Ideas node with final component set
    """

    def __init__(self, intent: str, input_hashes: list[str] | None = None) -> None:
        self.intent = intent
        self.input_hashes = input_hashes
        self._conversation: Optional[ConversationFacilitator] = None

    async def resolve(self) -> Optional[Ideas]:
        """Extract theses from inputs. Returns Ideas container or None if no inputs."""
        # 1. Get input text — required for extraction
        input_text = await self._get_input_text()
        if not input_text:
            self._report.ok = True
            self._report.summary = "No inputs in scope for extraction"
            self._report.artifacts["thesis_hashes"] = []
            return None

        # 2. Parse extraction intent
        self._conversation = ConversationFacilitator()
        self._conversation.set_system_prompt(SYSTEM_PROMPT)
        parsed = await self._parse_intent()

        # 3. Get existing vocabulary for dedup
        comp_repo = StatementRepository()
        vocab = comp_repo.get_vocabulary_with_rationales()
        not_like_these = [c["statement"] for c in vocab]

        # 4. Extraction loop
        extracted_components, extraction_reports = await self._extraction_loop(
            input_text=input_text,
            parsed=parsed,
            target_count=parsed.count,
            not_like_these=not_like_these,
        )
        for r in extraction_reports:
            self._report = self._report.merge(r)

        if not extracted_components:
            self._report.ok = True
            self._report.summary = "No theses extracted"
            self._report.artifacts["thesis_hashes"] = []
            return None

        # 5. Semantic dedup
        deduped: list[Statement] = []
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
            deduped = dedup_result.components
        else:
            deduped = extracted_components

        # 6. Create Ideas
        ideas = self._create_ideas(deduped, parsed)

        # 7. Build final artifacts
        self._report.artifacts["thesis_hashes"] = [c.hash for c in deduped]
        self._report.artifacts["ideas_hash"] = ideas.hash if ideas else None
        self._report.artifacts["extracted_theses_count"] = len(extracted_components)
        self._report.artifacts["duplicates_found_and_deleted"] = deleted_count
        self._report.artifacts["theses"] = [
            {"hash": c.hash, "text": c.text} for c in deduped
        ]
        self._report.summary = f"Extracted {len(deduped)} thesis(es)"

        return ideas

    # --- Intent Parsing ---

    def _parse_intent_prompt(self, input_preview: str) -> str:
        """Build user prompt for parsing extraction intent."""
        return f"""Parse this extraction intent into structured parameters.

**Intent:** {self.intent}

**Available inputs preview:** {input_preview}

Determine:

1. **count**: Number of theses to extract.
   - If a number is specified in intent (e.g., "3 theses" → count: 3), use it
   - Otherwise default to 3
2. **constraints**: What to avoid or exclude
3. **preferences**: What to prefer (e.g., "prefer existing", "focus on X")
4. **domain_hint**: Derive a contextual domain hint from intent and inputs
5. **focus**: Topic/theme to focus extraction on"""

    async def _parse_intent(self) -> ParsedIntentDto:
        """Parse unstructured intent into structured parameters."""
        input_previews = await self._get_input_previews()

        result = await self._conversation.submit(
            response_model=ParsedIntentDto,
            user_content=self._parse_intent_prompt(input_previews),
        )

        result.count = max(1, min(result.count, 10))
        return result

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
        """Get preview of each input (uses digest if available, else first 500 chars)."""
        inputs = self._get_inputs()

        if not inputs:
            return "No inputs"

        previews = []
        for i, input_node in enumerate(inputs, 1):
            if input_node.digest:
                previews.append(f"[Input {i}]\n{input_node.digest}")
            else:
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
        self._report.node_created(ideas)

        # Connect to inputs (filtered or all)
        for input_node in self._get_inputs():
            ideas.inputs.connect(input_node)
            self._report.relationship_created(ideas.inputs, ideas, input_node)

        # Connect to components
        for comp in components:
            ideas.statements.connect(comp)
            self._report.relationship_created(ideas.statements, ideas, comp)

        ideas.commit()
        self._report.node_committed(ideas)

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
    intent: Annotated[
        str,
        Field(
            description="Extraction instructions — e.g. 'extract 3 theses about trust', 'find themes in the inputs', 'surface theses about security'"
        ),
    ],
    input_hashes: Annotated[
        list[str] | None,
        Field(
            description="Optional list of input hashes to process selectively. If None, processes all inputs in scope."
        ),
    ] = None,
) -> str:
    """Extract theses from inputs. Requires inputs in scope — returns empty if none.
    For anchoring named concepts directly, use anchor_theses instead.

    Examples: 'extract 5 theses about trust and integrity',
    'find theses from inputs, prefer existing ones if suitable',
    'surface 3 new theses about security, avoid anything about performance'
    """
    concern = SurfaceTheses(intent=intent, input_hashes=input_hashes)
    await concern.resolve()
    return str(concern.report)
