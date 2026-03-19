"""
TransformationGeneration: Capability for generating a full transformation tetrad from an Ac+ candidate.

Given an Ac+ candidate, generates the complementary Re+, and the negative poles Re- and Ac-
following the Coherence Constraint (CC).

Usage:
    service = TransformationGeneration()
    tetrad = await service.execute(wu, ac_plus, apexes, input_text)
    print(f"Ac+: {tetrad.ac_plus.statement}")
    print(f"Re+: {tetrad.re_plus.statement}")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import (
    ConversationFacilitator,
)
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.sensemaking.capabilities.positive_ac_re_apex_derivation import (
    ApexDerivationResultDto,
)
from dialectical_framework.agents.sensemaking.capabilities.ac_re_taxonomy import (
    INSIGHT_SCALE,
    PROACTIVENESS_SCALE,
    get_polar_pair,
    insight_label_to_value,
    proactiveness_label_to_value,
)
from dialectical_framework.agents.sensemaking.capabilities.action_extraction import (
    ActionCandidateResultDto,
)
from dialectical_framework.protocols.has_config import SettingsAware

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


SYSTEM_PROMPT = """You are an expert in dialectical reasoning, specializing in Action-Reflection transformations.

Your task is to complete a transformation tetrad given an Ac+ (Positive Action) statement.

## Transformation Structure

A transformation has 4 key positions:
- Ac+ (given): T- → A+ path (action escaping T's problems toward A's benefits)
- Re+: A- → T+ path (reflection escaping A's problems toward T's benefits)
- Re-: What happens when Ac+ is taken WITHOUT adequate Re+ (action without reflection)
- Ac-: What happens when Re+ is taken WITHOUT adequate Ac+ (reflection without action)

## Coherence Constraint (CC)

The negative poles must satisfy:
- Re-: "Ac+ without Re+ yields Re-" — taking action without reflection leads to this problem
- Ac-: "Re+ without Ac+ yields Ac-" — reflecting without action leads to this problem

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

