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
from dialectical_framework.graph.repositories.transformation_repository import \
    TransformationRepository
from dialectical_framework.utils.edge_context import (
    REFINE_REFLECTION, REFINE_TETRAD, build_coarser_context,
    build_edge_context, coarser_journey_section)
from dialectical_framework.concerns.positive_ac_re_apex_derivation import \
    ApexDerivationResultDto
from dialectical_framework.concerns.scoring_scales import HS_SCALE
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.utils.progress import report_progress

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition


SYSTEM_PROMPT = """You are an expert in dialectical reasoning, specializing in Action-Reflection transformations.

Your task is to generate a transformation tetrad. A transformation captures BOTH your action AND how the opposite side's action reflects back on you.

## Two-Perspective Model

Every wheel edge has a diametrically opposite edge. A transformation uses BOTH:

- **Action Perspective** (this edge): Where you ACT. Ac, Ac+, Ac- are generated from this context.
- **Reflection Perspective** (opposite edge): Where the OTHER SIDE acts. Re, Re+, Re- respond to their action.

In a 1-PP wheel (e.g., Love/Hate), the same nodes appear on both sides but carry different semantic content — "my action toward independence" vs "their reconnection action that grounds me."

## Transformation Structure

The +/- notation is STRUCTURAL (like electrical charges), not a value judgment:
- "+" transitions target beneficial states
- "-" transitions target problematic states

**Action side** (from Action Perspective):
- **Ac+**: source.neg → target.pos (escaping your problems toward their benefits)
- **Ac-**: source.pos → target.neg (your strength wasted — what Ac itself degenerates into when Re+ is absent)

**Reflection side** (from Reflection Perspective, responding to opposite Ac+):
- **Re+**: opp_source.neg → opp_target.pos (how their action grounds you toward growth)
- **Re-**: opp_source.pos → opp_target.neg (their opening squandered — what Re itself degenerates into when Ac+ is absent)

## Circular Causality: Why Ac+ and Re+ Must Be Complementary

Positive synthesis (S+) emerges ONLY when Ac+ and Re+ work together:
- Ac+ alone (action never grounded in reflection on the other side) degenerates into Ac-
- Re+ alone (reflection never grounded in your own action) degenerates into Re-

Together, they form a closed loop — your action + awareness of the other side's action = self-regulation.

**Re+ should NOT simply restate or mirror Ac+.** It must be a genuinely complementary reflection that:
- Responds to what the OPPOSITE SIDE is doing (their Ac+)
- Addresses what YOUR action doesn't cover
- Could stand alone as valuable insight grounded in the other side's dynamics

**Never propose direct reinforcement of a "+" aspect.** Strengthening T+ head-on also strengthens A- and flips T+ into T- (one-sided overdevelopment). Transformations work indirectly: they transform the "-" of one side into the "+" of the other, never pump a "+" directly.

**Forcefulness reverses polarity.** Ac+ and Re+ must stay subtle and flexible enough to balance each other — an Ac+ or Re+ that imposes, coerces, or overpowers stops being "+" and becomes its "-" counterpart. When a candidate reads as forcing an outcome rather than enabling it, soften it or reject it.

## Diagonal Contradictions

The tetrad has diagonal contradictions that must be preserved:
- **Re+ must contradict Ac-**: The positive reflection opposes the drift toward A-
- **Ac+ must contradict Re-**: The positive action opposes regression toward T-

## Coherence Constraint (CC)

The "-" aspects describe failure modes when transitions are unbalanced. The
SUBJECT is preserved and its own polarity flips — the same form as the aspect
tetrad's "T+ without A+ yields T-":
- Ac-: "Ac+ without Re+ yields Ac-" — action never grounded in reflection overextends into wasted strength
- Re-: "Re+ without Ac+ yields Re-" — reflection never grounded in action overextends into regression

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
7. Statements are a fuller actionable form, longer than the headline
8. In headline/statement/explanation prose, refer to concepts by their actual statement wording — never by T/A/T+/A-/Ac+/Re- notation. The notation is context-relative and meaningless to anyone reading the stored text later.

## Example (1-PP: T = Love, A = Indifference)

**Action Perspective** (edge Love→Indifference):
- T = Love, T+ = Bonding, T- = Enmeshment
- A = Indifference, A+ = Autonomy, A- = Alienation

**Reflection Perspective** (opposite edge Indifference→Love):
- T = Indifference, T+ = Autonomy, T- = Alienation
- A = Love, A+ = Bonding, A- = Enmeshment

**Opposite side's Ac+ (their action, Alienation → Bonding):**
"Recognize isolation patterns to rebuild genuine connection"

**Your Ac+ (T- → A+, Enmeshment → Autonomy):**
"Establish personal boundaries while staying emotionally available"

**Your Re+ (A- → T+, Alienation → Bonding) — responding to their Ac+:**
"Let their reaching toward you rekindle the closeness you'd let grow cold"
- Responds to THEIR action (reconnection) by moving YOU from alienation toward bonding
- COMPLEMENTS your Ac+: boundaries build autonomy, this rekindles bonding — together you hold both poles (S+)
- Does NOT mirror Ac+ — Ac+ moves toward autonomy, Re+ moves toward bonding

**Ac- (T+ → A-, Bonding → Alienation):** "Drawing the line on your own terms, never taking their reaching in, hardens closeness into distance"
- What Ac+ ITSELF degenerates into when Re+ is absent: the boundaries stay, the emotional availability drops out
- Ac+ without Re+ yields Ac- — your action left unreflected, overextended into wasted strength

**Re- (A+ → T-, Autonomy → Enmeshment):** "Dwelling on their reaching with no move of your own lets independence collapse into clinging"
- What Re+ ITSELF degenerates into when Ac+ is absent: their opening is taken in and then squandered
- Re+ without Ac+ yields Re- — your reflection left unacted, overextended into regression

Notice: Re+ contradicts Ac- (rekindling closeness vs. hardening it into distance), Ac+ contradicts Re- (boundaries you actually set vs. reaching you only dwell on).
"""


