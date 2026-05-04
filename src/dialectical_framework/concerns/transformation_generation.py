"""
TransformationGeneration: Concern for generating a full transformation tetrad from an Ac+ candidate.

Given an Ac+ candidate, generates the complementary Re+, and the negative aspects Re- and Ac-
following the Coherence Constraint (CC).

Usage:
    service = TransformationGeneration()
    tetrad = await service.resolve(edge, ac_plus, apexes, input_text)
    print(f"Ac+: {tetrad.ac_plus.statement}")
    print(f"Re+: {tetrad.re_plus.statement}")
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.concerns.ac_re_taxonomy import (
    INSIGHT_SCALE, PROACTIVENESS_SCALE, get_polar_pair, insight_label_to_value,
    proactiveness_label_to_value)
from dialectical_framework.concerns.action_extraction import \
    ActionCandidateResultDto
from dialectical_framework.graph.repositories.transformation_repository import (
    CoarserTransformation, TransformationRepository)
from dialectical_framework.utils.edge_context import build_edge_context as _build_edge_context
from dialectical_framework.concerns.positive_ac_re_apex_derivation import \
    ApexDerivationResultDto
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition


SYSTEM_PROMPT = """You are an expert in dialectical reasoning, specializing in Action-Reflection transformations.

Your task is to complete a transformation tetrad given an Ac+ statement.

## Transformation Structure

The +/- notation is STRUCTURAL (like electrical charges), not a value judgment:
- "+" aspects target beneficial states (T+ or A+)
- "-" aspects target problematic states (T- or A-)

A transformation has 4 transition aspects:
- **Ac+**: T- → A+ (action targeting A+: escaping T's problems toward A's benefits)
- **Re+**: A- → T+ (reflection targeting T+: escaping A's problems toward T's benefits)
- **Re-**: A+ → T- (reflection targeting T-: what happens when action lacks reflection)
- **Ac-**: T+ → A- (action targeting A-: what happens when reflection lacks action)

## Circular Causality: Why Ac+ and Re+ Must Be Complementary

Positive synthesis (S+) emerges ONLY when Ac+ and Re+ work together as complementary transitions:
- Ac+ alone (action without reflection) regresses to Re- (back to T-)
- Re+ alone (reflection without action) drifts to Ac- (toward A-)

Together, they form a closed loop of circular causality — the source of self-regulation in healthy systems.

