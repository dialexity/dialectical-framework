"""
AspectClassification: Concern for classifying a user-provided aspect.

Evaluates a given aspect statement against a tension (T-A pair) to determine:
- HS: Heuristic Similarity to the apex concept (0.0-1.0)
  - HS > 0.1: Valid for the specified position
  - HS <= 0.1: Wrong category, check suggested_position
- Complementarity: How it relates to T and A (K_T, K_A)

This is the aspect counterpart to AntithesisClassification.

Does NOT create any database nodes - caller decides what to do with result.

Usage:
    classifier = AspectClassification()
    result = await classifier.resolve(
        thesis=thesis_component,
        antithesis=antithesis_component,
        aspect_statement="Personal freedom",
        position="A+",
        text="context about relationships..."
    )
    if result.heuristic_similarity > 0.1:  # Valid for A+
        print(f"HS: {result.heuristic_similarity}, K_T: {result.complementarity_t}")
    else:
        print(f"Suggested position: {result.suggested_position}")
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
from dialectical_framework.concerns.statement_classification import \
    StatementClassification
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                          POSITION_A_PLUS,
                                                          POSITION_T_MINUS,
                                                          POSITION_T_PLUS)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import \
        DialecticalComponent


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical aspect evaluator.

Your task is to evaluate whether a given statement is a valid aspect (positive or negative elaboration)
for a thesis-antithesis tension, and measure its quality.

## Aspect Positions

A complete dialectical tetrad has 6 positions:
- T: Thesis (neutral statement)
- A: Antithesis (dialectical opposite of T)
- T+: Positive aspect of thesis (benefits, strengths)
- T-: Negative aspect of thesis (risks, downsides, shadow)
- A+: Positive aspect of antithesis (benefits, strengths)
- A-: Negative aspect of antithesis (risks, downsides, shadow)

## Diagonal Contradiction (Structural Constraint)

Aspects form contradiction pairs across the diagonal:
- **T+ contradicts A-**: They cannot both be true/good simultaneously
- **A+ contradicts T-**: They cannot both be true/good simultaneously

Example (T=Love, A=Indifference):
- T+ (Bonding) contradicts A- (Alienation)
- A+ (Autonomy) contradicts T- (Enmeshment)

When evaluating an aspect, consider whether it would properly contradict its diagonal counterpart.
If a proposed T+ doesn't oppose A-, or A+ doesn't oppose T-, it may be misclassified.

## HS (Heuristic Similarity) Scale

HS measures how well the aspect represents the apex concept for that position:
- 0.9-1.0: Perfect or near-perfect match - exemplary representation of the apex
- 0.7-0.9: Very similar - captures most aspects of the apex concept
- 0.5-0.7: Related - captures some aspects, moderate fit for position
- 0.3-0.5: Somewhat related - weak but still the right category
- 0.1-0.3: Weakly related - likely better suited for a different position
- 0.0-0.1: Not related - wrong category entirely, definitely belongs elsewhere

**Critical threshold**: HS > 0.1 means valid for this position (quality varies).
HS ≤ 0.1 means wrong category - suggest the correct position.

## Complementarity Scale

Complementarity measures how well the aspect complements, enhances, or supports T and A.

**K_T (Complementarity to Thesis)**: 0.0 to 1.0
How well does this aspect complement, enhance, or support the Thesis?
- 0.0 = Actively undermines or contradicts T
- 0.5 = Neutral, neither helps nor hurts T
- 1.0 = Strongly supports and enhances T

**K_A (Complementarity to Antithesis)**: 0.0 to 1.0
How well does this aspect complement, enhance, or support the Antithesis?
- 0.0 = Actively undermines or contradicts A
- 0.5 = Neutral, neither helps nor hurts A
- 1.0 = Strongly supports and enhances A

Respond with structured output matching the requested format."""


# --- DTOs ---

VALID_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]


class AspectEvaluationDto(BaseModel):
    """Result of evaluating an aspect against a tension."""

    heuristic_similarity: float = Field(
        ge=0.0,
        le=1.0,
        description="Heuristic Similarity to the apex concept (0.0-1.0). HS > 0.1 means valid for this position.",
    )
    complementarity_t: float = Field(
        ge=0.0,
        le=1.0,
        description="Complementarity to thesis (0.0 to 1.0)",
    )
    complementarity_a: float = Field(
        ge=0.0,
        le=1.0,
        description="Complementarity to antithesis (0.0 to 1.0)",
    )
    suggested_position: Optional[str] = Field(
        default=None,
        description="If HS is very low, which position might fit better? (T/A/T+/T-/A+/A- or null if unrelated)",
    )
    reasoning: str = Field(description="Explanation of the evaluation")


# --- Result ---


@dataclass
class AspectClassificationResult:
    """Result of aspect classification - no DB nodes created.

    Validity is determined by heuristic_similarity:
    - HS > 0.1: Valid for this position
    - HS <= 0.1: Wrong category, check suggested_position
    """

    statement: str
    position: str
    meaning: str
    heuristic_similarity: float
    complementarity_t: float
    complementarity_a: float
    apex_concept: str
    reasoning: str
    suggested_position: Optional[str] = None


# --- Concern ---


