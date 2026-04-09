"""
AntithesisClassification: Capability for classifying a user-provided antithesis.

Evaluates a given antithesis statement against a thesis to determine:
- Mode: Where on the negation→privation scale (0.0-1.0)
- HS: Heuristic Similarity to the apex concept (0.0-1.0)
- Arousal: How active/visible is the tension

This is the antithesis counterpart to StatementClassification for theses.

Does NOT create any database nodes - caller decides what to do with result.

This module is the authority for antithesis taxonomy constants:
- SYSTEM_PROMPT: Canonical taxonomy/scales prompt
- ContextualizedTaxonomyDto: Taxonomy contextualization for a thesis
- AROUSAL_VALUES / arousal_label_to_value: Arousal scale mapping
- MODE_FIELDS: Mode label to value mapping

Usage:
    classifier = AntithesisClassification()
    result = await classifier.execute(
        thesis=thesis_component,
        antithesis_statement="Distrust",
        text="context about software systems..."
    )
    print(f"Mode: {result.mode_value}, HS: {result.heuristic_similarity}")

    # Caller creates component if needed:
    antithesis = DialecticalComponent(statement=result.statement, meaning=result.meaning)
    antithesis.commit()
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Optional

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.executable_capability import \
    ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.features.statement_classification import \
    StatementClassification

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import \
        DialecticalComponent


# --- System Prompt (canonical for antithesis taxonomy) ---

SYSTEM_PROMPT = """You are a dialectical antithesis evaluator using the universal antithesis taxonomy.

Your task is to evaluate a given antithesis statement against a thesis and determine where it falls
in the taxonomy.

## Universal Antithesis Taxonomy Structure

[T]-lessness (APEX)
├── Anti-[T] (active opposition)
│   ├── Violations (attacks on T)
│   │   ├── Negation (1.0) - Direct, active opposition
│   │   ├── Inversion (0.9) - Reversal of meaning
│   │   ├── Devaluation (0.8) - Diminishing worth
│   │   ├── Hollowing (0.7) - Emptying of substance
│   │   └── Corruption (0.6) - Degrading/perverting
│   └── Deformation (distortions of T)
│       ├── Distortion (0.5) - Twisting form
│       └── Skew (0.4) - Imbalancing
└── Absence of [T] (passive opposition)
    ├── Inhibition (obstacles to T)
    │   ├── Blocking (0.3) - Obstructing
    │   ├── Suppression (0.2) - Holding down
    │   └── Distancing (0.1) - Drifting from
    └── Privation (0.0) - Complete absence

Example for T="Love":

Lovelessness (APEX)
├── Anti-Love
│   ├── Violations
│   │   ├── Hate (1.0)
│   │   ├── Love as weapon (0.9)
│   │   ├── Love is weakness (0.8)
│   │   ├── Empty affection (0.7)
│   │   └── Possessive love (0.6)
│   └── Deformation
│       ├── Conditional love (0.5)
│       └── Unbalanced devotion (0.4)
└── Absence of Love
    ├── Inhibition
    │   ├── Walls against intimacy (0.3)
    │   ├── Buried feelings (0.2)
    │   └── Emotional withdrawal (0.1)
    └── Complete indifference (0.0)

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

HS measures how well the antithesis represents the apex concept:
- 0.9-1.0: Perfect or near-perfect match - exemplary antithesis
- 0.7-0.9: Very similar - captures most aspects of the apex
- 0.5-0.7: Related - captures some aspects, moderate quality
- 0.3-0.5: Somewhat related - weak but still a valid antithesis
- 0.1-0.3: Weakly related - poor quality antithesis, but still in the right category
- 0.0-0.1: Not related - wrong category entirely, not an antithesis (likely a pole or unrelated)

**Critical threshold**: HS > 0.1 means valid antithesis (quality varies).
HS ≤ 0.1 means wrong category - this is NOT an antithesis.

