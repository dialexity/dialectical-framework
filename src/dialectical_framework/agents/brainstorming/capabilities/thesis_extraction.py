"""
ThesisExtractor: Service for extracting theses from content.

Core business logic for thesis extraction (Phase 1 of polarity-finder).
Returns RunReport with effects. Used by ExtractTheses tool and webapp routes.

Steps:
1. Extract assertable content from source
2. Identify thesis candidates (validate, decompose compounds)
3. Classify as Simple/Complex
4. Anchor complex theses in taxonomy
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.run_report import RunReport
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    pass


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical thesis extractor following the polarity-finder algorithm.

Your task is to extract, validate, classify, and anchor theses from source content.

## Thesis Classification

**SIMPLE/BINARY** - is_simple = true
- Can be directly true/false, yes/no, present/absent
- Has literal, binary nature
- Examples: "The sky is blue", "Water boils at 100C", "API is stateless"

**COMPLEX/SYSTEMIC** - is_simple = false
- Involves relationships, processes, or functional roles
- Concerns viability, health, or functioning of systems
- Has trade-offs, tensions, or dynamic aspects
- Examples: "Trust", "Data consistency", "Love", "User experience"

Heuristic: If thesis involves relationship, process, or functional role → Complex

## Taxonomy for Complex Theses

### SYSTEMIC TAXONOMY

| Branch | Question | General | Engineering | Ecology | Institutions | Love |
|--------|----------|---------|-------------|---------|--------------|------|
| Integrity | "Can it hold together?" | Cohesion | assembly | Symbiosis | Soc. cohesion | Bonding |
| Fidelity | "Can it process accurately?" | Modeling | simulation | Sensing | knowledge | Understanding |
| Exchange | "Can it exchange sustainably?" | Exchange | energy flow | Cyclicity | economy | Giving |
| Flexibility | "Can it adapt?" | Exploration | control | plasticity | innovation | Openness |
| Resilience | "Can it recover?" | Recovery | tolerance | resilience | crisis recovery | Repair |

### ELEMENTAL TAXONOMY (alternative)

| Element | Question | General T |
|---------|----------|-----------|
| Fire | "What energizes it?" | Activation |
| Earth | "What holds it together?" | Cohesion |
| Air | "How does it flow?" | Exchange |
| Water | "How does it adapt?" | Reflection |

Respond with structured output matching the requested format."""


# --- Step 1 DTOs: Extract Assertable Content ---