1. Re+ must be a REFLECTION in the polar pair category of the given Ac+
2. Ac+ and Re+ should have similar insight levels (within 0.1-0.2)
3. Re- and Ac- typically have lower insight than their positive counterparts
4. Re- describes the failure mode of action-without-reflection
5. Ac- describes the failure mode of reflection-without-action
6. All statements should be 1-15 words, actionable and memorable
"""


class TransitionDto(BaseModel):
    """A transition with headline, statement, and explanation."""

    headline: str = Field(description="Short headline (component length)")
    statement: str = Field(description="The transition statement (1-15 words)")
    explanation: str = Field(description="Full explanation of why this transition makes sense")
    insight: float = Field(ge=0.0, le=1.0, description="Insight level (0.0-1.0)")
    proactiveness: float = Field(
        ge=0.0, le=1.0, description="Proactiveness level (0.0-1.0)"
    )
    insight_label: str = Field(description="Insight category label")
    proactiveness_label: str = Field(description="Proactiveness category label")


class TetradCompletionDto(BaseModel):
    """LLM response for completing a tetrad."""

    # Neutral category reframings (contextualized taxonomy categories, component length)
    ac_category_reframing: str = Field(
        description="Contextualized action category (component length, e.g., 'Boundary-setting intervention')"
    )
    re_category_reframing: str = Field(
        description="Contextualized reflection category (component length, e.g., 'Connection needs interpretation')"
    )

    # Re+ fields
    re_plus_headline: str = Field(description="Re+ headline (component length)")
    re_plus_statement: str = Field(description="Re+ statement (1-15 words)")
    re_plus_explanation: str = Field(description="How Re+ complements Ac+")
    re_plus_insight_label: str = Field(description="Insight level for Re+")
    re_plus_proactiveness_label: str = Field(description="Proactiveness category for Re+")

    # Re- fields
    re_minus_headline: str = Field(description="Re- headline (component length)")
    re_minus_statement: str = Field(description="Re- statement (1-15 words)")
    re_minus_explanation: str = Field(description="Why this is the failure mode of unguided action")
    re_minus_insight_label: str = Field(description="Insight level for Re-")
    re_minus_proactiveness_label: str = Field(description="Proactiveness category for Re-")

    # Ac- fields
    ac_minus_headline: str = Field(description="Ac- headline (component length)")
    ac_minus_statement: str = Field(description="Ac- statement (1-15 words)")
    ac_minus_explanation: str = Field(description="Why this is the failure mode of ungrounded reflection")
    ac_minus_insight_label: str = Field(description="Insight level for Ac-")
    ac_minus_proactiveness_label: str = Field(description="Proactiveness category for Ac-")


class HsScoringDto(BaseModel):
    """LLM response for HS scoring of transitions against apexes."""

    ac_plus_hs: float = Field(
        ge=0.0, le=1.0,
        description="Heuristic Similarity of Ac+ to the Ac+ apex (0.0-1.0)"
    )
    ac_plus_reasoning: str = Field(
        description="Brief reasoning for the Ac+ HS score"
    )
    re_plus_hs: float = Field(
        ge=0.0, le=1.0,
        description="Heuristic Similarity of Re+ to the Re+ apex (0.0-1.0)"
    )
    re_plus_reasoning: str = Field(
        description="Brief reasoning for the Re+ HS score"
    )


class TransformationTetradDto(BaseModel):
    """Complete transformation with 4 poles and 2 neutral category reframings."""

    # Neutral category reframings (T → A and A → T)
    ac_category_reframing: str = Field(
        description="Contextualized action category (e.g., 'Intervening through boundary-setting')"
    )
    re_category_reframing: str = Field(
        description="Contextualized reflection category (e.g., 'Interpreting connection needs')"
    )

    # Pole transitions
    ac_plus: TransitionDto
    re_plus: TransitionDto
    re_minus: TransitionDto
    ac_minus: TransitionDto
    ac_plus_hs: float = Field(description="Heuristic Similarity of Ac+ to apex")
    re_plus_hs: float = Field(description="Heuristic Similarity of Re+ to apex")


class TransformationGeneration(
    ExecutableCapability[TransformationTetradDto], SettingsAware
):
    """
    Capability for generating a complete transformation tetrad from an Ac+ candidate.

    Given an Ac+ (T- → A+ action), generates:
    - Re+ (A- → T+ reflection) using polar pairs
    - Re- and Ac- satisfying the Coherence Constraint
    - HS scores by comparing to derived apexes
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def execute(
        self,
        wu: WisdomUnit,
        ac_plus: ActionCandidateResultDto,
        apexes: ApexDerivationResultDto,
        input_text: str = "",
    ) -> TransformationTetradDto:
        """
        Generate a complete transformation tetrad from an Ac+ candidate.

        Args:
            wu: The WisdomUnit context
            ac_plus: The Ac+ candidate to build the tetrad around
            apexes: Derived apex statements for HS calculation
            input_text: Optional source content context

        Returns:
            TransformationTetradDto with all 4 positions and HS scores
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not wu.is_complete():
            raise ValueError("WisdomUnit must have all 6 positions")

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Get WU context
        wu_context = self._build_wu_context(wu)

        # Determine expected Re+ category based on Ac+ polar pair
        expected_re_category = self._get_expected_re_category(
            ac_plus.proactiveness_label
        )

        # Generate tetrad completion
        completion = await self._generate_tetrad_completion(
            wu_context, input_text, ac_plus, expected_re_category
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
        )

        re_plus_dto = self._build_transition_dto(
            completion.re_plus_headline,
            completion.re_plus_statement,
            completion.re_plus_insight_label,
            completion.re_plus_proactiveness_label,
            completion.re_plus_explanation,
        )

        re_minus_dto = self._build_transition_dto(
            completion.re_minus_headline,
            completion.re_minus_statement,
            completion.re_minus_insight_label,
            completion.re_minus_proactiveness_label,
            completion.re_minus_explanation,
        )

        ac_minus_dto = self._build_transition_dto(
            completion.ac_minus_headline,
            completion.ac_minus_statement,
            completion.ac_minus_insight_label,
            completion.ac_minus_proactiveness_label,
            completion.ac_minus_explanation,
        )

        # Score HS in a separate LLM call
        hs_scores = await self._score_hs(
            ac_plus.statement,
            re_plus_dto.statement,
            apexes,
        )
        ac_plus_hs = hs_scores.ac_plus_hs
        re_plus_hs = hs_scores.re_plus_hs

        result = TransformationTetradDto(
            ac_category_reframing=completion.ac_category_reframing,
            re_category_reframing=completion.re_category_reframing,
            ac_plus=ac_plus_dto,
            re_plus=re_plus_dto,
            re_minus=re_minus_dto,
            ac_minus=ac_minus_dto,
            ac_plus_hs=ac_plus_hs,
            re_plus_hs=re_plus_hs,
        )

        # Report artifacts
        self._report.artifacts["ac_category_reframing"] = completion.ac_category_reframing
        self._report.artifacts["re_category_reframing"] = completion.re_category_reframing
        self._report.artifacts["ac_plus_statement"] = ac_plus.statement
        self._report.artifacts["re_plus_statement"] = re_plus_dto.statement
        self._report.artifacts["ac_plus_hs"] = ac_plus_hs
        self._report.artifacts["re_plus_hs"] = re_plus_hs
        self._report.summary = (
            f"Generated tetrad: Ac+ HS={ac_plus_hs:.2f}, Re+ HS={re_plus_hs:.2f}"
        )

        return result

    def _build_wu_context(self, wu: WisdomUnit) -> str:
        """Build context string from WisdomUnit components."""
        parts = []

        positions = [
            ("T", wu.t),
            ("T+", wu.t_plus),
            ("T-", wu.t_minus),
            ("A", wu.a),
            ("A+", wu.a_plus),
            ("A-", wu.a_minus),
        ]

        for name, manager in positions:
            result = manager.get()
            if result:
                comp, _ = result
                parts.append(f"{name}: {comp.statement}")

        return "\n".join(parts)

    def _get_expected_re_category(self, ac_proactiveness_label: str) -> str:
        """Get the expected Re category based on Ac+ polar pair."""
        try:
            return get_polar_pair(ac_proactiveness_label)
        except ValueError:
            # Default to Interpretation if no polar pair found
            return "Interpretation"

    async def _generate_tetrad_completion(
        self,
        wu_context: str,
        input_text: str,
        ac_plus: ActionCandidateResultDto,
        expected_re_category: str,
    ) -> TetradCompletionDto:
        """Generate the remaining tetrad positions from Ac+."""
        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        prompt = f"""{context_section}Given this dialectical polarity:

