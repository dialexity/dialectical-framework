"""
ExtractAntitheses: Work tool for generating antitheses for a SINGLE thesis.

Uses conversational pattern: all steps share context through conversation history,
enabling prompt caching. Composite DTO reduces 33 calls to 12 calls.

This is the Phase 2 work tool, symmetric to ExtractTheses (Phase 1).
- ExtractTheses: handles thesis extraction for one text/content
- ExtractAntitheses: handles antithesis generation for one thesis

Does NOT create Ideas node - that's the orchestrator's job (PolarityFindingAgent).
Returns component hashes + HS values for the orchestrator to use.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from mirascope import Messages

from dialectical_framework.agents.conversational_tool import ConversationalTool
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.estimation import ArousalEstimation, ModeEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.node_repository import NodeRepository

if TYPE_CHECKING:
    pass


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical antithesis generator using the universal antithesis taxonomy.

## Universal Antithesis Taxonomy Structure

```
                    APEX: [T]-lessness
                           │
        ┌──────────────────┴──────────────────┐
        │                                     │
   Anti-[T]                            Absence of [T]
  (Violations)                          (Inhibition)
        │                                     │
┌───────┴───────┐                     ┌───────┴───────┐
│               │                     │               │
Corruption     Deformation            Inhibition      Privation
```

## Mode Scale (interaction mechanism from absence to negation)

| Mode | Type | Description |
|------|------|-------------|
| 1.0 | Negation | Direct, active opposition to T |
| 0.9 | Inversion | Reversal of T's meaning |
| 0.8 | Devaluation | Diminishing T's worth |
| 0.7 | Hollowing | Emptying T of substance |
| 0.6 | Corruption | Degrading/perverting T |
| 0.5 | Distortion | Twisting T's form |
| 0.4 | Skew | Imbalancing T |
| 0.3 | Blocking | Obstructing T |
| 0.2 | Suppression | Holding T down |
| 0.1 | Distancing | Drifting from T |
| 0.0 | Privation | Complete absence of T |

## Arousal Scale (activation from invisible to visible)

| Arousal | Description |
|---------|-------------|
| dormant | Completely latent, invisible tension |
| latent | Barely perceptible, nascent |
| low | Mild, background tension |
| mild | Noticeable but subdued |
| moderate | Balanced, present tension |
| elevated | Becoming prominent |
| high | Strong, clearly visible |
| intense | Very active, urgent |
| active | Fully manifest, immediate |

## HS (Heuristic Similarity) Scale

HS measures how well the candidate represents the apex concept:
- 0.0-0.3: Unrelated or tangentially related
- 0.3-0.5: Somewhat related but different focus
- 0.5-0.7: Related, captures some aspects of apex
- 0.7-0.9: Very similar, captures most aspects of apex
- 0.9-1.0: Equivalent or near-equivalent to apex

Respond with structured output matching the requested format."""


# --- DTOs for LLM structured outputs ---


class ContextualizedTaxonomyDto(BaseModel):
    """Contextualized universal taxonomy for a thesis.

    Structure (from docs/r&d/taxonomy-universal.md):
                            APEX: [T]-lessness
                                   │
                ┌──────────────────┴──────────────────┐
                │                                     │
           Anti-[T]                            Absence of [T]
          (Violations)                          (Inhibition)
                │                                     │
        ┌───────┴───────┐                     ┌───────┴───────┐
        │               │                     │               │
   Corruption     Deformation            Inhibition      Privation
    """

    # Mode field -> mode value mapping (excludes apex)
    MODE_FIELDS: ClassVar[dict[str, float]] = {
        "negation": 1.0,      # Direct, active opposition to T
        "inversion": 0.9,     # Reversal of T's meaning
        "devaluation": 0.8,   # Diminishing T's worth
        "hollowing": 0.7,     # Emptying T of substance
        "corruption": 0.6,    # Degrading/perverting T
        "distortion": 0.5,    # Twisting T's form
        "skew": 0.4,          # Imbalancing T
        "blocking": 0.3,      # Obstructing T
        "suppression": 0.2,   # Holding T down
        "distancing": 0.1,    # Drifting from T
        "privation": 0.0,     # Complete absence of T
    }

    apex: str = Field(description="[T]-lessness concept (complete absence/negation)")
    # Anti-[T] branch (Mode 0.7-1.0)
    negation: str = Field(description="Mode 1.0: Direct, active opposition to T")
    inversion: str = Field(description="Mode 0.9: Reversal of T's meaning")
    devaluation: str = Field(description="Mode 0.8: Diminishing T's worth")
    hollowing: str = Field(description="Mode 0.7: Emptying T of substance")
    corruption: str = Field(description="Mode 0.6: Degrading/perverting T")
    # Deformation branch (Mode 0.4-0.5)
    distortion: str = Field(description="Mode 0.5: Twisting T's form")
    skew: str = Field(description="Mode 0.4: Imbalancing T")
    # Absence of T branch (Mode 0.0-0.3)
    blocking: str = Field(description="Mode 0.3: Obstructing T")
    suppression: str = Field(description="Mode 0.2: Holding T down")
    distancing: str = Field(description="Mode 0.1: Drifting from T")
    privation: str = Field(description="Mode 0.0: Complete absence of T")


