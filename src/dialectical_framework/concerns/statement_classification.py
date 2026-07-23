"""
StatementClassification: Concern for classifying dialectical statements.

Provides:
1. LLM-based classification (resolve) - for new statements needing full classification
2. Static lookup methods - for deriving meaning from parent (no LLM needed)

Usage:
    # Full classification (LLM)
    classifier = StatementClassification()
    result = await classifier.resolve(statement="Trust", text="software architecture...")

    # Lookup antithesis meaning (deterministic, no LLM)
    meaning = StatementClassification.lookup_antithesis_meaning(thesis)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.perspective import (POSITION_A,
                                                          POSITION_A_MINUS,
                                                          POSITION_A_PLUS,
                                                          POSITION_T,
                                                          POSITION_T_MINUS,
                                                          POSITION_T_PLUS)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import \
        Statement


# --- Taxonomy Constants ---

# Systemic taxonomy mapping from Table S-1
# Structure: branch -> {POSITION_T: apex, POSITION_A: apex, POSITION_T_PLUS: apex, ...}
SYSTEMIC_TAXONOMY = {
    "Apex": {
        POSITION_T: "Integration",
        POSITION_A: "Disintegration",
        POSITION_T_PLUS: "Coherence",
        POSITION_T_MINUS: "Rigid fusion",
        POSITION_A_PLUS: "Differentiation",
        POSITION_A_MINUS: "Disintegration",
    },
    "Integrity": {
        POSITION_T: "Cohesion",
        POSITION_A: "Separation",
        POSITION_T_PLUS: "Coherence",
        POSITION_T_MINUS: "Locking-in",
        POSITION_A_PLUS: "Differentiation",
        POSITION_A_MINUS: "Rupture",
    },
    "Fidelity": {
        POSITION_T: "Modeling",
        POSITION_A: "Error correction",
        POSITION_T_PLUS: "Accuracy",
        POSITION_T_MINUS: "Dogmatism",
        POSITION_A_PLUS: "Critical testing",
        POSITION_A_MINUS: "Denial",
    },
    "Exchange": {
        POSITION_T: "Exchange",
        POSITION_A: "Consumption",
        POSITION_T_PLUS: "Exchange",
        POSITION_T_MINUS: "Dependency",
        POSITION_A_PLUS: "Constraint",
        POSITION_A_MINUS: "Depletion",
    },
    "Flexibility": {
        POSITION_T: "Exploration",
        POSITION_A: "Constraint",
        POSITION_T_PLUS: "Plasticity",
        POSITION_T_MINUS: "Chaotic drift",
        POSITION_A_PLUS: "Stabilization",
        POSITION_A_MINUS: "Suffocating",
    },
    "Resilience": {
        POSITION_T: "Recovery",
        POSITION_A: "Disruption",
        POSITION_T_PLUS: "Recovery",
        POSITION_T_MINUS: "Fragility",
        POSITION_A_PLUS: "Buffering",
        POSITION_A_MINUS: "Collapse",
    },
}

# Elemental taxonomy mapping from Table S-2 (four classical elements + Apex).
# A peer taxonomy to SYSTEMIC_TAXONOMY, NOT a validation lens: it carves a
# different set of distinctions (notably Fire/Drive — energy/motivation — which
# has no systemic home). Table S-2 carries no K_T/K_A/HS numbers; systemic
# remains the only numerically-grounded table. Runtime HS is LLM-computed
# against the apex concept name, so elemental lookups work without them.
# The Apex column is identical to the systemic Apex (same Viability apex).
ELEMENTAL_TAXONOMY = {
    "Apex": {
        POSITION_T: "Integration",
        POSITION_A: "Disintegration",
        POSITION_T_PLUS: "Coherence",
        POSITION_T_MINUS: "Rigid fusion",
        POSITION_A_PLUS: "Differentiation",
        POSITION_A_MINUS: "Disintegration",
    },
    "Fire": {  # Drive: "What energizes it?"
        POSITION_T: "Activation",
        POSITION_A: "Inhibition",
        POSITION_T_PLUS: "Motivation",
        POSITION_T_MINUS: "Impulsivity",
        POSITION_A_PLUS: "Regulation",
        POSITION_A_MINUS: "Repression",
    },
    "Earth": {  # Structure: "What holds it together?"
        POSITION_T: "Cohesion",
        POSITION_A: "Separation",
        POSITION_T_PLUS: "Coherence",
        POSITION_T_MINUS: "Locking-in",
        POSITION_A_PLUS: "Differentiation",
        POSITION_A_MINUS: "Rupture",
    },
    "Air": {  # Process: "How does it flow?"
        POSITION_T: "Exchange",
        POSITION_A: "Consumption",
        POSITION_T_PLUS: "Exchange",
        POSITION_T_MINUS: "Dependency",
        POSITION_A_PLUS: "Constraint",
        POSITION_A_MINUS: "Depletion",
    },
    "Water": {  # Adaptation: "How does it adapt?"
        POSITION_T: "Reflection",
        POSITION_A: "Correction",
        POSITION_T_PLUS: "Plasticity",
        POSITION_T_MINUS: "Fragility",
        POSITION_A_PLUS: "Stabilization",
        POSITION_A_MINUS: "Collapse",
    },
}

VALID_DOMAINS = ["General", "Engineering", "Ecology", "Institutions", "Love"]
VALID_BRANCHES = [
    "Apex",
    "Integrity",
    "Fidelity",
    "Exchange",
    "Flexibility",
    "Resilience",
]
VALID_ELEMENTS = ["Fire", "Earth", "Air", "Water"]
VALID_ELEMENTAL_BRANCHES = ["Apex", "Fire", "Earth", "Air", "Water"]  # Apex is a valid elemental branch too
VALID_ASPECT_POSITIONS = [
    POSITION_T_PLUS,
    POSITION_T_MINUS,
    POSITION_A_PLUS,
    POSITION_A_MINUS,
]

# Taxonomy URI family tokens. A meaning URI is
# dx://taxonomy/{Family}({domain}.v1)/Viability/{branch}/{leaf}. The family
# token selects which taxonomy vocabulary applies; the parsing/lookup algorithm
# is taxonomy-agnostic. Adding a taxonomy = add its dict + one registry line.
SYSTEMIC_PREFIX = "dx://taxonomy/System("
ELEMENTAL_PREFIX = "dx://taxonomy/Elements("
VIABILITY_CATEGORY = "Viability"

# Registry mapping URI family token -> taxonomy dict.
TAXONOMY_BY_FAMILY = {
    "System": SYSTEMIC_TAXONOMY,
    "Elements": ELEMENTAL_TAXONOMY,
}


def _family_for_meaning(meaning: Optional[str]) -> str:
    """Resolve the URI family token for a meaning (defaults to 'System')."""
    if meaning:
        for family in TAXONOMY_BY_FAMILY:
            if f"/{family}(" in meaning:
                return family
    return "System"


def _taxonomy_for_meaning(meaning: Optional[str]) -> dict:
    """Resolve which taxonomy dict a meaning URI belongs to (defaults to systemic).

    Dispatches on the URI family token (System, Elements, ...). Systemic is the
    default and the only numerically-grounded table.
    """
    return TAXONOMY_BY_FAMILY[_family_for_meaning(meaning)]


def parse_meaning_uri(
    meaning: str,
) -> tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """
    Parse a meaning URI to extract domain, category, branch, and leaf.

    Format:    dx://taxonomy/{Family}({domain}.v1)/{category}/{branch}/{leaf}
    Systemic:  dx://taxonomy/System(General.v1)/Viability/Integrity/Cohesion
    Elements:  dx://taxonomy/Elements(General.v1)/Viability/Fire/Activation

    Where:
    - domain: General, Engineering, Ecology, Institutions, Love
    - category: Viability (parent of all branches)
    - branch: systemic (Apex, Integrity, Fidelity, Exchange, Flexibility,
      Resilience) or elemental (Apex, Fire, Earth, Air, Water)
    - leaf: specific concept (Cohesion, Activation, etc.)

    The algorithm is taxonomy-agnostic; use _taxonomy_for_meaning(meaning) to
    resolve which taxonomy dict the returned branch belongs to.

    Args:
        meaning: The meaning URI to parse

    Returns:
        Tuple of (domain, category, branch, leaf) - any may be None if not found
    """
    if not meaning:
        return None, None, None, None

    domain = None
    category = None
    branch = None
    leaf = None

    # Extract domain from {Family}({domain}.v1) if present — family-agnostic.
    if ".v1)" in meaning:
        open_paren = meaning.find("(")
        dot_v1 = meaning.find(".v1)")
        if 0 <= open_paren < dot_v1:
            domain = meaning[open_paren + 1 : dot_v1]

    # Split URI into path segments
    # Remove protocol prefix for parsing
    path_part = meaning
    if "://" in meaning:
        path_part = meaning.split("://", 1)[1]

    segments = [s for s in path_part.split("/") if s]

    # Find category and branch by looking for Viability followed by a valid
    # branch from either taxonomy (systemic or elemental).
    valid_branches = set(VALID_BRANCHES) | set(VALID_ELEMENTAL_BRANCHES)
    for i, segment in enumerate(segments):
        if segment == VIABILITY_CATEGORY:
            category = segment
            # Next segment should be the branch
            if i + 1 < len(segments) and segments[i + 1] in valid_branches:
                branch = segments[i + 1]
                # Leaf is the segment after branch
                if i + 2 < len(segments):
                    leaf = segments[i + 2]
            break

    return domain, category, branch, leaf


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical statement classifier.

Your task is to classify statements and anchor them in taxonomy.

## Statement Classification

**SIMPLE/BINARY** - is_simple = true
- Verifiable by direct observation or logical identity
- No trade-offs, no systemic dynamics, no causal chains
- Examples: "The sky is blue", "Water boils at 100C", "API is stateless", "The repository has 3 branches"

**COMPLEX** - is_simple = false
- Involves causal dynamics, trade-offs, or systemic relationships
- Describes how one thing affects another, or how a process shapes outcomes
- Concerns viability, health, functioning, or governance of systems
- Examples: "Trust", "Data consistency", "Open markets promote innovation", "Centralization enables coordination", "Distributed systems trade consistency for availability"

Heuristic: If the statement describes a causal relationship (X causes/enables/prevents Y), a trade-off, or a systemic dynamic → Complex. If it is a bare fact verifiable by inspection → Simple.

## Taxonomy for Complex Statements

Every complex statement is anchored in ONE of two peer taxonomies. Choose the
taxonomy first, then locate the thesis concept (leaf) within it.

**Choosing the taxonomy:**
- **systemic** (default) — the thesis is best understood by which viability
  capacity of a system it serves. Fits engineering, institutional, ecological,
  informational, and governance concepts. Use this unless the elemental test
  below clearly fits.
- **elemental** — the thesis is fundamentally about drive, energy, motivation,
  or activation (systemic has no home for this — it maps to Fire), OR it is a
  broad cross-domain, psychological, or natural concept where the functional-
  capacity question feels forced and the Drive/Structure/Process/Adaptation
  frame fits better.

### SYSTEMIC TAXONOMY

| Branch | Question | General | Engineering | Ecology | Institutions | Love |
|--------|----------|---------|-------------|---------|--------------|------|
| Integrity | "Can it hold together?" | Cohesion | assembly | Symbiosis | Soc. cohesion | Bonding |
| Fidelity | "Can it process accurately?" | Modeling | simulation | Sensing | knowledge | Understanding |
| Exchange | "Can it exchange sustainably?" | Exchange | energy flow | Cyclicity | economy | Giving |
| Flexibility | "Can it adapt?" | Exploration | control | plasticity | innovation | Openness |
| Resilience | "Can it recover?" | Recovery | tolerance | resilience | crisis recovery | Repair |

### ELEMENTAL TAXONOMY

| Element | Question | General T |
|---------|----------|-----------|
| Fire | "What energizes/drives it?" | Activation |
| Earth | "What holds it together?" | Cohesion |
| Air | "How does it flow/exchange?" | Exchange |
| Water | "How does it adapt/correct?" | Reflection |

For systemic, use the provided text to determine the appropriate domain.
For example, "Trust" in a software text → Engineering domain.
"Trust" in a relationship text → Love domain.

Respond with structured output matching the requested format."""


