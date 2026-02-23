"""
ExtractTheses tool - Step-by-step thesis extraction following polarity-finder algorithm.

Handles both:
- Direct thesis input: text="Love" → classify and anchor
- Content extraction: text="Remote work improves..." → extract, classify, anchor

PHASE 1: CONTENT EXTRACTION
- STEP 1: Extract Assertable Content
- STEP 2: Thesis Candidate Identification
- STEP 3: Thesis Classification (Simple/Complex)
- STEP 4: Taxonomy Anchoring
"""

from __future__ import annotations

from mirascope import BaseTool, Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse
from pydantic import BaseModel, Field

from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain


# --- Step 1 DTOs: Extract Assertable Content ---

class ContentItemDto(BaseModel):
    """A raw content item extracted from source."""
    content: str = Field(description="The raw content item")
    content_type: str = Field(description="Type: claim, value, goal, constraint, decision, assumption, direct")


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
        description="If compound, decomposed atomic theses. If atomic, single item."
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
    domain: str = Field(default="General", description="For systemic: General, Engineering, Ecology, Institutions, Love")
    branch: str = Field(description="Branch/Element name")
    leaf: str = Field(description="T concept from taxonomy")
    reasoning: str = Field(description="Brief explanation")


class ExtractTheses(BaseTool, HasBrain, SettingsAware):
    """
    Extract thesis concepts following polarity-finder Phase 1 algorithm.

    Handles both direct thesis and content extraction with the same workflow:
    - Short input ("Love") → treated as direct thesis
    - Long input → extract multiple theses from content

    Returns list of committed component hashes. Does NOT create Ideas node.
    """

    text: str = Field(description="Source content to extract from, OR direct thesis statement")
    count: int = Field(default=3, description="Maximum number of theses to extract (1-4)")
    focus: str = Field(default="", description="Filter for extraction: 'security', 'design decisions', etc.")
    domain_hint: str = Field(default="", description="Taxonomy domain hint: 'Engineering', 'Love', etc.")
    not_like_these: list[str] = Field(default_factory=list, description="Existing statements to avoid")

    # --- STEP 1: Extract Assertable Content ---

    @prompt_template(
        """
        USER:
        <source_text>
        {text}
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

        Extract up to {count} most important content items.
        If the input is very short (1-5 words), treat it as a single direct thesis.

        {rule_out}
        """
    )
    def _step1_prompt(self) -> Messages.Type:
        focus_guidance = f"Focus on: {self.focus}" if self.focus else ""
        rule_out = ""
        if self.not_like_these:
            rule_out = "Avoid items similar to:\n- " + "\n- ".join(self.not_like_these)

        return {
            "computed_fields": {
                "text": self.text,
                "count": min(self.count, 4) + 2,  # Extract more, filter later
                "focus_guidance": focus_guidance,
                "rule_out": rule_out,
            }
        }

    async def _step1_extract_content(self) -> list[ContentItemDto]:
        """STEP 1: Extract assertable content from source."""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=ExtractedContentDto)
        async def _extract():
            return self._step1_prompt()

        result = await _extract()
        return result.items

    # --- STEP 2: Thesis Candidate Identification ---

    @prompt_template(
        """
        USER:
        STEP 2: Thesis Candidate Identification

        Content item: "{content}"
        Type: {content_type}

        Check if this is a valid thesis candidate:
        1. Is it ASSERTABLE? (Can be evaluated as true/false, good/bad, present/absent)
        2. Is it SUBSTANTIVE? (Not trivial or tautological)
        3. Is it ATOMIC? (Single concept, not compound)

        If compound (multiple concepts joined), decompose into atomic theses.
        Each atomic thesis should be 1-{component_length} words.

        Return:
        - is_assertable: true/false
        - is_substantive: true/false
        - is_atomic: true/false
        - atomic_theses: list of atomic thesis statements
        """
    )
    def _step2_prompt(self, content: str, content_type: str) -> Messages.Type:
        return {
            "computed_fields": {
                "content": content,
                "content_type": content_type,
                "component_length": self.settings.component_length,
            }
        }

    async def _step2_identify_candidates(self, item: ContentItemDto) -> list[str]:
        """STEP 2: Check if content is thesis candidate, decompose if compound."""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=CandidateCheckDto)
        async def _check():
            return self._step2_prompt(item.content, item.content_type)

        result = await _check()

        if not result.is_assertable or not result.is_substantive:
            return []

        return result.atomic_theses

    # --- STEP 3: Thesis Classification ---

    @prompt_template(
        """
        USER:
        STEP 3: Thesis Classification

        Thesis: "{thesis}"

        Classify this thesis:

        **SIMPLE/BINARY** - Answer: is_simple = true
        - Can be directly true/false, yes/no, present/absent
        - Has literal, binary nature
        - Examples: "The sky is blue", "Water boils at 100C", "API is stateless"

        **COMPLEX/SYSTEMIC** - Answer: is_simple = false
        - Involves relationships, processes, or functional roles
        - Concerns viability, health, or functioning of systems
        - Has trade-offs, tensions, or dynamic aspects
        - Examples: "Trust", "Data consistency", "Love", "User experience"

        Heuristic: If T involves relationship, process, or functional role → Complex
        """
    )
    def _step3_prompt(self, thesis: str) -> Messages.Type:
        return {
            "computed_fields": {
                "thesis": thesis,
            }
        }

    async def _step3_classify(self, thesis: str) -> tuple[bool, str]:
        """STEP 3: Classify thesis as Simple (True) or Complex (False)."""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=ClassificationDto)
        async def _classify():
            return self._step3_prompt(thesis)

        result = await _classify()
        return result.is_simple, result.reasoning

    # --- STEP 4: Taxonomy Location (for Complex theses) ---

    # TODO: these aren't entiredly correct taxonomies, we need to improve
    @prompt_template(
        """
        USER:
        STEP 4: Locate this COMPLEX thesis in the taxonomy.

        Thesis: "{thesis}"
        {domain_context}

        ## SYSTEMIC TAXONOMY

        | Branch | Question | General | Engineering | Ecology | Institutions | Love |
        |--------|----------|---------|-------------|---------|--------------|------|
        | Integrity | "Can it hold together?" | Cohesion | assembly | Symbiosis | Soc. cohesion | Bonding |
        | Fidelity | "Can it process accurately?" | Modeling | simulation | Sensing | knowledge | Understanding |
        | Exchange | "Can it exchange sustainably?" | Exchange | energy flow | Cyclicity | economy | Giving |
        | Flexibility | "Can it adapt?" | Exploration | control | plasticity | innovation | Openness |
        | Resilience | "Can it recover?" | Recovery | tolerance | resilience | crisis recovery | Repair |

        ## ELEMENTAL TAXONOMY (alternative)

        | Element | Question | General T |
        |---------|----------|-----------|
        | Fire | "What energizes it?" | Activation |
        | Earth | "What holds it together?" | Cohesion |
        | Air | "How does it flow?" | Exchange |
        | Water | "How does it adapt?" | Reflection |

        Return:
        - taxonomy_type: "systemic" or "elemental"
        - domain: For systemic only (General, Engineering, Ecology, Institutions, Love)
        - branch: Branch or Element name
        - leaf: The T concept from the table
        - reasoning: Brief explanation
        """
    )
    def _step4_prompt(self, thesis: str) -> Messages.Type:
        domain_context = f"Domain hint: {self.domain_hint}" if self.domain_hint else ""
        return {
            "computed_fields": {
                "thesis": thesis,
                "domain_context": domain_context,
            }
        }

    async def _step4_locate_in_taxonomy(self, thesis: str) -> TaxonomyLocationDto:
        """STEP 4: Locate complex thesis in taxonomy."""
        @with_langfuse()
        @use_brain(brain=self.brain, response_model=TaxonomyLocationDto)
        async def _locate():
            return self._step4_prompt(thesis)

        return await _locate()

    # --- Build Meaning URI ---

    def _build_meaning_uri(self, is_simple: bool, location: TaxonomyLocationDto | None) -> str:
        """Build meaning URI from classification and taxonomy location."""
        if is_simple:
            return "dx://taxonomy/Simple"

        if not location:
            return "dx://taxonomy/System(General.v1)/Viability/Fidelity/Modeling"

        # Normalize
        taxonomy_type = location.taxonomy_type.lower().strip()
        domain = location.domain.strip().title() if location.domain else "General"
        branch = location.branch.strip().title() if location.branch else "Fidelity"
        leaf = location.leaf.strip().title().replace(" ", "") if location.leaf else branch

        valid_domains = ["General", "Engineering", "Ecology", "Institutions", "Love"]
        if domain not in valid_domains:
            domain = "General"

        if taxonomy_type == "elemental":
            valid_elements = ["Fire", "Earth", "Air", "Water"]
            if branch not in valid_elements:
                branch = "Earth"
            return f"dx://taxonomy/Elemental/Viability/{branch}/{leaf}"
        else:
            valid_branches = ["Integrity", "Fidelity", "Exchange", "Flexibility", "Resilience"]
            if branch not in valid_branches:
                branch = "Fidelity"
            return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{leaf}"

    # --- Main Flow ---

    async def call(self) -> str:
        """
        Execute the step-by-step thesis extraction algorithm.

        Returns list of component hashes. Does NOT create Ideas node.
        """
        results = []
        component_hashes = []

        # STEP 1: Extract assertable content
        content_items = await self._step1_extract_content()
        results.append(f"STEP 1: Extracted {len(content_items)} content items")

        # STEP 2: Identify thesis candidates
        all_candidates: list[str] = []
        for item in content_items:
            candidates = await self._step2_identify_candidates(item)
            all_candidates.extend(candidates)

        # Deduplicate
        all_candidates = list(dict.fromkeys(all_candidates))
        results.append(f"STEP 2: Identified {len(all_candidates)} thesis candidates")

        if not all_candidates:
            return "\n".join(results) + "\nNo thesis candidates found."

        # Limit to requested count
        candidates_to_process = all_candidates[:min(self.count, 4)]

        # STEP 3 & 4: Classify and anchor each candidate
        for thesis in candidates_to_process:
            # STEP 3: Classify
            is_simple, classification_reasoning = await self._step3_classify(thesis)
            classification = "SIMPLE" if is_simple else "COMPLEX"

            # STEP 4: Locate in taxonomy (if complex)
            location = None
            if not is_simple:
                location = await self._step4_locate_in_taxonomy(thesis)

            # Build meaning URI
            meaning = self._build_meaning_uri(is_simple, location)

            # Create and commit component
            component = DialecticalComponent(statement=thesis, meaning=meaning)
            component.commit()

            # Add rationale
            rationale_text = f"Classification: {classification}. {classification_reasoning}"
            if location:
                rationale_text += f" Taxonomy: {location.taxonomy_type}/{location.branch}/{location.leaf}. {location.reasoning}"
            rationale = Rationale(text=rationale_text)
            rationale.set_explanation(component)
            rationale.commit()

            component_hashes.append(component.short_hash)
            results.append(f"  [{component.short_hash}] {thesis} → {classification} → {meaning}")

        results.insert(2, f"STEP 3-4: Classified and anchored {len(component_hashes)} theses:")
        results.append(f"\nNew DialecticalComponent hashes in the graph: {', '.join(component_hashes)}")

        return "\n".join(results)
