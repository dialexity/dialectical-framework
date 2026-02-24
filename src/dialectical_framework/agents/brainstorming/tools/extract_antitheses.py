"""
ExtractAntitheses: Work tool for generating antitheses for a SINGLE thesis.

This is the Phase 2 work tool, symmetric to ExtractTheses (Phase 1).
- ExtractTheses: handles thesis extraction for one text/content
- ExtractAntitheses: handles antithesis generation for one thesis

Does NOT create Ideas node - that's the orchestrator's job (PolarityFindingAgent).
Returns component hashes + HS values for the orchestrator to use.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Optional

from mirascope import BaseTool, Messages, prompt_template
from mirascope.integrations.langfuse import with_langfuse
from pydantic import BaseModel, Field

from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.estimation import ArousalEstimation, ModeEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.repositories.node_repository import NodeRepository
from dialectical_framework.protocols.has_brain import HasBrain
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.use_brain import use_brain

if TYPE_CHECKING:
    pass


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


class CandidateDto(BaseModel):
    """Antithesis candidate at a Mode point."""

    statement: str = Field(description="Candidate antithesis statement (similar length to thesis)")
    explanation: str = Field(description="How it fits the Mode branch")


class HSEstimationDto(BaseModel):
    """HS estimation result."""

    hs_value: float = Field(
        ge=0.0, le=1.0, description="Heuristic Similarity (0.0-1.0)"
    )
    explanation: str = Field(description="Reasoning for the HS assessment")


class ArousalEstimationDto(BaseModel):
    """Arousal estimation result."""

    arousal_label: str = Field(description="dormant/latent/low/mild/moderate/elevated/high/intense/active")
    explanation: str = Field(description="Reasoning for the arousal assessment")


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


class ExtractAntitheses(BaseTool, HasBrain, SettingsAware):
    """
    Extract antitheses for a SINGLE thesis.

    This is the work tool for Phase 2 of polarity-finder.
    Handles both simple and complex theses:
    - Simple: Direct negation with HS=1.0, Mode=1.0
    - Complex: Contextualized taxonomy with candidates at key Mode points

    Does NOT create Ideas node. Returns report with hashes and HS values.    PolarityFindingAgent (orchestrator) creates Ideas and handles batching.

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

    @prompt_template(
        """
        USER:
        {context_section}

        Generate a direct negation for this simple thesis.

        Thesis: "{thesis}"

        Generate:
        1. A direct negation statement that is the logical opposite (similar length to thesis)
        2. Assess the arousal level (activation from invisible to visible):
           - dormant: Completely latent, invisible tension
           - latent: Barely perceptible, nascent
           - low: Mild, background tension
           - mild: Noticeable but subdued
           - moderate: Balanced, present tension
           - elevated: Becoming prominent
           - high: Strong, clearly visible
           - intense: Very active, urgent
           - active: Fully manifest, immediate
        """
    )
    def _simple_negation_prompt(self, thesis: str) -> Messages.Type:
        context_section = f"<context>\n{self.text}\n</context>" if self.text else ""
        return {
            "computed_fields": {
                "thesis": thesis,
                "context_section": context_section,
            }
        }

    async def _process_simple(
        self, thesis: DialecticalComponent
    ) -> list[AntithesisResult]:
        """Process a simple thesis: generate direct negation with HS=1.0, Mode=1.0."""

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=SimpleNegationDto)
        async def _generate():
            return self._simple_negation_prompt(thesis.statement)

        result = await _generate()

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

    @prompt_template(
        """
        USER:
        {context_section}

        Contextualize the universal antithesis taxonomy for this thesis.

        Thesis: "{thesis}"
        Thesis meaning: {meaning}

        Universal taxonomy structure:
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

        Mode scale (interaction mechanism from absence to negation):
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

        Generate specific contextualizations for each Mode level.
        Each contextualization should be 2-5 words describing that type
        of opposition in the specific context of the thesis.

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
        - privation: "Complete indifference"
        """
    )
    def _contextualize_prompt(self, thesis: str, meaning: str) -> Messages.Type:
        context_section = f"<context>\n{self.text}\n</context>" if self.text else ""
        return {
            "computed_fields": {
                "thesis": thesis,
                "meaning": meaning or "unanchored",
                "context_section": context_section,
            }
        }

    async def _contextualize_taxonomy(
        self, thesis: DialecticalComponent
    ) -> ContextualizedTaxonomyDto:
        """Contextualize universal taxonomy for a complex thesis."""

        @with_langfuse()
        @use_brain(brain=self.brain, response_model=ContextualizedTaxonomyDto)
        async def _contextualize():
            return self._contextualize_prompt(thesis.statement, thesis.meaning or "")

        return await _contextualize()

    @prompt_template(
        """
        USER:
        Generate an antithesis candidate for this thesis at a specific Mode point.

        Thesis: "{thesis}"

        Contextualized taxonomy:
        - Apex ({apex_label}): {apex}
        - Target branch ({branch_name}): {branch_context}

        Generate a candidate antithesis that fits the {branch_name} branch.
        The candidate should represent {branch_name} of the thesis concept.
        Keep the antithesis similar in length and abstraction level to the thesis.
        """
    )
    def _candidate_prompt(
        self,
        thesis: str,
        apex: str,
        branch_name: str,
        branch_context: str,
    ) -> Messages.Type:
        return {
            "computed_fields": {
                "thesis": thesis,
                "apex": apex,
                "apex_label": "complete absence",
                "branch_name": branch_name,
                "branch_context": branch_context,
            }
        }

    @prompt_template(
        """
        USER:
        Rate semantic similarity between this candidate and the apex concept.

        Candidate: "{candidate}"
        Apex ([T]-lessness concept): "{apex}"
        Thesis being opposed: "{thesis}"

        How well does the candidate represent the general concept of the apex?
        Rate from 0.0 (unrelated) to 1.0 (equivalent).

        Consider:
        - 0.0-0.3: Unrelated or tangentially related
        - 0.3-0.5: Somewhat related but different focus
        - 0.5-0.7: Related, captures some aspects of apex
        - 0.7-0.9: Very similar, captures most aspects of apex
        - 0.9-1.0: Equivalent or near-equivalent to apex
        """
    )
    def _hs_prompt(self, candidate: str, apex: str, thesis: str) -> Messages.Type:
        return {
            "computed_fields": {
                "candidate": candidate,
                "apex": apex,
                "thesis": thesis,
            }
        }

    @prompt_template(
        """
        USER:
        Assess the activation level of this dialectical tension.

        Thesis: "{thesis}"
        Antithesis: "{antithesis}"

        Arousal describes how actively the opposition manifests (from invisible to visible):
        - dormant: Completely latent, invisible tension
        - latent: Barely perceptible, nascent
        - low: Mild, background tension
        - mild: Noticeable but subdued
        - moderate: Balanced, present tension
        - elevated: Becoming prominent
        - high: Strong, clearly visible
        - intense: Very active, urgent
        - active: Fully manifest, immediate
        """
    )
    def _arousal_prompt(self, thesis: str, antithesis: str) -> Messages.Type:
        return {
            "computed_fields": {
                "thesis": thesis,
                "antithesis": antithesis,
            }
        }

    async def _generate_with_taxonomy(
        self,
        thesis: DialecticalComponent,
        taxonomy: ContextualizedTaxonomyDto,
    ) -> list[AntithesisResult]:
        """Generate antithesis candidates using contextualized taxonomy."""
        results: list[AntithesisResult] = []
        manager = EstimationManager()

        # Build antithesis meaning from thesis meaning
        antithesis_meaning = self._derive_antithesis_meaning(thesis.meaning)

        for field_name, mode_value in ContextualizedTaxonomyDto.MODE_FIELDS.items():
            branch_context = getattr(taxonomy, field_name, "")
            if not branch_context:
                continue

            mode_name = field_name.capitalize()  # e.g., "negation" -> "Negation"

            # Generate candidate at this Mode point
            @with_langfuse()
            @use_brain(brain=self.brain, response_model=CandidateDto)
            async def _generate_candidate():
                return self._candidate_prompt(
                    thesis.statement,
                    taxonomy.apex,
                    mode_name,
                    branch_context,
                )

            candidate_result = await _generate_candidate()

            # Skip if matches not_like_these
            if candidate_result.statement in self.not_like_these:
                continue

            # Estimate HS for this candidate
            @with_langfuse()
            @use_brain(brain=self.brain, response_model=HSEstimationDto)
            async def _estimate_hs():
                return self._hs_prompt(
                    candidate_result.statement,
                    taxonomy.apex,
                    thesis.statement,
                )

            hs_result = await _estimate_hs()

            # Estimate Arousal
            @with_langfuse()
            @use_brain(brain=self.brain, response_model=ArousalEstimationDto)
            async def _estimate_arousal():
                return self._arousal_prompt(
                    thesis.statement, candidate_result.statement
                )

            arousal_result = await _estimate_arousal()
            arousal_value = arousal_label_to_value(arousal_result.arousal_label)

            # Create antithesis component
            antithesis = DialecticalComponent(
                statement=candidate_result.statement,
                meaning=antithesis_meaning,
            )
            antithesis.commit()

            # Connect OPPOSITE_OF
            thesis.oppositions.connect(antithesis)

            # Store Mode and Arousal estimations
            manager.upsert_estimation(antithesis, ModeEstimation, mode_value)
            manager.upsert_estimation(antithesis, ArousalEstimation, arousal_value)

            # Add rationale
            rationale = Rationale(
                text=(
                    f"Generated at {mode_name} (Mode={mode_value:.1f}) branch. "
                    f"{candidate_result.explanation} "
                    f"HS={hs_result.hs_value:.2f}: {hs_result.explanation} "
                    f"Arousal={arousal_result.arousal_label}: {arousal_result.explanation}"
                )
            )
            rationale.set_explanation_target(antithesis)
            rationale.commit()

            results.append(
                AntithesisResult(
                    component=antithesis,
                    mode_value=mode_value,
                    arousal_value=arousal_value,
                    hs_value=hs_result.hs_value,
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