<wisdom_unit>
{wu_context}
</wisdom_unit>

And this Ac+ (Positive Action) statement:
- Statement: "{ac_plus.statement}"
- Insight: {ac_plus.insight_label} ({ac_plus.insight})
- Proactiveness: {ac_plus.proactiveness_label} ({ac_plus.proactiveness})

Complete the transformation:

## Category Reframings (contextualize the taxonomy categories)

1. **Ac (Action category)**: Contextualize "{ac_plus.proactiveness_label}" for this specific T-A polarity.
   - Example: "Intervention" → "Intervening through boundary-setting"
   - The reframing should describe how {ac_plus.proactiveness_label} manifests in this context

2. **Re (Reflection category)**: Contextualize "{expected_re_category}" for this specific T-A polarity.
   - Example: "Interpretation" → "Interpreting connection needs"
   - The reframing should describe how {expected_re_category} manifests in this context

## Tetrad Completion

For each position, provide:
- A **headline** (~{self.settings.component_length} words) - short, memorable essence
- A **statement** (1-15 words) - fuller actionable description
- An **explanation** - why this transition makes sense

3. **Re+** (Positive Reflection): Generate a complementary reflection at the {expected_re_category.upper()} proactiveness level.
   - Re+ should guide the A- → T+ path
   - Insight should be similar to the one of Ac+ (~{ac_plus.insight_label})
   - This reflection gives meaning and direction to the action

4. **Re-** (Negative Reflection): What happens when Ac+ is taken WITHOUT Re+?
   - "Action without reflection" failure mode
   - Usually lower insight than Re+

5. **Ac-** (Negative Action): What happens when Re+ is taken WITHOUT Ac+?
   - "Reflection without action" failure mode
   - Usually lower insight than Ac+

Requirements:
- Headlines ~{self.settings.component_length} words, statements 1-15 words
- Re+ must be in the {expected_re_category} category (polar pair of {ac_plus.proactiveness_label})
- Negative poles describe failure modes, not opposites"""

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

    def _build_transition_dto(
        self,
        headline: str,
        statement: str,
        insight_label: str,
        proactiveness_label: str,
        explanation: str,
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
        )