**Re+ should NOT simply restate or mirror Ac+.** It must be a genuinely complementary reflection that:
- Addresses a DIFFERENT aspect of the tension (what Ac+ doesn't cover)
- Works harmoniously WITH Ac+ to create a complete solution
- Could stand alone as valuable insight, not just a reaction to Ac+

## Diagonal Contradictions

The tetrad has diagonal contradictions that must be preserved:
- **Re+ must contradict Ac-**: The positive reflection opposes the drift toward A-
- **Ac+ must contradict Re-**: The positive action opposes regression toward T-

## Coherence Constraint (CC)

The "-" aspects describe failure modes when transitions are unbalanced:
- Re-: "Ac+ without Re+ yields Re-" — unguided action regresses toward T-
- Ac-: "Re+ without Ac+ yields Ac-" — ungrounded reflection drifts toward A-

## Y-Axis: Insight (0.0 → 1.0)

```
APEX
├── GENERATIVE
│   ├── Transformational
│   │   ├── Transcendence (1.0) - Paradigm shift, new dimension
│   │   ├── Redirection (0.9) - Fundamental change of direction
│   │   └── Inversion (0.8) - Flipping perspective entirely
│   └── Strategic
│       ├── Anticipation (0.7) - Acting/thinking ahead of events
│       └── Leverage (0.6) - Finding and using leverage points
├── CONFIGURATIONAL
│   ├── Composition (0.5) - Combining elements in new ways
│   └── Reformulation (0.4) - Restating/restructuring approach
└── CORRECTIVE
    ├── Adjusted
    │   ├── Variation (0.3) - Making deliberate small changes
    │   └── Tuning (0.2) - Fine-tuning existing approach
    └── Reactive
        ├── Procedure (0.1) - Following established protocol
        └── Reflex (0.0) - Automatic, instinctive response
```

## X-Axis: Proactiveness (0.0 → 1.0)

**Reflections (Re zone: 0.0-0.4)**

| Value | Label | Description |
|-------|-------|-------------|
| 0.0   | Observation | Passive noticing without judgment |
| 0.1   | Detection | Identifying patterns or anomalies |
| 0.2   | Interpretation | Making sense of what's detected |
| 0.3   | Framing | Placing in broader context |
| 0.4   | Evaluation | Assessing value/significance |

**Actions (Ac zone: 0.5-1.0)**

| Value | Label | Description |
|-------|-------|-------------|
| 0.5   | Coordination | Aligning multiple elements |
| 0.6   | Intervention | Stepping in to change something |
| 0.7   | Implementation | Executing a defined plan |
| 0.8   | Configuration | Arranging/structuring elements |
| 0.9   | Governance | Directing, setting rules/policies |
| 1.0   | Stewardship | Active long-term caretaking |

## Ac → Re Polar Pairs

| Ac (Action) | Re (Reflection) |
|-------------|-----------------|
| Coordination (0.5) | Framing (0.3) |
| Intervention (0.6) | Interpretation (0.2) ← APEX PAIR |
| Implementation (0.7) | Detection (0.1) |
| Configuration (0.8) | Observation (0.0) |
| Governance (0.9) | Evaluation (0.4) |
| Stewardship (1.0) | Evaluation (0.4) |

## Requirements

1. **Re+ must COMPLEMENT Ac+**, not mirror it — address what Ac+ doesn't cover
2. Re+ must be a REFLECTION in the polar pair category of the given Ac+
3. Ac+ and Re+ should have similar insight levels (within 0.1-0.2)
4. **Re+ must contradict Ac-** (positive reflection opposes drift toward A-)
5. **Ac+ must contradict Re-** (positive action opposes regression toward T-)
6. Re- and Ac- typically have lower insight than the "+" aspects
7. All statements should be 1-15 words, actionable and memorable

## Example (T = Love, A = Indifference)

**Perspective aspects:**
- T+ = Bonding (healthy connection)
- T- = Enmeshment (loss of identity)
- A+ = Autonomy (healthy independence)
- A- = Alienation (disconnection)

**Ac+ (T- → A+):** "Establish personal boundaries while staying emotionally available"
- This ACTION helps escape Enmeshment toward Autonomy

**Re+ (A- → T+):** "Recognize connection needs without demanding fusion"
- This REFLECTION helps escape Alienation toward Bonding
- COMPLEMENTS Ac+ (boundaries + recognition = balanced relationship)
- Does NOT simply restate "be autonomous" — addresses the OTHER side

**Re- (A+ → T-):** "Autonomy pursued without reflection becomes cold detachment"
- Failure mode: taking Ac+ without Re+ leads back to Enmeshment patterns

**Ac- (T+ → A-):** "Bonding valued without action becomes passive withdrawal"
- Failure mode: taking Re+ without Ac+ drifts toward Alienation

Notice: Re+ contradicts Ac- (recognition vs. withdrawal), Ac+ contradicts Re- (boundaries vs. detachment).
"""


class TransitionDto(BaseModel):
    """A transition with headline, statement, and explanation."""

    headline: str = Field(description="Short headline (component length)")
    statement: str = Field(description="The transition statement (1-15 words)")
    explanation: str = Field(
        description="Full explanation of why this transition makes sense"
    )
    haiku: str = Field(description="3-line haiku capturing the transition essence")
    insight: float = Field(ge=0.0, le=1.0, description="Insight level (0.0-1.0)")
    proactiveness: float = Field(
        ge=0.0, le=1.0, description="Proactiveness level (0.0-1.0)"
    )
    insight_label: str = Field(description="Insight category label")
    proactiveness_label: str = Field(description="Proactiveness category label")


class TetradCompletionDto(BaseModel):
    """LLM response for completing a tetrad (without category reframings)."""

    # Re+ fields
    re_plus_headline: str = Field(description="Re+ headline (component length)")
    re_plus_statement: str = Field(description="Re+ statement (1-15 words)")
    re_plus_explanation: str = Field(description="How Re+ complements Ac+")
    re_plus_haiku: str = Field(description="Re+ haiku (3-line poem)")
    re_plus_insight_label: str = Field(description="Insight level for Re+")
    re_plus_proactiveness_label: str = Field(
        description="Proactiveness category for Re+"
    )

    # Re- fields
    re_minus_headline: str = Field(description="Re- headline (component length)")
    re_minus_statement: str = Field(description="Re- statement (1-15 words)")
    re_minus_explanation: str = Field(
        description="Why this is the failure mode of unguided action"
    )
    re_minus_haiku: str = Field(description="Re- haiku (3-line poem)")
    re_minus_insight_label: str = Field(description="Insight level for Re-")
    re_minus_proactiveness_label: str = Field(
        description="Proactiveness category for Re-"
    )

    # Ac- fields
    ac_minus_headline: str = Field(description="Ac- headline (component length)")
    ac_minus_statement: str = Field(description="Ac- statement (1-15 words)")
    ac_minus_explanation: str = Field(
        description="Why this is the failure mode of ungrounded reflection"
    )
    ac_minus_haiku: str = Field(description="Ac- haiku (3-line poem)")
    ac_minus_insight_label: str = Field(description="Insight level for Ac-")
    ac_minus_proactiveness_label: str = Field(
        description="Proactiveness category for Ac-"
    )


class HsScoringDto(BaseModel):
    """LLM response for HS scoring of transitions against apexes."""

    ac_plus_hs: float = Field(
        ge=0.0,
        le=1.0,
        description="Heuristic Similarity of Ac+ to the Ac+ apex (0.0-1.0)",
    )
    ac_plus_reasoning: str = Field(description="Brief reasoning for the Ac+ HS score")
    re_plus_hs: float = Field(
        ge=0.0,
        le=1.0,
        description="Heuristic Similarity of Re+ to the Re+ apex (0.0-1.0)",
    )
    re_plus_reasoning: str = Field(description="Brief reasoning for the Re+ HS score")


class CategoryReframingDto(BaseModel):
    """LLM response for contextualizing Ac and Re taxonomy categories as full transitions."""

    # Ac (neutral action category: T → A)
    ac_headline: str = Field(description="Ac headline (component length)")
    ac_statement: str = Field(description="Ac statement (1-15 words)")
    ac_explanation: str = Field(
        description="Why this reframing captures how the action category manifests"
    )
    ac_haiku: str = Field(description="Ac haiku (3-line poem)")
    ac_insight_label: str = Field(description="Insight level for Ac")
    ac_proactiveness_label: str = Field(description="Proactiveness category for Ac")

    # Re (neutral reflection category: A → T)
    re_headline: str = Field(description="Re headline (component length)")
    re_statement: str = Field(description="Re statement (1-15 words)")
    re_explanation: str = Field(
        description="Why this reframing captures how the reflection category manifests"
    )
    re_haiku: str = Field(description="Re haiku (3-line poem)")
    re_insight_label: str = Field(description="Insight level for Re")
    re_proactiveness_label: str = Field(description="Proactiveness category for Re")


class TransformationTetradDto(BaseModel):
    """Complete transformation with 6 positions: 2 neutral categories + 4 aspects."""

    # Neutral category transitions (T → A and A → T)
    ac: TransitionDto = Field(description="Neutral action category transition (T → A)")
    re: TransitionDto = Field(
        description="Neutral reflection category transition (A → T)"
    )

    # Aspect transitions
    ac_plus: TransitionDto
    re_plus: TransitionDto
    re_minus: TransitionDto
    ac_minus: TransitionDto
    ac_plus_hs: float = Field(description="Heuristic Similarity of Ac+ to apex")
    re_plus_hs: float = Field(description="Heuristic Similarity of Re+ to apex")


class TransformationGeneration(
    ReasonableConcern[TransformationTetradDto], SettingsAware
):
    """
    Concern for generating a complete transformation tetrad from an Ac+ candidate.

    Given an Ac+ (T- → A+ action), generates:
    - Re+ (A- → T+ reflection) using polar pairs
    - Re- and Ac- satisfying the Coherence Constraint
    - HS scores by comparing to derived apexes
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        edge: Transition,
        ac_plus: ActionCandidateResultDto,
        apexes: ApexDerivationResultDto,
        input_text: str = "",
    ) -> TransformationTetradDto:
        """
        Generate a complete transformation tetrad from an Ac+ candidate.

        The edge's source segment becomes the T-side context and
        the edge's target segment becomes the A-side context.

        Automatically looks up coarser-layer parent Transformations for
        hierarchical refinement context.

        Args:
            edge: The wheel edge (Transition between main statements)
            ac_plus: The Ac+ candidate to build the tetrad around
            apexes: Derived apex statements for HS calculation
            input_text: Optional source content context

        Returns:
            TransformationTetradDto with all 4 positions and HS scores
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        source_segment = edge.get_source_wheel_segment()
        target_segment = edge.get_target_wheel_segment()
        if not source_segment or not target_segment:
            raise ValueError(f"Cannot resolve segments for edge {edge.short_hash}")

        if not source_segment.is_complete() or not target_segment.is_complete():
            raise ValueError("Both segments must be complete for transformation generation")

        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        edge_context = _build_edge_context(source_segment, target_segment)

        # Look up coarser-layer parents for refinement context
        tr_repo = TransformationRepository()
        parents = tr_repo.find_parent_transformations(edge=edge)
        parent_context = self._build_coarser_context(parents)

        # Determine expected Re+ category based on Ac+ polar pair
        expected_re_category = self._get_expected_re_category(
            ac_plus.proactiveness_label
        )

        # Generate tetrad completion
        completion = await self._generate_tetrad_completion(
            edge_context, input_text, ac_plus, expected_re_category,
            parent_context=parent_context,
        )

        # Build transition DTOs
        ac_plus_dto = TransitionDto(
            headline=ac_plus.headline,
            statement=ac_plus.statement,
            insight=ac_plus.insight,
            proactiveness=ac_plus.proactiveness,
            insight_label=ac_plus.insight_label,
            proactiveness_label=ac_plus.proactiveness_label,
            explanation=ac_plus.explanation,
            haiku=ac_plus.haiku,
        )

        re_plus_dto = self._build_transition_dto(
            completion.re_plus_headline,
            completion.re_plus_statement,
            completion.re_plus_insight_label,
            completion.re_plus_proactiveness_label,
            completion.re_plus_explanation,
            completion.re_plus_haiku,
        )

        re_minus_dto = self._build_transition_dto(
            completion.re_minus_headline,
            completion.re_minus_statement,
            completion.re_minus_insight_label,
            completion.re_minus_proactiveness_label,
            completion.re_minus_explanation,
            completion.re_minus_haiku,
        )

        ac_minus_dto = self._build_transition_dto(
            completion.ac_minus_headline,
            completion.ac_minus_statement,
            completion.ac_minus_insight_label,
            completion.ac_minus_proactiveness_label,
            completion.ac_minus_explanation,
            completion.ac_minus_haiku,
        )

        # Score HS in a separate LLM call
        hs_scores = await self._score_hs(
            ac_plus.statement,
            re_plus_dto.statement,
            apexes,
        )
        ac_plus_hs = hs_scores.ac_plus_hs
        re_plus_hs = hs_scores.re_plus_hs

        # Generate category reframings in a separate LLM call (same conversation)
        category_reframings = await self._generate_category_reframings(
            ac_plus.proactiveness_label,
            expected_re_category,
        )

        # Build neutral category transitions
        ac_dto = self._build_transition_dto(
            category_reframings.ac_headline,
            category_reframings.ac_statement,
            category_reframings.ac_insight_label,
            category_reframings.ac_proactiveness_label,
            category_reframings.ac_explanation,
            category_reframings.ac_haiku,
        )
        re_dto = self._build_transition_dto(
            category_reframings.re_headline,
            category_reframings.re_statement,
            category_reframings.re_insight_label,
            category_reframings.re_proactiveness_label,
            category_reframings.re_explanation,
            category_reframings.re_haiku,
        )

        result = TransformationTetradDto(
            ac=ac_dto,
            re=re_dto,
            ac_plus=ac_plus_dto,
            re_plus=re_plus_dto,
            re_minus=re_minus_dto,
            ac_minus=ac_minus_dto,
            ac_plus_hs=ac_plus_hs,
            re_plus_hs=re_plus_hs,
        )

        # Report artifacts
        self._report.artifacts["ac_statement"] = ac_dto.statement
        self._report.artifacts["re_statement"] = re_dto.statement
        self._report.artifacts["ac_plus_statement"] = ac_plus.statement
        self._report.artifacts["re_plus_statement"] = re_plus_dto.statement
        self._report.artifacts["ac_plus_hs"] = ac_plus_hs
        self._report.artifacts["re_plus_hs"] = re_plus_hs
        self._report.summary = (
            f"Generated tetrad: Ac+ HS={ac_plus_hs:.2f}, Re+ HS={re_plus_hs:.2f}"
        )

        return result


    def _get_expected_re_category(self, ac_proactiveness_label: str) -> str:
        """Get the expected Re category based on Ac+ polar pair."""
        try:
            return get_polar_pair(ac_proactiveness_label)
        except ValueError:
            # Default to Interpretation if no polar pair found
            return "Interpretation"

    def _build_coarser_context(
        self, parents: list[CoarserTransformation]
    ) -> Optional[str]:
        """
        Build hierarchical refinement context from coarser parent Transformations.

        Parents are ordered coarsest-first. Each represents a broader transition
        that the current edge is a sub-step of.

        Returns:
            Formatted string for LLM prompt, or None if no parents
        """
        if not parents:
            return None

        parts = []
        current_edge_id = None

        for ct in parents:
            tr = ct.transformation

            edge_result = tr.edge.get()
            if not edge_result:
                continue
            tr_edge, _ = edge_result

            edge_source = tr_edge.source.get()
            edge_target = tr_edge.target.get()
            if not edge_source or not edge_target:
                continue

            source_text = edge_source[0].text
            target_text = edge_target[0].text

            indent = "  " * (ct.layer - 1)

            if tr_edge._id != current_edge_id:
                current_edge_id = tr_edge._id
                parts.append(f"{indent}\"{source_text}\" → \"{target_text}\":")
            else:
                parts.append(f"{indent}(variant):")

            ac_plus_result = tr.ac_plus.get()
            if ac_plus_result:
                trans, _ = ac_plus_result
                parts.append(f"{indent}  Action: {trans.instruction}")

            re_plus_result = tr.re_plus.get()
            if re_plus_result:
                trans, _ = re_plus_result
                parts.append(f"{indent}  Reflection: {trans.instruction}")

        return "\n".join(parts) if parts else None

    async def _generate_tetrad_completion(
        self,
        edge_context: str,
        input_text: str,
        ac_plus: ActionCandidateResultDto,
        expected_re_category: str,
        parent_context: Optional[str] = None,
    ) -> TetradCompletionDto:
        """Generate the remaining tetrad positions from Ac+."""
        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        parent_section = ""
        if parent_context:
            parent_section = f"""