class TransitionDto(BaseModel):
    """A transition with headline, statement, and explanation."""

    headline: str = Field(description="Short headline (component length)")
    statement: str = Field(description="The transition statement (fuller than the headline)")
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


class AcMinusCompletionDto(BaseModel):
    """LLM response for generating Ac- (action failure mode)."""

    ac_minus_headline: str = Field(description="Ac- headline (component length)")
    ac_minus_statement: str = Field(description="Ac- statement (fuller than the headline)")
    ac_minus_explanation: str = Field(
        description="Why this is what the action itself degenerates into when reflection is absent"
    )
    ac_minus_haiku: str = Field(description="Ac- haiku (3-line poem)")
    ac_minus_insight_label: str = Field(description="Insight level for Ac-")
    ac_minus_proactiveness_label: str = Field(
        description="Proactiveness category for Ac-"
    )


class ReSideCompletionDto(BaseModel):
    """LLM response for generating Re+ and Re- from opposite edge context."""

    # Re+ fields
    re_plus_headline: str = Field(description="Re+ headline (component length)")
    re_plus_statement: str = Field(description="Re+ statement (fuller than the headline)")
    re_plus_explanation: str = Field(description="How Re+ responds to the opposite action")
    re_plus_haiku: str = Field(description="Re+ haiku (3-line poem)")
    re_plus_insight_label: str = Field(description="Insight level for Re+")
    re_plus_proactiveness_label: str = Field(
        description="Proactiveness category for Re+"
    )

    # Re- fields
    re_minus_headline: str = Field(description="Re- headline (component length)")
    re_minus_statement: str = Field(description="Re- statement (fuller than the headline)")
    re_minus_explanation: str = Field(
        description="Why this is what the reflection itself degenerates into when action is absent"
    )
    re_minus_haiku: str = Field(description="Re- haiku (3-line poem)")
    re_minus_insight_label: str = Field(description="Insight level for Re-")
    re_minus_proactiveness_label: str = Field(
        description="Proactiveness category for Re-"
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
    ac_statement: str = Field(description="Ac statement (fuller than the headline)")
    ac_explanation: str = Field(
        description="Why this reframing captures how the action category manifests"
    )
    ac_haiku: str = Field(description="Ac haiku (3-line poem)")
    ac_insight_label: str = Field(description="Insight level for Ac")
    ac_proactiveness_label: str = Field(description="Proactiveness category for Ac")

    # Re (neutral reflection category: the opposite edge's T → A)
    re_headline: str = Field(description="Re headline (component length)")
    re_statement: str = Field(description="Re statement (fuller than the headline)")
    re_explanation: str = Field(
        description="Why this reframing captures how the reflection category manifests"
    )
    re_haiku: str = Field(description="Re haiku (3-line poem)")
    re_insight_label: str = Field(description="Insight level for Re")
    re_proactiveness_label: str = Field(description="Proactiveness category for Re")


class TransformationTetradDto(BaseModel):
    """Complete transformation with 6 positions: 2 neutral categories + 4 aspects."""

    # Neutral category transitions (this edge's T → A, and the opposite edge's T → A)
    ac: TransitionDto = Field(
        description="Neutral action category transition (this edge's T → A)"
    )
    re: TransitionDto = Field(
        description="Neutral reflection category transition (the opposite edge's T → A)"
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

    Given an Ac+ (this edge's T- → A+ action), generates:
    - Re+ (the opposite edge's T- → A+ reflection) using polar pairs
    - Re- and Ac- satisfying the Coherence Constraint
    - HS scores by comparing to derived apexes
    """

    #: How many progress steps one `resolve()` reports. Callers multiply by their
    #: tetrad count to get a denominator, so this MUST equal the number of
    #: `report_progress` calls below — `TestProgressStepsMatchesTheCalls` asserts it,
    #: because drift here silently corrupts every progress bar rather than failing.
    PROGRESS_STEPS = 4

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        edge: Transition,
        ac_plus: ActionCandidateResultDto,
        opposite_ac_plus: ActionCandidateResultDto,
        apexes: ApexDerivationResultDto,
        input_text: str = "",
        parent_context: Optional[str] = None,
    ) -> TransformationTetradDto:
        """
        Generate a complete transformation tetrad from an Ac+ candidate.

        The Ac-side (Ac, Ac+, Ac-) uses this edge's context.
        The Re-side (Re, Re+, Re-) uses the opposite edge's context,
        derived via source_segment.opposite / target_segment.opposite.

        Args:
            edge: The wheel edge (Transition between main statements)
            ac_plus: The Ac+ candidate for this edge
            opposite_ac_plus: The Ac+ from the opposite edge (grounds Re-side)
            apexes: Derived apex statements for HS calculation
            input_text: Optional source content context
            parent_context: Rendered coarser-layer refinement context. Passed in
                by a caller that already looked it up for THIS edge — the Ac+ that
                becomes this tetrad's own first position was generated against the
                same string, and re-deriving it here would ask the same question
                once per candidate (three times an edge) for an answer that cannot
                have changed: parents live on strictly coarser wheels, which the
                climb commits in an earlier rung behind a barrier. None means look
                it up, so a direct caller keeps working.

        Returns:
            TransformationTetradDto with all 6 positions and HS scores
        """

        source_segment = edge.get_source_wheel_segment()
        target_segment = edge.get_target_wheel_segment()
        if not source_segment or not target_segment:
            raise ValueError(f"Cannot resolve segments for edge {edge.short_hash}")

        if not source_segment.is_complete() or not target_segment.is_complete():
            raise ValueError("Both segments must be complete for transformation generation")

        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        edge_context = build_edge_context(source_segment, target_segment)
        opposite_edge_context = build_edge_context(
            source_segment.opposite, target_segment.opposite
        )

        # Look up coarser-layer parents for refinement context, unless the caller
        # already did it for this edge (see `parent_context` in the docstring).
        if parent_context is None:
            tr_repo = TransformationRepository()
            parents = tr_repo.find_parent_transformations(edge=edge)
            parent_context = build_coarser_context(parents)

        # Determine expected Re+ category based on Ac+ polar pair
        expected_re_category = self._get_expected_re_category(
            ac_plus.proactiveness_label
        )

        # The four `report_progress` calls below are the ONLY thing a person can see
        # during this chain: nothing here writes a graph node, so no `Effect` reaches
        # the bus until `_create_transformation` runs after the last of them. That is
        # what made `explore`'s transformation phase 45.6s of silence.
        #
        # `detail` carries NO framework vocabulary — no T+/A-, no Ac/Re, no insight
        # band. A host may render it verbatim, and the silent Advisor's whole contract
        # is that the machinery stays hidden (CLAUDE.md, "User-Facing Vocabulary is
        # App-Layer"). Plain description of the activity only.

        # Generate Ac- (this-edge context)
        report_progress("Working out how this move can overshoot")
        ac_minus_completion = await self._generate_ac_minus(
            edge_context, input_text, ac_plus, parent_context=parent_context,
        )

        # Generate Re+, Re- (opposite-edge context + opposite Ac+)
        #
        # `parent_context` is handed over explicitly even though this call shares
        # `self._conversation` with the Ac- one above, so the hierarchy is already
        # in history. In the window is not the same as being ASKED to refine from
        # it: measured, this call read `<broader_journey>` from history and had no
        # instruction pointing at it, so it refined by accident of ordering — and
        # nothing enforces that Ac- runs first, nor that a future edit does not
        # `isolate()` this call the way `ActionExtraction` does. It now names the
        # `Reflection:` line it descends from, which history alone cannot do.
        report_progress("Working out the answering move")
        re_side_completion = await self._generate_re_side(
            opposite_edge_context, opposite_ac_plus, ac_plus,
            expected_re_category, parent_context=parent_context,
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
            re_side_completion.re_plus_headline,
            re_side_completion.re_plus_statement,
            re_side_completion.re_plus_insight_label,
            re_side_completion.re_plus_proactiveness_label,
            re_side_completion.re_plus_explanation,
            re_side_completion.re_plus_haiku,
        )

        re_minus_dto = self._build_transition_dto(
            re_side_completion.re_minus_headline,
            re_side_completion.re_minus_statement,
            re_side_completion.re_minus_insight_label,
            re_side_completion.re_minus_proactiveness_label,
            re_side_completion.re_minus_explanation,
            re_side_completion.re_minus_haiku,
        )

        ac_minus_dto = self._build_transition_dto(
            ac_minus_completion.ac_minus_headline,
            ac_minus_completion.ac_minus_statement,
            ac_minus_completion.ac_minus_insight_label,
            ac_minus_completion.ac_minus_proactiveness_label,
            ac_minus_completion.ac_minus_explanation,
            ac_minus_completion.ac_minus_haiku,
        )

        # Score HS in a separate LLM call.
        #
        # NO `parent_context`, and that is deliberate rather than an oversight left
        # over from the two calls above. This is a judgement against the apexes, and
        # transition-level HS is stored on the relationship and rendered to the
        # advisor as evidence (it does NOT gate — `HS_THRESHOLD` is polarity-level
        # only, see `analyst.py` / `dialectical_context.py`). A score nudged by "be more
        # concrete than the broader path" is a different class of defect from an
        # unrefined statement. It shares `self._conversation`, so the hierarchy is in
        # its window regardless; what a prompt controls is whether anything ASKS it
        # to score against the ancestry, and nothing should. Same for the category
        # reframings below, which derive from positions already refined.
        # Pinned by tests/test_refinement_context.py.
        report_progress("Scoring how well the pair holds together")
        hs_scores = await self._score_hs(
            ac_plus.statement,
            re_plus_dto.statement,
            apexes,
        )
        ac_plus_hs = hs_scores.ac_plus_hs
        re_plus_hs = hs_scores.re_plus_hs

        # Generate category reframings (Ac from this-edge, Re from opposite-edge)
        report_progress("Naming what kind of move this is")
        category_reframings = await self._generate_category_reframings(
            ac_plus.proactiveness_label,
            expected_re_category,
            opposite_edge_context,
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

    async def _generate_ac_minus(
        self,
        edge_context: str,
        input_text: str,
        ac_plus: ActionCandidateResultDto,
        parent_context: Optional[str] = None,
    ) -> AcMinusCompletionDto:
        """Generate Ac- (what the action degenerates into when grounding reflection is absent)."""
        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        parent_section = coarser_journey_section(parent_context, REFINE_TETRAD)

        prompt = f"""{context_section}{parent_section}Given this Action Perspective:

<action_perspective>
{edge_context}
</action_perspective>

And this Ac+ (positive action: T- → A+):
- Statement: "{ac_plus.statement}"
- Insight: {ac_plus.insight_label} ({ac_plus.insight})
- Proactiveness: {ac_plus.proactiveness_label} ({ac_plus.proactiveness})

Generate Ac- (the action failure mode: T+ → A-).

## Ac- (action targeting A-)

What happens when the action is taken WITHOUT the reflection that grounds it?
- What Ac+ ITSELF degenerates into when Re+ is absent — an overextension of the action, not merely a bad action
- The path from T+ (strength) toward A- (problem) — strength wasted
- Usually lower insight than Ac+

Requirements:
- Headline ~{self.settings.component_length} words, statement up to {self.settings.transition_length} words
- Produce a haiku (3 lines, 5-7-5 syllables)
- Ac- must be something that Re+ can CONTRADICT (positive reflection opposes this drift)"""

        return await self._conversation.submit(
            response_model=AcMinusCompletionDto,
            user_content=prompt,
        )

    async def _generate_re_side(
        self,
        opposite_edge_context: str,
        opposite_ac_plus: ActionCandidateResultDto,
        own_ac_plus: ActionCandidateResultDto,
        expected_re_category: str,
        parent_context: Optional[str] = None,
    ) -> ReSideCompletionDto:
        """Generate Re+ and Re- from the opposite edge's context and action."""
        parent_section = coarser_journey_section(parent_context, REFINE_REFLECTION)

        prompt = f"""{parent_section}Now consider the opposite edge — the other side's dynamics that ground your reflection.

<reflection_perspective>
{opposite_edge_context}
</reflection_perspective>

The opposite side has taken this action (their Ac+):
- Statement: "{opposite_ac_plus.statement}"
- Insight: {opposite_ac_plus.insight_label} ({opposite_ac_plus.insight})
- Proactiveness: {opposite_ac_plus.proactiveness_label} ({opposite_ac_plus.proactiveness})

Your own action (Ac+) is: "{own_ac_plus.statement}"

Generate the Reflection side — how their action grounds and challenges you.

## 1. Re+ (positive reflection: how their action grounds you)

Given their action, what reflection does it trigger that leads to growth?
- Path: escaping the Reflection Perspective's negative toward its positive
- Re+ at the {expected_re_category.upper()} proactiveness level
- **CRITICAL**: Re+ must COMPLEMENT your Ac+ ("{own_ac_plus.statement}") — together they form S+
- Re+ addresses what your action DOESN'T cover — the other side's contribution
- Insight should be similar to Ac+ (~{own_ac_plus.insight_label})
- Re+ must CONTRADICT Ac- (the positive reflection opposes drift)

## 2. Re- (negative reflection: reflection without the action that grounds it)

What happens when their action IS taken in, but nothing you do grounds that reflection?
- What Re+ ITSELF degenerates into when Ac+ is absent — an overextension of the reflection, not the absence of one
- Path: the Reflection Perspective's positive regresses you toward your negative
- NOT the same failure as Ac-: Ac- is your action left unreflected, Re- is your reflection left unacted
- Your Ac+ must CONTRADICT Re- (your positive action opposes this regression)
- Usually lower insight than Re+

Requirements:
- Headlines ~{self.settings.component_length} words, statements up to {self.settings.transition_length} words
- For each position, produce a haiku (3 lines, 5-7-5 syllables)
- Re+ must be in the {expected_re_category} category (polar pair of {own_ac_plus.proactiveness_label})
- Diagonal contradictions: Re+ vs Ac-, Ac+ vs Re-"""

        return await self._conversation.submit(
            response_model=ReSideCompletionDto,
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

{HS_SCALE}

Score each transition by comparing its semantic meaning to the corresponding apex."""

        return await self._conversation.submit(
            response_model=HsScoringDto,
            user_content=prompt,
        )

    async def _generate_category_reframings(
        self,
        ac_category: str,
        re_category: str,
        opposite_edge_context: str,
    ) -> CategoryReframingDto:
        """Generate contextualized category reframings for Ac and Re as full transitions."""
        prompt = f"""Now generate the neutral category transitions for this transformation.

## Ac (Action category: this edge's T → A): {ac_category}
Generate a transition that describes how "{ac_category}" specifically manifests in the Action Perspective's T-A polarity.
- Example: For Love/Indifference, "Intervention" → "Boundary-setting intervention"
- This is a NEUTRAL action category (not + or -), describing the general T → A movement on this edge

## Re (Reflection category: the opposite edge's T → A): {re_category}
The Reflection Perspective (opposite edge):

<reflection_perspective>
{opposite_edge_context}
</reflection_perspective>

Generate a transition that describes how "{re_category}" specifically manifests as reflective response from the opposite side.
- Example: For Love/Indifference, "Interpretation" → "Connection needs interpretation"
- This is a NEUTRAL reflection category (not + or -), describing the general reflective movement

For each, provide:
- **headline** (~{self.settings.component_length} words) - short, memorable reframing
- **statement** (up to {self.settings.transition_length} words) - fuller description of the contextualized category
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