class ModePointResultDto(BaseModel):
    """Antithesis candidate at a Mode point with HS and arousal estimation."""

    statement: str = Field(description="Antithesis candidate statement (similar length to thesis)")
    hs_value: float = Field(
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


# --- Constants ---


# Systemic taxonomy mapping for T→A lookup (thesis branch → antithesis branch)
# Format: branch_name -> {generic_t, generic_a}
SYSTEMIC_TAXONOMY = {
    "Integrity": {"generic_t": "Integration", "generic_a": "Disintegration"},
    "Fidelity": {"generic_t": "Modeling", "generic_a": "ErrorCorrection"},
    "Exchange": {"generic_t": "Exchange", "generic_a": "Consumption"},
    "Flexibility": {"generic_t": "Exploration", "generic_a": "Exploitation"},
    "Resilience": {"generic_t": "Recovery", "generic_a": "Disruption"},
}


# Arousal label to value mapping (0.1-0.9 range, passive→active)
AROUSAL_VALUES = {
    "dormant": 0.1,     # Completely latent, invisible tension
    "latent": 0.2,      # Barely perceptible, nascent
    "low": 0.3,         # Mild, background tension
    "mild": 0.4,        # Noticeable but subdued
    "moderate": 0.5,    # Balanced, present tension
    "elevated": 0.6,    # Becoming prominent
    "high": 0.7,        # Strong, clearly visible
    "intense": 0.8,     # Very active, urgent
    "active": 0.9,      # Fully manifest, immediate
}


def arousal_label_to_value(label: str) -> float:
    """Convert arousal label to value. Returns default if unknown."""
    return AROUSAL_VALUES.get(label.lower().strip(), 0.5)


# --- Antithesis Result Container ---


class AntithesisResult:
    """Container for an antithesis with its metadata."""

    def __init__(
        self,
        component: DialecticalComponent,
        mode_value: float,
        arousal_value: float,
        hs_value: float,
    ):
        self.component = component
        self.mode_value = mode_value
        self.arousal_value = arousal_value
        self.hs_value = hs_value


# --- Main Work Tool ---


class ExtractAntitheses(ConversationalTool):
    """
    Extract antitheses for a SINGLE thesis.

    Uses conversational pattern where all steps share context through
    conversation history, enabling prompt caching. Composite DTO reduces
    calls from 33 (1 + 11 × 3) to 12 (1 contextualize + 11 composite).

    This is the work tool for Phase 2 of polarity-finder.
    Handles both simple and complex theses:
    - Simple: Direct negation with HS=1.0, Mode=1.0
    - Complex: Contextualized taxonomy with candidates at key Mode points

    Does NOT create Ideas node. Returns report with hashes and HS values.
    PolarityFindingAgent (orchestrator) creates Ideas and handles batching.
    """

    #TODO: The thesis's `meaning` field refers to its taxonomy location, which could be useful for narrowing down antithesis generation
    thesis_hash: str = Field(description="Hash of thesis to generate antitheses for")
    text: str = Field(default="", description="Source content context for antithesis generation")
    not_like_these: list[str] = Field(
        default_factory=list,
        description="Statements to avoid (for dedup)"
    )

    async def call(self) -> str:
        """Extract antitheses for the thesis and return report with hashes + HS values."""
        # Initialize conversation with system prompt
        self._messages.append(Messages.System(SYSTEM_PROMPT))

        # 1. Resolve thesis
        thesis = self._resolve_thesis()
        if thesis is None:
            return f"ERROR: Thesis with hash '{self.thesis_hash}' not found"

        # 2. Process based on complexity
        if thesis.is_simple:
            results = await self._process_simple(thesis)
            taxonomy = None
        else:
            taxonomy = await self._contextualize_taxonomy(thesis)
            results = await self._generate_with_taxonomy(thesis, taxonomy)

        # 3. Build report with hashes and HS values
        return self._build_report(thesis, results, taxonomy)

    def _resolve_thesis(self) -> Optional[DialecticalComponent]:
        """Resolve thesis hash to component."""
        repo = NodeRepository()
        try:
            comp = repo.find_by_hash(self.thesis_hash)
            if isinstance(comp, DialecticalComponent):
                return comp
        except ValueError:
            pass
        return None

    # --- Simple Thesis Processing ---

    def _simple_negation_prompt(self, thesis: str) -> str:
        """Build user prompt for simple thesis negation."""
        context_section = f"<context>\n{self.text}\n</context>\n\n" if self.text else ""
        return f"""{context_section}Generate a direct negation for this simple thesis.

Thesis: "{thesis}"

Generate:
1. A direct negation statement that is the logical opposite (similar length to thesis)
2. Assess the arousal level using the scale from the system prompt
3. Explain your arousal assessment"""

    async def _process_simple(
        self, thesis: DialecticalComponent
    ) -> list[AntithesisResult]:
        """Process a simple thesis: generate direct negation with HS=1.0, Mode=1.0."""
        result = await self._converse(
            response_model=SimpleNegationDto,
            user_content=self._simple_negation_prompt(thesis.statement),
        )

        # Skip if matches not_like_these
        if result.negation in self.not_like_these:
            return []

        # Create antithesis component
        antithesis = DialecticalComponent(
            statement=result.negation,
            meaning="dx://taxonomy/Simple",
        )
        antithesis.commit()

        # Connect OPPOSITE_OF
        thesis.oppositions.connect(antithesis)

        # Store Mode and Arousal estimations
        arousal_value = arousal_label_to_value(result.arousal_label)
        manager = EstimationManager()
        manager.upsert_estimation(antithesis, ModeEstimation, 1.0)
        manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value)

        # Add rationale
        rationale = Rationale(
            text=f"Direct negation of simple thesis. Arousal: {result.arousal_label} - {result.arousal_explanation}"
        )
        rationale.set_explanation_target(antithesis)
        rationale.commit()

        return [
            AntithesisResult(
                component=antithesis,
                mode_value=1.0,
                arousal_value=arousal_value,
                hs_value=1.0,
            )
        ]

    # --- Complex Thesis Processing ---

    def _contextualize_prompt(self, thesis: str, meaning: str) -> str:
        """Build user prompt for taxonomy contextualization."""
        context_section = f"<context>\n{self.text}\n</context>\n\n" if self.text else ""
        return f"""{context_section}Contextualize the universal antithesis taxonomy for this thesis.

Thesis: "{thesis}"
Thesis meaning: {meaning or "unanchored"}

Using the taxonomy structure and Mode scale from the system prompt, generate specific contextualizations for each Mode level.

Example for thesis "Love":
- apex: "Lovelessness"
- negation: "Hate"
- inversion: "Love as weapon"
- devaluation: "Love is weakness"
- hollowing: "Empty affection"
- corruption: "Possessive love"
- distortion: "Conditional love"
- skew: "Unbalanced devotion"
- blocking: "Walls against intimacy"
- suppression: "Buried feelings"
- distancing: "Emotional withdrawal"
- privation: "Complete indifference" """

    async def _contextualize_taxonomy(
        self, thesis: DialecticalComponent
    ) -> ContextualizedTaxonomyDto:
        """Contextualize universal taxonomy for a complex thesis."""
        return await self._converse(
            response_model=ContextualizedTaxonomyDto,
            user_content=self._contextualize_prompt(thesis.statement, thesis.meaning or ""),
        )

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

    async def _generate_with_taxonomy(
        self,
        thesis: DialecticalComponent,
        taxonomy: ContextualizedTaxonomyDto,
    ) -> list[AntithesisResult]:
        """Generate antithesis candidates using contextualized taxonomy (parallel)."""
        # Collect mode points to process
        mode_points: list[tuple[str, float, str]] = []  # (field_name, mode_value, branch_context)
        for field_name, mode_value in ContextualizedTaxonomyDto.MODE_FIELDS.items():
            branch_context = getattr(taxonomy, field_name, "")
            if branch_context:
                mode_points.append((field_name, mode_value, branch_context))

        if not mode_points:
            return []

        # Generate all candidates in parallel using isolated calls to avoid
        # race conditions on self._messages. These are terminal calls (no
        # subsequent _converse calls depend on them), so we don't merge back.
        tasks = [
            self._converse_isolated(
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
        results: list[AntithesisResult] = []
        manager = EstimationManager()
        antithesis_meaning = self._derive_antithesis_meaning(thesis.meaning)

        for (field_name, mode_value, _), mode_result in zip(mode_points, mode_results):
            # Skip if matches not_like_these
            if mode_result.statement in self.not_like_these:
                continue

            arousal_value = arousal_label_to_value(mode_result.arousal_label)

            # Create antithesis component
            antithesis = DialecticalComponent(
                statement=mode_result.statement,
                meaning=antithesis_meaning,
            )
            antithesis.commit()

            # Connect OPPOSITE_OF
            thesis.oppositions.connect(antithesis)

            # Store Mode and Arousal estimations
            manager.upsert_estimation(antithesis, ModeEstimation, mode_value)
            manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value)

            # Add rationale
            mode_name = field_name.capitalize()
            rationale = Rationale(
                text=(
                    f"Generated at {mode_name} (Mode={mode_value:.1f}) branch. "
                    f"HS={mode_result.hs_value:.2f}, Arousal={mode_result.arousal_label}. "
                    f"{mode_result.explanation}"
                )
            )
            rationale.set_explanation_target(antithesis)
            rationale.commit()

            results.append(
                AntithesisResult(
                    component=antithesis,
                    mode_value=mode_value,
                    arousal_value=arousal_value,
                    hs_value=mode_result.hs_value,
                )
            )

        return results

    def _derive_antithesis_meaning(self, thesis_meaning: Optional[str]) -> str:
        """
        Derive antithesis meaning from thesis meaning using systemic taxonomy.

        Maps thesis branch to corresponding antithesis concept.
        """
        if not thesis_meaning:
            return "dx://taxonomy/System(General.v1)/Viability/Fidelity/ErrorCorrection"

        # Parse thesis meaning to extract branch
        # Format: dx://taxonomy/System(Domain.v1)/Viability/Branch/Leaf
        for branch, mapping in SYSTEMIC_TAXONOMY.items():
            if f"/{branch}/" in thesis_meaning:
                # Replace the T leaf with A leaf
                # Extract domain from thesis meaning
                domain = "General"
                if "System(" in thesis_meaning:
                    start = thesis_meaning.find("System(") + 7
                    end = thesis_meaning.find(".v1)")
                    if end > start:
                        domain = thesis_meaning[start:end]

                return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{mapping['generic_a']}"

        # Default: use Fidelity/ErrorCorrection
        return "dx://taxonomy/System(General.v1)/Viability/Fidelity/ErrorCorrection"

    # --- Report Building ---

    def _build_report(
        self,
        thesis: DialecticalComponent,
        results: list[AntithesisResult],
        taxonomy: Optional[ContextualizedTaxonomyDto],
    ) -> str:
        """Build report with hashes and HS values for the orchestrator."""
        lines = []

        # Header
        is_simple = thesis.is_simple
        lines.append(f"**Thesis:** [{thesis.short_hash}] {thesis.statement}")
        lines.append(f"**Type:** {'SIMPLE' if is_simple else 'COMPLEX'}")

        if taxonomy:
            lines.append(f"**Apex:** {taxonomy.apex}")

        lines.append("")

        if not results:
            lines.append("**Antitheses:** None generated")
            return "\n".join(lines)

        lines.append(f"**Antitheses ({len(results)}):**")
        for r in results:
            lines.append(
                f"  [{r.component.short_hash}] {r.component.statement} "
                f"(Mode={r.mode_value:.1f}, Arousal={r.arousal_value:.2f}, HS={r.hs_value:.2f})"
            )

        # Machine-readable section for orchestrator
        lines.append("")
        lines.append("**Antithesis hashes:**")
        hash_data = ", ".join(
            f"{r.component.short_hash}:HS={r.hs_value:.2f}"
            for r in results
        )
        lines.append(hash_data)

        return "\n".join(lines)