<broader_journey>
Your current edge is one detailed sub-step within a broader transition.
Below is the hierarchy from broadest to most specific (indented = more detailed):

{parent_context}

Your tetrad details one sub-step of the most-indented transition above.
Be more concrete and specific than the broader path, while staying coherent
with its overall direction.
</broader_journey>

"""

        prompt = f"""{context_section}{parent_section}Given this Perspective:

<perspective>
{edge_context}
</perspective>

And this Ac+ (action targeting A+) statement:
- Statement: "{ac_plus.statement}"
- Insight: {ac_plus.insight_label} ({ac_plus.insight})
- Proactiveness: {ac_plus.proactiveness_label} ({ac_plus.proactiveness})

Complete the transformation tetrad.

For each position, provide:
- A **headline** (~{self.settings.component_length} words) - short, memorable essence
- A **statement** (1-15 words) - fuller actionable description
- An **explanation** - why this transition makes sense

## 1. Re+ (reflection targeting T+)

Generate a COMPLEMENTARY reflection at the {expected_re_category.upper()} proactiveness level.
- Re+ guides the A- → T+ path (escaping A's problems toward T's benefits)
- **CRITICAL**: Re+ must COMPLEMENT Ac+, not mirror it — address what Ac+ doesn't cover
- Together, Ac+ and Re+ should form a complete solution (circular causality for S+)
- Insight should be similar to Ac+ (~{ac_plus.insight_label})
- Re+ must CONTRADICT Ac- (the positive reflection opposes drift toward A-)

