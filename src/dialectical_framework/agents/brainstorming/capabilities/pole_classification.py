"""
PoleClassification: Capability for classifying a user-provided pole.

Evaluates a given pole statement against a tension (T-A pair) to determine:
- HS: Heuristic Similarity to the apex concept (0.0-1.0)
  - HS > 0.1: Valid for the specified position
  - HS <= 0.1: Wrong category, check suggested_position
- Complementarity: How it relates to T and A (K_T, K_A)

This is the pole counterpart to AntithesisClassification.

Does NOT create any database nodes - caller decides what to do with result.

Usage:
    classifier = PoleClassification()
    result = await classifier.execute(
        thesis=thesis_component,
        antithesis=antithesis_component,
        pole_statement="Personal freedom",
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

from dialectical_framework.agents.brainstorming.capabilities.statement_classification import (
    StatementClassification,
)
from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_A_MINUS,
    POSITION_A_PLUS,
    POSITION_T_MINUS,
    POSITION_T_PLUS,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


# --- System Prompt ---

SYSTEM_PROMPT = """You are a dialectical pole evaluator.

Your task is to evaluate whether a given statement is a valid pole (positive or negative aspect)
for a thesis-antithesis tension, and measure its quality.

## Pole Positions

A complete dialectical tetrad has 6 positions:
- T: Thesis (neutral statement)
- A: Antithesis (dialectical opposite of T)
- T+: Positive aspect of thesis (benefits, strengths)
- T-: Negative aspect of thesis (risks, downsides, shadow)
- A+: Positive aspect of antithesis (benefits, strengths)
- A-: Negative aspect of antithesis (risks, downsides, shadow)

## Validity Criteria

A pole is VALID for a position if:
1. **T+**: Represents a genuine benefit/strength of the thesis
2. **T-**: Represents a genuine risk/downside/shadow of the thesis
3. **A+**: Represents a genuine benefit/strength of the antithesis
4. **A-**: Represents a genuine risk/downside/shadow of the antithesis

A pole is INVALID if:
- It belongs to a different position (e.g., given as T+ but is actually A+)
- It's unrelated to the tension
- It's actually the thesis or antithesis level concept (T or A), not an aspect
  - If so, suggest "T" or "A" as the better position

## HS (Heuristic Similarity) Scale

HS measures how well the pole represents the apex concept for that position:
- 0.9-1.0: Perfect or near-perfect match - exemplary representation of the apex
- 0.7-0.9: Very similar - captures most aspects of the apex concept
- 0.5-0.7: Related - captures some aspects, moderate fit for position
- 0.3-0.5: Somewhat related - weak but still the right category
- 0.1-0.3: Weakly related - likely better suited for a different position
- 0.0-0.1: Not related - wrong category entirely, definitely belongs elsewhere

**Critical threshold**: HS > 0.1 means valid for this position (quality varies).
HS ≤ 0.1 means wrong category - suggest the correct position.

## Complementarity Scale

Complementarity measures how well the pole complements, enhances, or supports T and A.

**K_T (Complementarity to Thesis)**: 0.0 to 1.0
How well does this pole complement, enhance, or support the Thesis?
- 0.0 = Actively undermines or contradicts T
- 0.5 = Neutral, neither helps nor hurts T
- 1.0 = Strongly supports and enhances T

**K_A (Complementarity to Antithesis)**: 0.0 to 1.0
How well does this pole complement, enhance, or support the Antithesis?
- 0.0 = Actively undermines or contradicts A
- 0.5 = Neutral, neither helps nor hurts A
- 1.0 = Strongly supports and enhances A

Respond with structured output matching the requested format."""


# --- DTOs ---

VALID_POSITIONS = [POSITION_T_PLUS, POSITION_T_MINUS, POSITION_A_PLUS, POSITION_A_MINUS]


class PoleEvaluationDto(BaseModel):
    """Result of evaluating a pole against a tension."""

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
class PoleClassificationResult:
    """Result of pole classification - no DB nodes created.

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


# --- Capability ---