class ContentItemDto(BaseModel):
    """A raw content item extracted from source."""

    content: str = Field(description="The raw content item")
    content_type: str = Field(
        description="Type: claim, value, goal, constraint, decision, assumption, direct"
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


# --- Step 3 DTOs: Classification ---


class ClassificationDto(BaseModel):
    """Result of classifying a thesis."""

    is_simple: bool = Field(description="True=Simple/Binary, False=Complex/Systemic")
    reasoning: str = Field(description="Brief explanation")


# --- Step 4 DTOs: Taxonomy Location (for Complex) ---


class TaxonomyLocationDto(BaseModel):
    """Result of locating thesis in taxonomy."""

    taxonomy_type: str = Field(description="'systemic' or 'elemental'")
    domain: str = Field(
        default="General",
        description="For systemic: General, Engineering, Ecology, Institutions, Love",
    )
    branch: str = Field(description="Branch/Element name")
    leaf: str = Field(description="T concept from taxonomy")
    reasoning: str = Field(description="Brief explanation")


# --- Service ---


class ThesisExtraction(SettingsAware):
    """
    Service for extracting theses from content.

    Handles both direct thesis input and content extraction:
    - Short input ("Love") → treated as direct thesis
    - Long input → extract multiple theses from content

    Returns RunReport with all effects (nodes created, relationships).
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def extract(
        self,
        text: str,
        count: int = 3,
        focus: str = "",
        domain_hint: str = "",
        not_like_these: Optional[list[str]] = None,
    ) -> RunReport:
        """
        Extract theses from text.

        Args:
            text: Source content to extract from, OR direct thesis statement
            count: Maximum number of theses to extract (1-4)
            focus: Filter for extraction (e.g., 'security', 'design decisions')
            domain_hint: Taxonomy domain hint (e.g., 'Engineering', 'Love')
            not_like_these: Existing statements to avoid

        Returns:
            RunReport with effects and artifacts
        """
        self._text = text
        self._count = min(count, 4)
        self._focus = focus
        self._domain_hint = domain_hint
        self._not_like_these = not_like_these or []
        self._report = RunReport(tool="thesis_extractor")

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # STEP 1: Extract assertable content
        content_items = await self._step1_extract_content()

        # STEP 2: Identify thesis candidates
        all_candidates: list[str] = []
        for item in content_items:
            candidates = await self._step2_identify_candidates(item)
            all_candidates.extend(candidates)

        # Deduplicate
        all_candidates = list(dict.fromkeys(all_candidates))

        if not all_candidates:
            self._report.ok = True
            self._report.summary = "No thesis candidates found"
            self._report.artifacts["thesis_hashes"] = []
            return self._report

        # Limit to requested count
        candidates_to_process = all_candidates[: self._count]

        # STEP 3 & 4: Classify and anchor each candidate
        thesis_hashes: list[str] = []
        for thesis_text in candidates_to_process:
            component = await self._process_thesis(thesis_text)
            if component:
                thesis_hashes.append(component.hash)

        # Build artifacts
        self._report.artifacts["thesis_hashes"] = thesis_hashes
        self._report.artifacts["candidate_count"] = len(all_candidates)

        # Summary
        self._report.summary = f"Extracted {len(thesis_hashes)} thesis(es) from content"

        return self._report

    # --- STEP 1: Extract Assertable Content ---

    async def _step1_extract_content(self) -> list[ContentItemDto]:
        """STEP 1: Extract assertable content from source."""
        result = await self._conversation.submit(
            response_model=ExtractedContentDto,
            user_content=self._step1_prompt(),
        )
        return result.items

    def _step1_prompt(self) -> str:
        """Build user prompt for Step 1."""
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

From this text, extract content items that could be theses:
- Claims/Assertions: "The system should...", "We use X because..."
- Values/Principles: "Security is paramount", "User experience first"
- Goals/Objectives: Desired outcomes, success criteria
- Constraints: "Must not exceed...", "Cannot allow..."
- Design Decisions: Architecture choices, trade-offs made
- Assumptions: Implicit or explicit premises
- Direct: If the input is already a single concept/thesis, mark as "direct"
{focus_guidance}
Extract up to {self._count + 2} most important content items.
If the input is very short (1-5 words), treat it as a single direct thesis.
{rule_out}"""

    # --- STEP 2: Thesis Candidate Identification ---

    async def _step2_identify_candidates(self, item: ContentItemDto) -> list[str]:
        """STEP 2: Check if content is thesis candidate, decompose if compound."""
        # Direct input bypasses validation
        if item.content_type.lower() == "direct":
            return [item.content]

        result = await self._conversation.submit(
            response_model=CandidateCheckDto,
            user_content=self._step2_prompt(item.content, item.content_type),
        )

        if not result.is_assertable or not result.is_substantive:
            return []

        return result.atomic_theses

    def _step2_prompt(self, content: str, content_type: str) -> str:
        """Build user prompt for Step 2."""
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

    # --- STEP 3 & 4: Classification and Anchoring ---

    async def _process_thesis(self, thesis_text: str) -> Optional[DialecticalComponent]:
        """Process a single thesis: classify and anchor."""
        # STEP 3: Classify
        is_simple, classification_reasoning = await self._step3_classify(thesis_text)
        classification = "SIMPLE" if is_simple else "COMPLEX"

        # STEP 4: Locate in taxonomy (if complex)
        location = None
        if not is_simple:
            location = await self._step4_locate_in_taxonomy(thesis_text)

        # Build meaning URI
        meaning = self._build_meaning_uri(is_simple, location)

        # Create and commit component
        component = DialecticalComponent(statement=thesis_text, meaning=meaning)
        component.commit()
        self._report.node_created(
            component,
            meta={
                "classification": classification,
                "meaning": meaning,
            },
        )

        # Add rationale
        rationale_text = f"Classification: {classification}. {classification_reasoning}"
        if location:
            rationale_text += f" Taxonomy: {location.taxonomy_type}/{location.branch}/{location.leaf}. {location.reasoning}"

        rationale = Rationale(text=rationale_text)
        rationale.set_explanation_target(component)
        rationale.commit()
        self._report.node_created(rationale)

        return component

    async def _step3_classify(self, thesis: str) -> tuple[bool, str]:
        """STEP 3: Classify thesis as Simple (True) or Complex (False)."""
        result = await self._conversation.submit(
            response_model=ClassificationDto,
            user_content=self._step3_prompt(thesis),
        )
        return result.is_simple, result.reasoning

    def _step3_prompt(self, thesis: str) -> str:
        """Build user prompt for Step 3."""
        return f"""STEP 3: Thesis Classification

Thesis: "{thesis}"

Using the classification criteria from the system prompt, classify this thesis as:
- SIMPLE/BINARY (is_simple = true): literal, binary nature
- COMPLEX/SYSTEMIC (is_simple = false): involves relationships, processes, functional roles

Provide your reasoning."""

    async def _step4_locate_in_taxonomy(self, thesis: str) -> TaxonomyLocationDto:
        """STEP 4: Locate complex thesis in taxonomy."""
        return await self._conversation.submit(
            response_model=TaxonomyLocationDto,
            user_content=self._step4_prompt(thesis),
        )

    def _step4_prompt(self, thesis: str) -> str:
        """Build user prompt for Step 4."""
        domain_context = (
            f"\nDomain hint: {self._domain_hint}" if self._domain_hint else ""
        )
        return f"""STEP 4: Locate this COMPLEX thesis in the taxonomy.

Thesis: "{thesis}"
{domain_context}

Using the taxonomy tables from the system prompt, determine:
- taxonomy_type: "systemic" or "elemental"
- domain: For systemic only (General, Engineering, Ecology, Institutions, Love)
- branch: Branch or Element name
- leaf: The T concept from the table
- reasoning: Brief explanation"""

    # --- Build Meaning URI ---

    def _build_meaning_uri(
        self, is_simple: bool, location: Optional[TaxonomyLocationDto]
    ) -> str:
        """Build meaning URI from classification and taxonomy location."""
        if is_simple:
            return "dx://taxonomy/Simple"

        if not location:
            return "dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling"

        # Normalize
        taxonomy_type = location.taxonomy_type.lower().strip()
        domain = location.domain.strip().title() if location.domain else "General"
        branch = location.branch.strip().title() if location.branch else "Fidelity"
        leaf = (
            location.leaf.strip().title().replace(" ", "") if location.leaf else branch
        )

        valid_domains = ["General", "Engineering", "Ecology", "Institutions", "Love"]
        if domain not in valid_domains:
            domain = "General"

        if taxonomy_type == "elemental":
            valid_elements = ["Fire", "Earth", "Air", "Water"]
            if branch not in valid_elements:
                branch = "Earth"
            return f"dx://taxonomy/Elemental/Viability/{branch}/{leaf}"
        else:
            valid_branches = [
                "Integrity",
                "Fidelity",
                "Exchange",
                "Flexibility",
                "Resilience",
            ]
            if branch not in valid_branches:
                branch = "Fidelity"
            return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{leaf}"