Respond with structured output matching the requested format."""


# --- Arousal Scale Constants ---

AROUSAL_VALUES = {
    "dormant": 0.1,  # Completely latent, invisible tension
    "latent": 0.2,  # Barely perceptible, nascent
    "low": 0.3,  # Mild, background tension
    "mild": 0.4,  # Noticeable but subdued
    "moderate": 0.5,  # Balanced, present tension
    "elevated": 0.6,  # Becoming prominent
    "high": 0.7,  # Strong, clearly visible
    "intense": 0.8,  # Very active, urgent
    "active": 0.9,  # Fully manifest, immediate
}


def arousal_label_to_value(label: str) -> float:
    """Convert arousal label to value. Returns default if unknown."""
    return AROUSAL_VALUES.get(label.lower().strip(), 0.5)


# --- Contextualized Taxonomy DTO ---


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
        "negation": 1.0,  # Direct, active opposition to T
        "inversion": 0.9,  # Reversal of T's meaning
        "devaluation": 0.8,  # Diminishing T's worth
        "hollowing": 0.7,  # Emptying T of substance
        "corruption": 0.6,  # Degrading/perverting T
        "distortion": 0.5,  # Twisting T's form
        "skew": 0.4,  # Imbalancing T
        "blocking": 0.3,  # Obstructing T
        "suppression": 0.2,  # Holding T down
        "distancing": 0.1,  # Drifting from T
        "privation": 0.0,  # Complete absence of T
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


# --- Shared Taxonomy Contextualization ---


def build_contextualize_prompt(
    thesis_statement: str, thesis_meaning: str, text: str
) -> str:
    """Build user prompt for taxonomy contextualization.

    Shared by AntithesisClassification and AntithesisExtraction.
    """
    context_section = f"<context>\n{text}\n</context>\n\n" if text else ""
    return f"""{context_section}Contextualize the universal antithesis taxonomy for this thesis.

Thesis: "{thesis_statement}"
Thesis meaning: {thesis_meaning or "unanchored"}

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


async def contextualize_taxonomy(
    thesis_statement: str,
    thesis_meaning: str,
    text: str,
    conversation: ConversationFacilitator,
) -> ContextualizedTaxonomyDto:
    """Contextualize universal taxonomy for a complex thesis.

    Shared by AntithesisClassification and AntithesisExtraction.

    Args:
        thesis_statement: The thesis statement
        thesis_meaning: The thesis meaning/anchor
        text: Optional context text
        conversation: ConversationFacilitator to use for the LLM call

    Returns:
        ContextualizedTaxonomyDto with contextualized mode points
    """
    prompt = build_contextualize_prompt(thesis_statement, thesis_meaning, text)
    return await conversation.submit(
        response_model=ContextualizedTaxonomyDto,
        user_content=prompt,
    )


# --- Evaluation DTOs ---


class AntithesisEvaluationDto(BaseModel):
    """Result of evaluating an antithesis against a thesis."""

    mode_label: str = Field(
        description="Mode level: negation/inversion/devaluation/hollowing/corruption/distortion/skew/blocking/suppression/distancing/privation"
    )
    mode_value: float = Field(ge=0.0, le=1.0, description="Mode value (0.0-1.0)")
    heuristic_similarity: float = Field(
        ge=0.0, le=1.0, description="Heuristic Similarity to apex concept (0.0-1.0)"
    )
    arousal_label: str = Field(
        description="Arousal level: dormant/latent/low/mild/moderate/elevated/high/intense/active"
    )
    explanation: str = Field(
        description="Reasoning for Mode, HS, and Arousal assessments"
    )


class SimpleAntithesisEvaluationDto(BaseModel):
    """Result of evaluating an antithesis for a simple thesis."""

    mode_value: float = Field(
        ge=0.0,
        le=1.0,
        description="Mode value (1.0=direct negation, lower values=weaker opposition)",
    )
    heuristic_similarity: float = Field(
        ge=0.0,
        le=1.0,
        description="How well does this antithesis represent the negation of the thesis? (0.0-1.0)",
    )
    arousal_label: str = Field(
        description="Arousal level: dormant/latent/low/mild/moderate/elevated/high/intense/active"
    )
    explanation: str = Field(
        description="Reasoning for Mode, HS, and Arousal assessments"
    )


