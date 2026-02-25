"""
AntithesisExtractor: Service for generating antitheses for a thesis.

Core business logic for antithesis extraction. Returns RunReport with effects.
Used by ExtractAntitheses tool (LLM orchestration) and webapp routes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.run_report import RunReport
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.estimation import ArousalEstimation, ModeEstimation
from dialectical_framework.graph.nodes.rationale import Rationale

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
    """
    Composite result for antithesis generation at a Mode point.

    Combines candidate generation, HS estimation, and arousal estimation
    into a single LLM call to reduce API calls from 3 to 1 per mode point.
    """

    statement: str = Field(description="Antithesis candidate statement (similar length to thesis)")
    heuristic_similarity: float = Field(
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


# --- Result Container ---


@dataclass
class AntithesisResult:
    """Container for an antithesis with its metadata."""

    component: DialecticalComponent
    mode_value: float
    arousal_value: float
    heuristic_similarity: float


# --- Service ---


class AntithesisExtraction(SettingsAware):
    """
    Service for extracting antitheses for a thesis.

    Handles both simple and complex theses:
    - Simple: Direct negation with HS=1.0, Mode=1.0
    - Complex: Contextualized taxonomy with candidates at key Mode points

    Returns RunReport with all effects (nodes created, relationships, estimations).
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def extract(
        self,
        thesis: DialecticalComponent,
        text: str = "",
        not_like_these: Optional[list[str]] = None,
    ) -> RunReport:
        """
        Extract antitheses for a thesis.

        Args:
            thesis: The thesis component to generate antitheses for
            text: Optional source content context
            not_like_these: Statements to avoid (for dedup)

        Returns:
            RunReport with effects and artifacts
        """
        self._text = text
        self._not_like_these = not_like_these or []
        self._report = RunReport(tool="antithesis_extractor")

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Process based on complexity
        if thesis.is_simple:
            results = await self._process_simple(thesis)
            taxonomy = None
        else:
            taxonomy = await self._contextualize_taxonomy(thesis)
            results = await self._generate_with_taxonomy(thesis, taxonomy)

        # Build artifacts
        self._report.artifacts["thesis_hash"] = thesis.hash
        self._report.artifacts["antithesis_hashes"] = [r.component.hash for r in results]
        self._report.artifacts["heuristic_similarity_by_hash"] = {
            r.component.hash: r.heuristic_similarity for r in results
        }
        if taxonomy:
            self._report.artifacts["apex"] = taxonomy.apex

        # Summary
        thesis_type = "simple" if thesis.is_simple else "complex"
        self._report.summary = (
            f"Extracted {len(results)} antithesis(es) for {thesis_type} thesis "
            f"'{thesis.statement[:50]}...'" if len(thesis.statement) > 50
            else f"Extracted {len(results)} antithesis(es) for {thesis_type} thesis '{thesis.statement}'"
        )

        return self._report

    # --- Simple Thesis Processing ---

    async def _process_simple(self, thesis: DialecticalComponent) -> list[AntithesisResult]:
        """Process a simple thesis: generate direct negation."""
        prompt = self._simple_negation_prompt(thesis.statement)
        result = await self._conversation.submit(
            response_model=SimpleNegationDto,
            user_content=prompt,
        )

        # Skip if matches not_like_these
        if result.negation in self._not_like_these:
            return []

        # Create antithesis component
        antithesis = DialecticalComponent(
            statement=result.negation,
            meaning="dx://taxonomy/Simple",
        )
        antithesis.commit()
        self._report.node_created(antithesis, meta={"mode": 1.0, "type": "simple_negation"})

        # Connect OPPOSITE_OF
        thesis.oppositions.connect(antithesis)
        self._report.relationship_created(
            thesis.oppositions, thesis, antithesis,
            meta={"auto_created": True}
        )

        # Add rationale (created first so it can be provider for estimations)
        arousal_value = arousal_label_to_value(result.arousal_label)
        rationale = Rationale(
            text=f"Direct negation of simple thesis. Arousal: {result.arousal_label} - {result.arousal_explanation}"
        )
        rationale.set_explanation_target(antithesis)
        rationale.commit()
        self._report.node_created(rationale)

        # Store estimations with rationale as provider
        manager = EstimationManager()
        mode_est = manager.upsert_estimation(antithesis, ModeEstimation, 1.0, provider=rationale)
        arousal_est = manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value, provider=rationale)
        if mode_est:
            self._report.node_updated(mode_est, patch={"value": 1.0})
        if arousal_est:
            self._report.node_updated(arousal_est, patch={"value": arousal_value})

        return [
            AntithesisResult(
                component=antithesis,
                mode_value=1.0,
                arousal_value=arousal_value,
                heuristic_similarity=1.0,
            )
        ]

    def _simple_negation_prompt(self, thesis: str) -> str:
        """Build user prompt for simple thesis negation."""
        context_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        return f"""{context_section}Generate a direct negation for this simple thesis.

Thesis: "{thesis}"

Generate:
1. A direct negation statement that is the logical opposite (similar length to thesis)
2. Assess the arousal level using the scale from the system prompt
3. Explain your arousal assessment"""

    # --- Complex Thesis Processing ---

    async def _contextualize_taxonomy(
        self, thesis: DialecticalComponent
    ) -> ContextualizedTaxonomyDto:
        """Contextualize universal taxonomy for a complex thesis."""
        prompt = self._contextualize_prompt(thesis.statement, thesis.meaning or "")
        return await self._conversation.submit(
            response_model=ContextualizedTaxonomyDto,
            user_content=prompt,
        )

    def _contextualize_prompt(self, thesis: str, meaning: str) -> str:
        """Build user prompt for taxonomy contextualization."""
        context_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        return f"""{context_section}Contextualize the universal antithesis taxonomy for this thesis.

Thesis: "{thesis}"
Thesis meaning: {meaning or "unanchored"}

Using the taxonomy structure and Mode scale from the system prompt, generate specific contextualizations for each Mode level.

Each contextualization should be 2-5 words describing that type of opposition in the specific context of the thesis.

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

    async def _generate_with_taxonomy(
        self,
        thesis: DialecticalComponent,
        taxonomy: ContextualizedTaxonomyDto,
    ) -> list[AntithesisResult]:
        """Generate antithesis candidates using contextualized taxonomy (parallel)."""
        # Collect mode points to process
        mode_points: list[tuple[str, float, str]] = []
        for field_name, mode_value in ContextualizedTaxonomyDto.MODE_FIELDS.items():
            branch_context = getattr(taxonomy, field_name, "")
            if branch_context:
                mode_points.append((field_name, mode_value, branch_context))

        if not mode_points:
            return []

        # Generate all candidates in parallel using isolated calls
        tasks = [
            self._conversation.isolate().submit(
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
            if mode_result.statement in self._not_like_these:
                continue

            arousal_value = arousal_label_to_value(mode_result.arousal_label)

            # Create antithesis component
            antithesis = DialecticalComponent(
                statement=mode_result.statement,
                meaning=antithesis_meaning,
            )
            antithesis.commit()
            self._report.node_created(
                antithesis,
                meta={"mode": mode_value, "branch": field_name, "heuristic_similarity": mode_result.heuristic_similarity}
            )

            # Connect OPPOSITE_OF
            thesis.oppositions.connect(antithesis)
            self._report.relationship_created(
                thesis.oppositions, thesis, antithesis,
                meta={"auto_created": True}
            )

            # Add rationale (created first so it can be provider for estimations)
            mode_name = field_name.capitalize()
            rationale = Rationale(
                text=(
                    f"Generated at {mode_name} (Mode={mode_value:.1f}) branch. "
                    f"Heuristic Similarity={mode_result.heuristic_similarity:.2f}, Arousal={mode_result.arousal_label}. "
                    f"{mode_result.explanation}"
                )
            )
            rationale.set_explanation_target(antithesis)
            rationale.commit()
            self._report.node_created(rationale)

            # Store estimations with rationale as provider
            mode_est = manager.upsert_estimation(antithesis, ModeEstimation, mode_value, provider=rationale)
            arousal_est = manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value, provider=rationale)
            if mode_est:
                self._report.node_updated(mode_est, patch={"value": mode_value})
            if arousal_est:
                self._report.node_updated(arousal_est, patch={"value": arousal_value})

            results.append(
                AntithesisResult(
                    component=antithesis,
                    mode_value=mode_value,
                    arousal_value=arousal_value,
                    heuristic_similarity=mode_result.heuristic_similarity,
                )
            )

        return results

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

    def _derive_antithesis_meaning(self, thesis_meaning: Optional[str]) -> str:
        """Derive antithesis meaning from thesis meaning using systemic taxonomy."""
        if not thesis_meaning:
            return "dx://taxonomy/System(General.v1)/Viability/Fidelity/ErrorCorrection"

        for branch, mapping in SYSTEMIC_TAXONOMY.items():
            if f"/{branch}/" in thesis_meaning:
                domain = "General"
                if "System(" in thesis_meaning:
                    start = thesis_meaning.find("System(") + 7
                    end = thesis_meaning.find(".v1)")
                    if end > start:
                        domain = thesis_meaning[start:end]

                return f"dx://taxonomy/System({domain}.v1)/Viability/{branch}/{mapping['generic_a']}"

        return "dx://taxonomy/System(General.v1)/Viability/Fidelity/ErrorCorrection"