## 2. Re- (reflection targeting T-)

What happens when Ac+ is taken WITHOUT Re+?
- Describes regression toward T- when action lacks guiding reflection
- Ac+ must CONTRADICT Re- (the positive action opposes this regression)
- Usually lower insight than Re+

## 3. Ac- (action targeting A-)

What happens when Re+ is taken WITHOUT Ac+?
- Describes drift toward A- when reflection lacks grounding action
- Re+ must CONTRADICT Ac- (the positive reflection opposes this drift)
- Usually lower insight than Ac+

Requirements:
- Headlines ~{self.settings.component_length} words, statements 1-15 words
- For each position, also produce a haiku (3 lines, 5-7-5 syllables) — easy to memorize
- Re+ must be in the {expected_re_category} category (polar pair of {ac_plus.proactiveness_label})
- Re+ must genuinely complement Ac+ (address DIFFERENT aspects of the tension)
- Diagonal contradictions: Re+ vs Ac-, Ac+ vs Re-"""

        return await self._conversation.submit(
            response_model=TetradCompletionDto,
            user_content=prompt,
        )

    async def _score_hs(
        self,
        ac_plus_statement: str,
        re_plus_statement: str,
        apexes: ApexDerivationResultDto,
    ) -> HsScoringDto:
        """Score HS for Ac+ and Re+ against their respective apexes."""
        prompt = f"""Score the Heuristic Similarity (HS) for these transitions against their apex statements.