# --- Result ---


@dataclass
class AntithesisClassificationResult:
    """Result of antithesis classification - no DB nodes created."""

    statement: str
    meaning: str
    mode_value: float
    mode_label: str
    arousal_value: float
    heuristic_similarity: float
    reasoning: str
    apex: Optional[str] = None  # The apex concept (for complex theses)


# --- Capability ---


class AntithesisClassification(ExecutableCapability[AntithesisClassificationResult]):
    """
    Capability for classifying a user-provided antithesis against a thesis.

    Evaluates the antithesis to determine:
    - Mode: Where on the negation→privation scale
    - HS: Heuristic Similarity to the apex concept
    - Arousal: How active/visible is the tension

    This mirrors StatementClassification but for antitheses.
    Does NOT create any database nodes - caller decides what to do with result.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def execute(
        self,
        thesis: DialecticalComponent,
        antithesis_statement: str,
        text: str = "",
    ) -> AntithesisClassificationResult:
        """
        Classify a user-provided antithesis against a thesis.

        Args:
            thesis: The thesis component to evaluate against
            antithesis_statement: The antithesis statement to classify
            text: Optional source content context

        Returns:
            AntithesisClassificationResult with mode, arousal, HS, meaning (no DB nodes created)
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Early validation
        if not thesis or not thesis.statement:
            raise ValueError("Cannot classify antithesis without a valid thesis")
        if not antithesis_statement or not antithesis_statement.strip():
            raise ValueError("Cannot classify empty antithesis statement")

        self._text = text
        self._antithesis_statement = antithesis_statement.strip()
        self._thesis = thesis

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Get meaning from thesis (deterministic lookup)
        antithesis_meaning = StatementClassification.lookup_antithesis_meaning(thesis)

        # Process based on thesis complexity
        if thesis.is_simple:
            result = await self._evaluate_simple(antithesis_meaning)
        else:
            result = await self._evaluate_complex(antithesis_meaning)

        # Build report
        self._report.artifacts["mode_value"] = result.mode_value
        self._report.artifacts["heuristic_similarity"] = result.heuristic_similarity
        self._report.artifacts["arousal_value"] = result.arousal_value
        self._report.ok = True
        self._report.summary = (
            f"Classified antithesis '{self._antithesis_statement}' "
            f"(Mode={result.mode_value:.1f}, HS={result.heuristic_similarity:.2f})"
        )

        return result

    # --- Simple Thesis Evaluation ---

    async def _evaluate_simple(self, meaning: str) -> AntithesisClassificationResult:
        """Evaluate antithesis for a simple thesis."""
        result = await self._conversation.submit(
            response_model=SimpleAntithesisEvaluationDto,
            user_content=self._simple_evaluation_prompt(),
        )

        arousal_value = arousal_label_to_value(result.arousal_label)

        # Derive mode_label from mode_value
        mode_label = self._mode_value_to_label(result.mode_value)

        return AntithesisClassificationResult(
            statement=self._antithesis_statement,
            meaning=meaning,
            mode_value=result.mode_value,
            mode_label=mode_label,
            arousal_value=arousal_value,
            heuristic_similarity=result.heuristic_similarity,
            reasoning=result.explanation,
            apex=None,
        )

    @staticmethod
    def _mode_value_to_label(mode_value: float) -> str:
        """Convert mode value to closest mode label using ContextualizedTaxonomyDto.MODE_FIELDS."""
        # Reuse the authoritative mapping from ContextualizedTaxonomyDto
        mode_fields = ContextualizedTaxonomyDto.MODE_FIELDS
        # Find closest match by mode value
        closest_label = min(
            mode_fields.keys(), key=lambda k: abs(mode_fields[k] - mode_value)
        )
        return closest_label

    def _simple_evaluation_prompt(self) -> str:
        """Build prompt for simple thesis evaluation."""
        context_section = (
            f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        )
        return f"""{context_section}Evaluate this antithesis for a simple (binary/literal) thesis.

Thesis: "{self._thesis.statement}"
Antithesis to evaluate: "{self._antithesis_statement}"

For simple theses, the "apex" is the direct logical negation of the thesis.

Determine:

1. **Mode** (0.0-1.0): Use the full Mode scale from the system prompt to determine how the antithesis opposes the thesis:
   - 1.0 = Negation (direct, active opposition)
   - 0.9 = Inversion (reversal of meaning)
   - 0.8 = Devaluation (diminishing worth)
   - 0.7 = Hollowing (emptying of substance)
   - 0.6 = Corruption (degrading/perverting)
   - 0.5 = Distortion (twisting form)
   - 0.4 = Skew (imbalancing)
   - 0.3 = Blocking (obstructing)
   - 0.2 = Suppression (holding down)
   - 0.1 = Distancing (drifting from)
   - 0.0 = Privation (complete absence)

2. **HS (Heuristic Similarity)** (0.0-1.0): How well does this antithesis represent the ideal negation (apex)?
   Use the HS scale from the system guidelines.

3. **Arousal**: Assess the arousal level of the T↔A tension using the arousal scale from the system guidelines.

4. **Explanation**: Provide reasoning for your assessments."""

    # --- Complex Thesis Evaluation ---

    async def _evaluate_complex(self, meaning: str) -> AntithesisClassificationResult:
        """Evaluate antithesis for a complex thesis."""
        # First, contextualize the taxonomy
        taxonomy = await self._contextualize_taxonomy()

        # Then evaluate the antithesis against the contextualized taxonomy
        evaluation = await self._conversation.submit(
            response_model=AntithesisEvaluationDto,
            user_content=self._complex_evaluation_prompt(taxonomy),
        )

        arousal_value = arousal_label_to_value(evaluation.arousal_label)

        return AntithesisClassificationResult(
            statement=self._antithesis_statement,
            meaning=meaning,
            mode_value=evaluation.mode_value,
            mode_label=evaluation.mode_label,
            arousal_value=arousal_value,
            heuristic_similarity=evaluation.heuristic_similarity,
            reasoning=evaluation.explanation,
            apex=taxonomy.apex,
        )

    async def _contextualize_taxonomy(self) -> ContextualizedTaxonomyDto:
        """Contextualize universal taxonomy for a complex thesis."""
        return await contextualize_taxonomy(
            thesis_statement=self._thesis.statement,
            thesis_meaning=self._thesis.meaning or "",
            text=self._text,
            conversation=self._conversation,
        )

    def _complex_evaluation_prompt(self, taxonomy: ContextualizedTaxonomyDto) -> str:
        """Build prompt for complex thesis evaluation."""
        # Build taxonomy reference
        taxonomy_ref = f"""Contextualized taxonomy for thesis "{self._thesis.statement}":
- Apex: {taxonomy.apex}
- Negation (1.0): {taxonomy.negation}
- Inversion (0.9): {taxonomy.inversion}
- Devaluation (0.8): {taxonomy.devaluation}
- Hollowing (0.7): {taxonomy.hollowing}
- Corruption (0.6): {taxonomy.corruption}
- Distortion (0.5): {taxonomy.distortion}
- Skew (0.4): {taxonomy.skew}
- Blocking (0.3): {taxonomy.blocking}
- Suppression (0.2): {taxonomy.suppression}
- Distancing (0.1): {taxonomy.distancing}
- Privation (0.0): {taxonomy.privation}"""

        return f"""Evaluate this antithesis against the contextualized taxonomy.

Thesis: "{self._thesis.statement}"
Antithesis to evaluate: "{self._antithesis_statement}"

{taxonomy_ref}

Determine:
1. **Mode**: Which Mode level does this antithesis most closely align with? Consider the semantic meaning and type of opposition.
2. **HS (Heuristic Similarity)**: How similar is this antithesis to the apex concept "{taxonomy.apex}"? Use the HS scale from the system prompt.
3. **Arousal**: Assess the arousal level of the T↔A tension using the scale from the system prompt.
4. **Explanation**: Provide reasoning for your assessments.

Important: The mode_value should match the mode_label (e.g., if mode_label is "corruption", mode_value should be 0.6)."""