# --- DTOs ---


class ClassificationDto(BaseModel):
    """Result of classifying a statement."""

    is_simple: bool = Field(description="True=Simple/Binary, False=Complex")
    reasoning: str = Field(description="Brief explanation")


class TaxonomyLocationDto(BaseModel):
    """Result of locating statement in taxonomy."""

    taxonomy_type: str = Field(
        description="'systemic' (default) or 'elemental' (drive/energy/activation, or broad cross-domain/psychological concepts)"
    )
    domain: str = Field(
        default="General",
        description="For systemic: General, Engineering, Ecology, Institutions, Love",
    )
    branch: str = Field(
        description="Systemic branch (Integrity/Fidelity/Exchange/Flexibility/Resilience) or element (Fire/Earth/Air/Water)"
    )
    leaf: str = Field(description="T concept from taxonomy")
    reasoning: str = Field(description="Brief explanation")


# --- Result ---


@dataclass
class ClassificationResult:
    """Result of statement classification."""

    statement: str
    is_simple: bool
    meaning: str
    classification_reasoning: str
    taxonomy_reasoning: Optional[str] = None


# --- Concern ---


class StatementClassification(ReasonableConcern[ClassificationResult]):
    """
    Concern for classifying dialectical statements (thesis or antithesis).

    Provides:
    1. resolve() - LLM-based classification for new statements
    2. Static lookup methods - deterministic meaning derivation from parent

    Does NOT create any database nodes - caller decides what to do with result.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    # --- Static Lookup Methods (no LLM) ---

    @staticmethod
    def lookup_antithesis_meaning(thesis: Statement) -> str:
        """
        Derive antithesis meaning from thesis - deterministic, no LLM needed.

        For simple thesis: returns dx://taxonomy/Simple
        For complex thesis: derives from thesis meaning (same branch, antithesis leaf)

        Args:
            thesis: The thesis component

        Returns:
            Meaning URI for the antithesis
        """
        if thesis.is_simple:
            return "dx://taxonomy/Simple"

        thesis_meaning = thesis.meaning
        if not thesis_meaning:
            return "dx://taxonomy/System(General.v1)/Viability/Fidelity/ErrorCorrection"

        # Parse thesis meaning URI properly, staying within its taxonomy family
        family = _family_for_meaning(thesis_meaning)
        taxonomy = TAXONOMY_BY_FAMILY[family]
        domain, category, branch, _ = parse_meaning_uri(thesis_meaning)

        if branch and branch in taxonomy:
            domain = domain or "General"
            category = category or VIABILITY_CATEGORY
            antithesis_leaf = taxonomy[branch][POSITION_A]
            return f"dx://taxonomy/{family}({domain}.v1)/{category}/{branch}/{antithesis_leaf}"

        # Fallback
        return "dx://taxonomy/System(General.v1)/Viability/Fidelity/ErrorCorrection"

    @staticmethod
    def lookup_thesis_meaning(
        branch: str,
        domain: str = "General",
        leaf: Optional[str] = None,
    ) -> str:
        """
        Build thesis meaning URI for a given branch/domain - deterministic, no LLM needed.

        Args:
            branch: Taxonomy branch (Integrity, Fidelity, Exchange, Flexibility, Resilience)
            domain: Domain (General, Engineering, Ecology, Institutions, Love)
            leaf: Optional leaf concept (defaults to branch's thesis_leaf)

        Returns:
            Meaning URI for the thesis
        """
        # Normalize and validate
        branch = branch.strip().title()
        domain = domain.strip().title()

        if branch not in VALID_BRANCHES:
            branch = "Fidelity"
        if domain not in VALID_DOMAINS:
            domain = "General"

        if leaf is None:
            leaf = SYSTEMIC_TAXONOMY.get(branch, {}).get(POSITION_T, branch)

        return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{leaf}"

    @staticmethod
    def lookup_aspect_meaning(
        parent: Statement,
        position: str,
    ) -> str:
        """
        Derive aspect meaning from parent component - deterministic, no LLM needed.

        For T+/T-: parent should be the thesis (T)
        For A+/A-: parent should be the antithesis (A)

        Args:
            parent: The parent component (T for T+/T-, A for A+/A-)
            position: Aspect position ("T+", "T-", "A+", "A-")

        Returns:
            Meaning URI for the aspect
        """
        if position not in VALID_ASPECT_POSITIONS:
            raise ValueError(
                f"Invalid position '{position}'. Must be one of: {VALID_ASPECT_POSITIONS}"
            )

        if parent.is_simple:
            return "dx://taxonomy/Simple"

        parent_meaning = parent.meaning
        if not parent_meaning:
            # Fallback to apex-level aspects
            leaf = SYSTEMIC_TAXONOMY["Apex"][position]
            return f"dx://taxonomy/System(General.v1)/Viability/Apex/{leaf}"

        # Parse parent meaning URI properly, staying within its taxonomy family
        family = _family_for_meaning(parent_meaning)
        taxonomy = TAXONOMY_BY_FAMILY[family]
        domain, category, branch, _ = parse_meaning_uri(parent_meaning)
        domain = domain or "General"
        category = category or VIABILITY_CATEGORY

        # Get aspect leaf from taxonomy using position directly as key
        if branch and branch in taxonomy:
            leaf = taxonomy[branch][position]
        else:
            # Use apex-level aspects
            leaf = taxonomy["Apex"][position]
            branch = "Apex"

        return f"dx://taxonomy/{family}({domain}.v1)/{category}/{branch}/{leaf}"

    @staticmethod
    def lookup_aspect_apex(
        parent: Statement,
        position: str,
    ) -> str:
        """
        Get the apex concept name for an aspect position - for HS calculation.

        This returns the generic apex concept (e.g., "Coherence" for T+ in Integrity branch)
        that serves as the reference for heuristic similarity scoring.

        Args:
            parent: The parent component (T for T+/T-, A for A+/A-)
            position: Aspect position (POSITION_T_PLUS, POSITION_T_MINUS, etc.)

        Returns:
            Apex concept name (e.g., "Coherence", "Differentiation")
        """
        if position not in VALID_ASPECT_POSITIONS:
            raise ValueError(
                f"Invalid position '{position}'. Must be one of: {VALID_ASPECT_POSITIONS}"
            )

        if parent.is_simple:
            return "Simple"

        parent_meaning = parent.meaning or ""

        # Parse parent meaning URI properly, staying within its taxonomy family
        taxonomy = _taxonomy_for_meaning(parent_meaning)
        _, _, branch, _ = parse_meaning_uri(parent_meaning)

        # Get aspect apex from taxonomy using position directly as key
        if branch and branch in taxonomy:
            return taxonomy[branch][position]
        else:
            return taxonomy["Apex"][position]

    @staticmethod
    def get_contradiction_pair(position: str) -> str:
        """
        Get the contradiction counterpart for an aspect position.

        T+ contradicts A-, A+ contradicts T-.

        Args:
            position: Aspect position ("T+", "T-", "A+", "A-")

        Returns:
            The contradicting aspect position
        """
        contradiction_map = {
            POSITION_T_PLUS: POSITION_A_MINUS,
            POSITION_A_MINUS: POSITION_T_PLUS,
            POSITION_A_PLUS: POSITION_T_MINUS,
            POSITION_T_MINUS: POSITION_A_PLUS,
        }
        if position not in contradiction_map:
            raise ValueError(
                f"Invalid position '{position}'. Must be one of: {VALID_ASPECT_POSITIONS}"
            )
        return contradiction_map[position]

    # --- LLM-based Classification ---

    async def resolve(
        self,
        statement: str,
        text: str = "",
        domain_hint: str = "",
    ) -> ClassificationResult:
        """
        Classify a statement using LLM.

        Args:
            statement: The statement to classify
            text: Source text to inform classification (e.g., article text)
            domain_hint: Optional explicit domain hint (e.g., 'Engineering', 'Love')

        Returns:
            ClassificationResult with is_simple, meaning URI, and reasoning
        """
        self._statement = statement.strip() if statement else ""

        # Early validation
        if not self._statement:
            raise ValueError("Cannot classify empty statement")

        self._text = text
        self._domain_hint = domain_hint

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Classify and locate in taxonomy
        classification, location = await self._classify_and_locate()

        # Build meaning URI
        meaning = self._build_meaning_uri(classification.is_simple, location)

        self._report.ok = True
        self._report.summary = f"Classified '{self._statement}' as {'Simple' if classification.is_simple else 'Complex'}"

        return ClassificationResult(
            statement=self._statement,
            is_simple=classification.is_simple,
            meaning=meaning,
            classification_reasoning=classification.reasoning,
            taxonomy_reasoning=location.reasoning if location else None,
        )

    async def _classify_and_locate(
        self,
    ) -> tuple[ClassificationDto, Optional[TaxonomyLocationDto]]:
        """Classify statement and locate in taxonomy if complex."""
        classification = await self._conversation.submit(
            response_model=ClassificationDto,
            user_content=self._classification_prompt(),
        )

        location: Optional[TaxonomyLocationDto] = None
        if not classification.is_simple:
            location = await self._conversation.submit(
                response_model=TaxonomyLocationDto,
                user_content=self._taxonomy_prompt(),
            )

        return classification, location

    def _classification_prompt(self) -> str:
        """Build prompt for classification."""
        text_section = ""
        if self._text:
            text_section = f"""
**Source Context:**
{self._text[:2000]}{"..." if len(self._text) > 2000 else ""}

Use this text to understand the intended meaning of the statement.
"""

        return f"""Classify this statement:

Statement: "{self._statement}"
{text_section}
Using the classification criteria from the system prompt, classify as:
- SIMPLE/BINARY (is_simple = true): verifiable by direct observation, no causal dynamics
- COMPLEX (is_simple = false): describes causal relationships, trade-offs, or systemic dynamics

A statement like "X prevents/enables/eliminates Y" describes a causal dynamic and is COMPLEX, even if one could argue the causal claim is "either true or false." The test is whether the statement embeds a systemic relationship, not whether one can assign it a truth value.

Provide your reasoning."""

    def _taxonomy_prompt(self) -> str:
        """Build prompt for taxonomy location."""
        text_section = ""
        if self._text:
            text_section = f"""
**Source Context:**
{self._text[:2000]}{"..." if len(self._text) > 2000 else ""}

Use this text to determine the appropriate domain.
"""

        domain_hint_section = ""
        if self._domain_hint:
            domain_hint_section = f"\nDomain hint: {self._domain_hint}"

        return f"""Locate this COMPLEX statement in the taxonomy.

Statement: "{self._statement}"
{text_section}{domain_hint_section}
Using the taxonomy tables from the system prompt, determine:
- taxonomy_type: "systemic" (default) or "elemental". Choose elemental only when the thesis is fundamentally about drive/energy/motivation/activation, or is a broad cross-domain/psychological concept where the systemic capacity question feels forced.
- domain: For systemic only (General, Engineering, Ecology, Institutions, Love)
- branch: Systemic branch (Integrity/Fidelity/Exchange/Flexibility/Resilience) or element (Fire/Earth/Air/Water)
- leaf: The T concept from the table
- reasoning: Brief explanation"""

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

        if domain not in VALID_DOMAINS:
            domain = "General"

        if taxonomy_type == "elemental":
            if branch not in VALID_ELEMENTS:
                branch = "Earth"
            # Elemental vocabulary is domain-generic (General); the family token
            # keeps the URI structurally uniform with systemic for future domains.
            return f"dx://taxonomy/Elements(General.v1)/Viability/{branch}/{leaf}"
        else:
            if branch not in VALID_BRANCHES:
                branch = "Fidelity"
            return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{leaf}"