## Transitions to Score

**Ac+ transition**: "{ac_plus_statement}"
**Ac+ apex**: "{apexes.ac_plus_apex.statement}"

**Re+ transition**: "{re_plus_statement}"
**Re+ apex**: "{apexes.re_plus_apex.statement}"

## HS (Heuristic Similarity) Scale

HS measures how well a transition captures the essence of its apex statement:
- 0.0-0.3: Unrelated or tangentially related to the apex
- 0.3-0.5: Somewhat related but different focus or aspect
- 0.5-0.7: Related, captures some key aspects of the apex
- 0.7-0.9: Very similar, captures most aspects of the apex
- 0.9-1.0: Equivalent or near-equivalent to the apex concept

Score each transition by comparing its semantic meaning to the corresponding apex."""

        return await self._conversation.submit(
            response_model=HsScoringDto,
            user_content=prompt,
        )

    async def _generate_category_reframings(
        self,
        ac_category: str,
        re_category: str,
    ) -> CategoryReframingDto:
        """Generate contextualized category reframings for Ac and Re as full transitions."""
        prompt = f"""Now generate the neutral category transitions for this transformation.

These are the T ↔ A transitions that contextualize the taxonomy categories:

## Ac (Action category: T → A): {ac_category}
Generate a transition that describes how "{ac_category}" specifically manifests in this T-A polarity.
- Example: For Love/Indifference, "Intervention" → "Boundary-setting intervention"
- This is a NEUTRAL action category (not + or -), describing the general T → A movement

