"""
DiagonalOppositionsCheck: Capability for validating diagonal opposition pairs.

Tests the opposition validity of diagonal pole pairs in a WisdomUnit:
- T+ vs A-: Does T+ oppose A-?
- A+ vs T-: Does A+ oppose T-?

These diagonal pairs should be mutually exclusive - they cannot both be true/good
simultaneously. Strong oppositions (>= 0.7) indicate valid tetrad structure.

Creates a DiagonalContradictionEstimation node attached to the WisdomUnit,
with Rationale explaining the evaluation.

Usage:
    checker = DiagonalOppositionsCheck()
    result = await checker.execute(wisdom_unit=wu)

    if result.is_valid:
        print("Diagonal oppositions are valid")
    else:
        est = result.estimation
        print(f"Weak oppositions: T+/A-={est.t_plus_vs_a_minus:.2f}, A+/T-={est.a_plus_vs_t_minus:.2f}")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.executable_capability import \
    ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.estimation import (
    ORTHOGONALITY_THRESHOLD, DiagonalContradictionEstimation)
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wisdom_unit import (POSITION_A,
                                                           POSITION_A_MINUS,
                                                           POSITION_A_PLUS,
                                                           POSITION_T,
                                                           POSITION_T_MINUS,
                                                           POSITION_T_PLUS)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


# --- DTOs ---


class ContradictionEvaluationDto(BaseModel):
    """Result of evaluating a single contradiction pair."""

    contradiction_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Contradiction strength (0.0-1.0). >= 0.7 is considered a valid contradiction.",
    )
    reasoning: str = Field(
        description="Brief explanation of the contradiction assessment"
    )


# --- Result ---


@dataclass
class DiagonalOppositionsCheckResult:
    """Result of diagonal oppositions check.

    Contains the estimation node and validation scores.
    For uncommitted WUs, estimation/rationale are created but not committed.
    """

    estimation: DiagonalContradictionEstimation
    rationale: Rationale

    # Detailed results for transparency
    t_plus_vs_a_minus_score: float
    t_plus_vs_a_minus_reasoning: str
    a_plus_vs_t_minus_score: float
    a_plus_vs_t_minus_reasoning: str

    @property
    def is_valid(self) -> bool:
        """True if both diagonal pairs show valid opposition (>= threshold)."""
        return self.estimation.is_valid


# --- Capability ---


class DiagonalOppositionsCheck(ExecutableCapability[DiagonalOppositionsCheckResult]):
    """
    Capability for validating diagonal opposition pairs.

    Tests two opposition pairs:
    1. T+ vs A-: Does T+ oppose A-?
    2. A+ vs T-: Does A+ oppose T-?

    Both must score >= 0.7 for the tetrad to have valid oppositions.

    Creates:
    - DiagonalContradictionEstimation node attached to the WisdomUnit
    - Rationale node explaining the evaluation
    """

    def __init__(self) -> None:
        pass

    async def execute(
        self,
        wisdom_unit: WisdomUnit,
        text: str = "",
    ) -> DiagonalOppositionsCheckResult:
        """
        Validate the diagonal opposition pairs of a WisdomUnit's tetrad.

        Creates a DiagonalContradictionEstimation node if WU is committed.
        For uncommitted WUs, returns validation scores without creating nodes.

        Args:
            wisdom_unit: The WisdomUnit to validate (must be complete with all 6 positions)
            text: Optional context for evaluation

        Returns:
            DiagonalOppositionsCheckResult with validity status and optional estimation node

        Raises:
            ValueError: If WisdomUnit is missing required components
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not wisdom_unit.is_complete():
            raise ValueError("WisdomUnit must be complete (have all 6 positions)")

        # Get statements for context and poles
        t_stmt = wisdom_unit.get_component(POSITION_T)
        a_stmt = wisdom_unit.get_component(POSITION_A)
        t_plus = wisdom_unit.get_component(POSITION_T_PLUS)
        t_minus = wisdom_unit.get_component(POSITION_T_MINUS)
        a_plus = wisdom_unit.get_component(POSITION_A_PLUS)
        a_minus = wisdom_unit.get_component(POSITION_A_MINUS)

        # Evaluate both diagonal pairs in parallel
        result_t_plus_a_minus, result_a_plus_t_minus = await asyncio.gather(
            self._evaluate_contradiction(
                pole_a_statement=t_plus.statement,
                pole_a_role=f"positive aspect of '{t_stmt.statement}'",
                pole_b_statement=a_minus.statement,
                pole_b_role=f"negative aspect of '{a_stmt.statement}'",
                text=text,
            ),
            self._evaluate_contradiction(
                pole_a_statement=a_plus.statement,
                pole_a_role=f"positive aspect of '{a_stmt.statement}'",
                pole_b_statement=t_minus.statement,
                pole_b_role=f"negative aspect of '{t_stmt.statement}'",
                text=text,
            ),
        )

        # Create estimation and rationale nodes
        avg_score = (
            result_t_plus_a_minus.contradiction_score
            + result_a_plus_t_minus.contradiction_score
        ) / 2
        is_valid = (
            result_t_plus_a_minus.contradiction_score >= ORTHOGONALITY_THRESHOLD
            and result_a_plus_t_minus.contradiction_score >= ORTHOGONALITY_THRESHOLD
        )
        status = "VALID" if is_valid else "WEAK"

        estimation = DiagonalContradictionEstimation(
            value=avg_score,
            t_plus_vs_a_minus=result_t_plus_a_minus.contradiction_score,
            a_plus_vs_t_minus=result_a_plus_t_minus.contradiction_score,
        )

        rationale_text = (
            f"Diagonal Contradiction Evaluation: {status}\n\n"
            f"T+ vs A- (score={result_t_plus_a_minus.contradiction_score:.2f}):\n"
            f'  "{t_plus.statement}" contradicts "{a_minus.statement}"?\n'
            f"  Reasoning: {result_t_plus_a_minus.reasoning}\n\n"
            f"A+ vs T- (score={result_a_plus_t_minus.contradiction_score:.2f}):\n"
            f'  "{a_plus.statement}" contradicts "{t_minus.statement}"?\n'
            f"  Reasoning: {result_a_plus_t_minus.reasoning}\n\n"
            f"Average: {avg_score:.2f} (threshold: {ORTHOGONALITY_THRESHOLD})"
        )
        rationale = Rationale(text=rationale_text)

        # Only commit and attach if WU is committed
        if wisdom_unit.is_committed:
            estimation.set_target(wisdom_unit)
            rationale.set_explanation_target(wisdom_unit)
            rationale.commit()
            self._report.node_created(rationale)

            estimation.set_provider(rationale)
            estimation.commit()
            self._report.node_created(estimation)

        result = DiagonalOppositionsCheckResult(
            estimation=estimation,
            rationale=rationale,
            t_plus_vs_a_minus_score=result_t_plus_a_minus.contradiction_score,
            t_plus_vs_a_minus_reasoning=result_t_plus_a_minus.reasoning,
            a_plus_vs_t_minus_score=result_a_plus_t_minus.contradiction_score,
            a_plus_vs_t_minus_reasoning=result_a_plus_t_minus.reasoning,
        )

        self._build_report(result)
        return result

    async def _evaluate_contradiction(
        self,
        pole_a_statement: str,
        pole_a_role: str,
        pole_b_statement: str,
        pole_b_role: str,
        text: str,
    ) -> ContradictionEvaluationDto:
        """Evaluate if two diagonal poles are mutually exclusive."""
        context_section = f"<context>\n{text}\n</context>\n\n" if text else ""

        prompt = f"""{context_section}Are these two concepts mutually exclusive?

Concept A: "{pole_a_statement}" ({pole_a_role})
Concept B: "{pole_b_statement}" ({pole_b_role})

In a well-formed dialectical structure, the positive aspect of one side should
contradict the negative aspect of the opposite side - they cannot both be
true or desirable at the same time.

Rate how strongly these concepts contradict each other:
- 0.9-1.0: Strong contradiction - clearly mutually exclusive, one negates the other
- 0.7-0.9: Valid contradiction - cannot both hold simultaneously
- 0.5-0.7: Weak contradiction - some tension but could potentially coexist
- 0.3-0.5: Minimal contradiction - largely independent concepts
- 0.0-0.3: No contradiction - compatible or even complementary"""

        conversation = ConversationFacilitator()
        return await conversation.submit(
            response_model=ContradictionEvaluationDto,
            user_content=prompt,
        )

    def _build_report(self, result: DiagonalOppositionsCheckResult) -> None:
        """Build execution report from result."""
        est = result.estimation
        self._report.artifacts["t_plus_vs_a_minus"] = est.t_plus_vs_a_minus
        self._report.artifacts["a_plus_vs_t_minus"] = est.a_plus_vs_t_minus
        self._report.artifacts["average"] = est.value
        self._report.artifacts["is_valid"] = result.is_valid

        self._report.ok = True
        status = "VALID" if result.is_valid else "WEAK"
        self._report.summary = (
            f"Diagonal Oppositions Check: {status} "
            f"(T+/A-={est.t_plus_vs_a_minus:.2f}, "
            f"A+/T-={est.a_plus_vs_t_minus:.2f}, "
            f"avg={est.value:.2f})"
        )
