"""
StatementClassification: Capability for classifying dialectical statements.

Provides:
1. LLM-based classification (execute) - for new statements needing full classification
2. Static lookup methods - for deriving meaning from parent (no LLM needed)

Usage:
    # Full classification (LLM)
    classifier = StatementClassification()
    result = await classifier.execute(statement="Trust", text="software architecture...")

    # Lookup antithesis meaning (deterministic, no LLM)
    meaning = StatementClassification.lookup_antithesis_meaning(thesis)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


# --- Taxonomy Constants ---

# Systemic taxonomy mapping for T→A lookup (thesis branch → antithesis leaf)
SYSTEMIC_TAXONOMY = {
    "Integrity": {"thesis_leaf": "Integration", "antithesis_leaf": "Disintegration"},
    "Fidelity": {"thesis_leaf": "Modeling", "antithesis_leaf": "ErrorCorrection"},
    "Exchange": {"thesis_leaf": "Exchange", "antithesis_leaf": "Consumption"},
    "Flexibility": {"thesis_leaf": "Exploration", "antithesis_leaf": "Exploitation"},
    "Resilience": {"thesis_leaf": "Recovery", "antithesis_leaf": "Disruption"},
}

VALID_DOMAINS = ["General", "Engineering", "Ecology", "Institutions", "Love"]
VALID_BRANCHES = ["Integrity", "Fidelity", "Exchange", "Flexibility", "Resilience"]
VALID_ELEMENTS = ["Fire", "Earth", "Air", "Water"]


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical statement classifier.

Your task is to classify statements and anchor them in taxonomy.

## Statement Classification

**SIMPLE/BINARY** - is_simple = true
- Can be directly true/false, yes/no, present/absent
- Has literal, binary nature
- Examples: "The sky is blue", "Water boils at 100C", "API is stateless"

**COMPLEX/SYSTEMIC** - is_simple = false
- Involves relationships, processes, or functional roles
- Concerns viability, health, or functioning of systems
- Has trade-offs, tensions, or dynamic aspects
- Examples: "Trust", "Data consistency", "Love", "User experience"

Heuristic: If statement involves relationship, process, or functional role → Complex

## Taxonomy for Complex Statements

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

**IMPORTANT**: Use the provided text to determine the appropriate domain.
For example, "Trust" in a software text → Engineering domain.
"Trust" in a relationship text → Love domain.

Respond with structured output matching the requested format."""


# --- DTOs ---


class ClassificationDto(BaseModel):
    """Result of classifying a statement."""

    is_simple: bool = Field(description="True=Simple/Binary, False=Complex/Systemic")
    reasoning: str = Field(description="Brief explanation")


class TaxonomyLocationDto(BaseModel):
    """Result of locating statement in taxonomy."""

    taxonomy_type: str = Field(description="'systemic' or 'elemental'")
    domain: str = Field(
        default="General",
        description="For systemic: General, Engineering, Ecology, Institutions, Love",
    )
    branch: str = Field(description="Branch/Element name")
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


# --- Capability ---


class StatementClassification(ExecutableCapability[ClassificationResult]):
    """
    Capability for classifying dialectical statements (thesis or antithesis).

    Provides:
    1. execute() - LLM-based classification for new statements
    2. Static lookup methods - deterministic meaning derivation from parent

    Does NOT create any database nodes - caller decides what to do with result.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    # --- Static Lookup Methods (no LLM) ---

    @staticmethod
    def lookup_antithesis_meaning(thesis: DialecticalComponent) -> str:
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

        # Parse thesis meaning and derive antithesis
        for branch, mapping in SYSTEMIC_TAXONOMY.items():
            if f"/{branch}/" in thesis_meaning:
                # Extract domain from thesis meaning
                domain = "General"
                if "System(" in thesis_meaning:
                    start = thesis_meaning.find("System(") + 7
                    end = thesis_meaning.find(".v1)")
                    if end > start:
                        domain = thesis_meaning[start:end]

                return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{mapping['antithesis_leaf']}"

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
            leaf = SYSTEMIC_TAXONOMY.get(branch, {}).get("thesis_leaf", branch)

        return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{leaf}"

    # --- LLM-based Classification ---

    async def execute(
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
        self._report = ExecutionReport(tool=self.__class__.__name__)
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
- SIMPLE/BINARY (is_simple = true): literal, binary nature
- COMPLEX/SYSTEMIC (is_simple = false): involves relationships, processes, functional roles

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
- taxonomy_type: "systemic" or "elemental"
- domain: For systemic only (General, Engineering, Ecology, Institutions, Love)
- branch: Branch or Element name
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
            return f"dx://taxonomy/Elemental/Viability/{branch}/{leaf}"
        else:
            if branch not in VALID_BRANCHES:
                branch = "Fidelity"
            return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{leaf}"