class PoleClassification(ExecutableCapability[PoleClassificationResult]):
    """
    Capability for classifying a user-provided pole against a tension.

    Evaluates the pole to determine:
    - Is it valid for the specified position?
    - HS: Heuristic Similarity to the apex concept
    - Complementarity: How it relates to T and A

    This mirrors AntithesisClassification but for poles.
    Does NOT create any database nodes - caller decides what to do with result.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def execute(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        pole_statement: str,
        position: str,
        text: str = "",
    ) -> PoleClassificationResult:
        """
        Classify a user-provided pole against a T-A tension.

        Args:
            thesis: The thesis component (T)
            antithesis: The antithesis component (A)
            pole_statement: The pole statement to classify
            position: Target position ("T+", "T-", "A+", "A-")
            text: Optional source content context

        Returns:
            PoleClassificationResult with validity, HS, complementarity (no DB nodes created)
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        # Validate inputs
        if not thesis or not thesis.statement:
            raise ValueError("Cannot classify pole without a valid thesis")
        if not antithesis or not antithesis.statement:
            raise ValueError("Cannot classify pole without a valid antithesis")
        if not pole_statement or not pole_statement.strip():
            raise ValueError("Cannot classify empty pole statement")
        if position not in VALID_POSITIONS:
            raise ValueError(
                f"Invalid position '{position}'. Must be one of: {VALID_POSITIONS}"
            )

        self._thesis = thesis
        self._antithesis = antithesis
        self._pole_statement = pole_statement.strip()
        self._position = position
        self._text = text

        # Initialize conversation
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        # Get meaning and apex from taxonomy (deterministic)
        parent = thesis if position in [POSITION_T_PLUS, POSITION_T_MINUS] else antithesis
        meaning = StatementClassification.lookup_pole_meaning(parent, position)
        apex_concept = StatementClassification.lookup_pole_apex(parent, position)

        # Evaluate pole
        evaluation = await self._evaluate_pole(apex_concept)

        # Build result (validity determined by HS > 0.1)
        result = PoleClassificationResult(
            statement=self._pole_statement,
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
            f"Classified pole '{self._pole_statement}' for {position} "
            f"(HS={result.heuristic_similarity:.2f})"
        )

        return result

    async def _evaluate_pole(self, apex_concept: str) -> PoleEvaluationDto:
        """Evaluate pole against tension using LLM."""
        prompt = self._build_evaluation_prompt(apex_concept)
        return await self._conversation.submit(
            response_model=PoleEvaluationDto,
            user_content=prompt,
        )

    def _build_evaluation_prompt(self, apex_concept: str) -> str:
        """Build prompt for pole evaluation."""
        context_section = f"<context>\n{self._text}\n</context>\n\n" if self._text else ""

        position_description = {
            POSITION_T_PLUS: "positive aspect (benefit/strength) of the THESIS",
            POSITION_T_MINUS: "negative aspect (risk/downside/shadow) of the THESIS",
            POSITION_A_PLUS: "positive aspect (benefit/strength) of the ANTITHESIS",
            POSITION_A_MINUS: "negative aspect (risk/downside/shadow) of the ANTITHESIS",
        }

        return f"""{context_section}Evaluate this pole statement for a dialectical tension.

**Tension:**
- Thesis (T): "{self._thesis.statement}"
- Antithesis (A): "{self._antithesis.statement}"

**Pole to evaluate:**
- Statement: "{self._pole_statement}"
- Target position: {self._position} ({position_description[self._position]})
- Apex concept for this position: "{apex_concept}"

**Determine:**

1. **heuristic_similarity** (0.0-1.0): How well does this pole represent the apex concept "{apex_concept}"?
   Use the HS scale from the system guidelines. Remember: HS > 0.1 = valid, HS ≤ 0.1 = wrong category.

2. **complementarity_t** (K_T, 0.0-1.0): How well does this pole complement, enhance, or support the thesis "{self._thesis.statement}"?
   Use the K_T scale from the system guidelines.

3. **complementarity_a** (K_A, 0.0-1.0): How well does this pole complement, enhance, or support the antithesis "{self._antithesis.statement}"?
   Use the K_A scale from the system guidelines.

4. **suggested_position**: If HS is very low (not a good fit for {self._position}), which position might fit better?
   - T: if this is actually a thesis-level concept (neutral statement of the T side)
   - A: if this is actually an antithesis-level concept (neutral statement of the A side)
   - T+/T-/A+/A-: if it's a pole but for a different position
   - null: if unrelated to this tension

5. **reasoning**: Explain your evaluation."""