class AspectClassification(ReasonableConcern[AspectClassificationResult]):
    """
    Concern for classifying a user-provided aspect against a tension.

    Evaluates the aspect to determine:
    - Is it valid for the specified position?
    - HS: Heuristic Similarity to the apex concept
    - Complementarity: How it relates to T and A

    This mirrors AntithesisClassification but for aspects.
    Does NOT create any database nodes - caller decides what to do with result.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        aspect_statement: str,
        position: str,
        text: str = "",
    ) -> AspectClassificationResult:
        """
        Classify a user-provided aspect against a T-A tension.

        Args:
            thesis: The thesis component (T)
            antithesis: The antithesis component (A)
            aspect_statement: The aspect statement to classify
            position: Target position ("T+", "T-", "A+", "A-")
            text: Optional source content context

        Returns:
            AspectClassificationResult with validity, HS, complementarity (no DB nodes created)
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Validate inputs
        if not thesis or not thesis.statement:
            raise ValueError("Cannot classify aspect without a valid thesis")
        if not antithesis or not antithesis.statement:
            raise ValueError("Cannot classify aspect without a valid antithesis")
        if not aspect_statement or not aspect_statement.strip():
            raise ValueError("Cannot classify empty aspect statement")
        if position not in VALID_POSITIONS:
            raise ValueError(
                f"Invalid position '{position}'. Must be one of: {VALID_POSITIONS}"
            )

        self._thesis = thesis
        self._antithesis = antithesis
        self._aspect_statement = aspect_statement.strip()
        self._position = position
        self._text = text

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Get meaning and apex from taxonomy (deterministic)
        parent = (
            thesis if position in [POSITION_T_PLUS, POSITION_T_MINUS] else antithesis
        )
        meaning = StatementClassification.lookup_aspect_meaning(parent, position)
        apex_concept = StatementClassification.lookup_aspect_apex(parent, position)

        # Evaluate aspect
        evaluation = await self._evaluate_aspect(apex_concept)

        # Build result (validity determined by HS > 0.1)
        result = AspectClassificationResult(
            statement=self._aspect_statement,
            position=position,
            meaning=meaning,
            heuristic_similarity=evaluation.heuristic_similarity,
            complementarity_t=evaluation.complementarity_t,
            complementarity_a=evaluation.complementarity_a,
            apex_concept=apex_concept,
            reasoning=evaluation.reasoning,
            suggested_position=evaluation.suggested_position,
        )

        # Build report
        self._report.artifacts["heuristic_similarity"] = result.heuristic_similarity
        self._report.artifacts["complementarity_t"] = result.complementarity_t
        self._report.artifacts["complementarity_a"] = result.complementarity_a
        self._report.ok = True

        self._report.summary = (
            f"Classified aspect '{self._aspect_statement}' for {position} "
            f"(HS={result.heuristic_similarity:.2f})"
        )

        return result

    async def _evaluate_aspect(self, apex_concept: str) -> AspectEvaluationDto:
        """Evaluate aspect against tension using LLM."""
        prompt = self._build_evaluation_prompt(apex_concept)
        return await self._conversation.submit(
            response_model=AspectEvaluationDto,
            user_content=prompt,
        )

    def _build_evaluation_prompt(self, apex_concept: str) -> str:
        """Build prompt for aspect evaluation."""
        context_section = (
            f"<context>\n{self._text}\n</context>\n\n" if self._text else ""
        )

        position_description = {
            POSITION_T_PLUS: "positive aspect (benefit/strength) of the THESIS",
            POSITION_T_MINUS: "negative aspect (risk/downside/shadow) of the THESIS",
            POSITION_A_PLUS: "positive aspect (benefit/strength) of the ANTITHESIS",
            POSITION_A_MINUS: "negative aspect (risk/downside/shadow) of the ANTITHESIS",
        }

        return f"""{context_section}Evaluate this aspect statement for a dialectical tension.

**Tension:**
- Thesis (T): "{self._thesis.statement}"
- Antithesis (A): "{self._antithesis.statement}"

**Aspect to evaluate:**
- Statement: "{self._aspect_statement}"
- Target position: {self._position} ({position_description[self._position]})
- Apex concept for this position: "{apex_concept}"

**Determine:**

1. **heuristic_similarity** (0.0-1.0): How well does this aspect represent the apex concept "{apex_concept}"?
   Use the HS scale from the system guidelines. Remember: HS > 0.1 = valid, HS ≤ 0.1 = wrong category.

2. **complementarity_t** (K_T, 0.0-1.0): How well does this aspect complement, enhance, or support the thesis "{self._thesis.statement}"?
   Use the K_T scale from the system guidelines.

3. **complementarity_a** (K_A, 0.0-1.0): How well does this aspect complement, enhance, or support the antithesis "{self._antithesis.statement}"?
   Use the K_A scale from the system guidelines.

4. **suggested_position**: If HS is very low (not a good fit for {self._position}), which position might fit better?
   - T: if this is actually a thesis-level concept (neutral statement of the T side)
   - A: if this is actually an antithesis-level concept (neutral statement of the A side)
   - T+/T-/A+/A-: if it's an aspect but for a different position
   - null: if unrelated to this tension

5. **reasoning**: Explain your evaluation."""