## Re (Reflection category: A → T): {re_category}
Generate a transition that describes how "{re_category}" specifically manifests in this A-T polarity.
- Example: For Love/Indifference, "Interpretation" → "Connection needs interpretation"
- This is a NEUTRAL reflection category (not + or -), describing the general A → T movement

For each, provide:
- **headline** (~{self.settings.component_length} words) - short, memorable reframing
- **statement** (1-15 words) - fuller description of the contextualized category
- **explanation** - why this reframing captures how the category operates here
- **haiku** (3 lines, 5-7-5 syllables) - poetic capture of the category's essence
- **insight_label** and **proactiveness_label** - should match the base category"""

        return await self._conversation.submit(
            response_model=CategoryReframingDto,
            user_content=prompt,
        )

    def _build_transition_dto(
        self,
        headline: str,
        statement: str,
        insight_label: str,
        proactiveness_label: str,
        explanation: str,
        haiku: str,
    ) -> TransitionDto:
        """Build a TransitionDto with numeric coordinates."""
        insight_label_key = insight_label.capitalize()
        proactiveness_label_key = proactiveness_label.capitalize()

        try:
            insight = insight_label_to_value(insight_label_key)
        except ValueError:
            insight = INSIGHT_SCALE["Composition"]  # Midpoint default

        try:
            proactiveness = proactiveness_label_to_value(proactiveness_label_key)
        except ValueError:
            proactiveness = PROACTIVENESS_SCALE["Evaluation"]  # Midpoint default

        return TransitionDto(
            headline=headline,
            statement=statement,
            insight=insight,
            proactiveness=proactiveness,
            insight_label=insight_label_key,
            proactiveness_label=proactiveness_label_key,
            explanation=explanation,
            haiku=haiku,
        )
