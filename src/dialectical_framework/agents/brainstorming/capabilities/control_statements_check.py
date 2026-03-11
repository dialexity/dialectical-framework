"""
ControlStatementsCheck: Capability for validating tetrad logical coherence.

Tests the logical coherence of a WisdomUnit's tetrad structure using control statements.

Control statements (from paper Table 4):
- "T+ without A+ yields T-"
- "A+ without T+ yields A-"

Example (T=Love, A=Hate):
- "Bonding (T+) without Autonomy (A+) yields Enmeshment (T-)"
- "Autonomy (A+) without Bonding (T+) yields Alienation (A-)"

Each statement is evaluated for logical coherence (CC score 0.0-1.0).
A tetrad passes validation if both CC scores >= 0.7.

Creates a ConceptualCoherenceEstimation node attached to the WisdomUnit,
with optional Rationale explaining the evaluation.

Usage:
    checker = ControlStatementsCheck()
    result = await checker.execute(wisdom_unit=wu)

    if result.estimation.is_coherent:
        print("Tetrad is logically coherent")
    else:
        est = result.estimation
        print(f"Tetrad needs review: {est.t_plus_without_a_plus_yields_t_minus:.2f}, {est.a_plus_without_t_plus_yields_a_minus:.2f}")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import ConversationFacilitator
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.estimation import ConceptualCoherenceEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_T_PLUS,
    POSITION_T_MINUS,
    POSITION_A_PLUS,
    POSITION_A_MINUS,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


# --- Constants ---

CC_THRESHOLD = 0.7  # Minimum coherence score for valid control statement


# --- DTOs ---

class CoherenceEvaluationDto(BaseModel):
    """Result of evaluating a single control statement."""

    coherence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Logical coherence score (0.0-1.0). >= 0.7 is considered coherent.",
    )
    reasoning: str = Field(
        description="Brief explanation of the coherence assessment"
    )


# --- Result ---

@dataclass
class ControlStatementsCheckResult:
    """Result of control statements check.

    Contains the estimation node that was created and attached to the WisdomUnit.
    """

    estimation: ConceptualCoherenceEstimation
    rationale: Rationale

    # Control statement details for transparency
    t_plus_without_a_plus_yields_t_minus_statement: str
    t_plus_without_a_plus_yields_t_minus_reasoning: str
    a_plus_without_t_plus_yields_a_minus_statement: str
    a_plus_without_t_plus_yields_a_minus_reasoning: str

    @property
    def is_coherent(self) -> bool:
        """True if both control statements pass the coherence threshold."""
        return self.estimation.is_coherent


# --- Capability ---

class ControlStatementsCheck(ExecutableCapability[ControlStatementsCheckResult]):
    """
    Capability for validating tetrad logical coherence using control statements.

    Tests two control statements:
    1. "{T+} without {A+} yields {T-}" - Does lacking A+ cause T to become T-?
    2. "{A+} without {T+} yields {A-}" - Does lacking T+ cause A to become A-?

    Both must score >= 0.7 for the tetrad to be considered coherent.

    Creates:
    - ConceptualCoherenceEstimation node attached to the WisdomUnit
    - Rationale node explaining the evaluation
    """

    def __init__(self) -> None:
        pass

    async def execute(
        self,
        wisdom_unit: WisdomUnit,
        text: str = "",
    ) -> ControlStatementsCheckResult:
        """
        Validate the conceptual coherence of a WisdomUnit's tetrad.

        Creates a ConceptualCoherenceEstimation node and attaches it to the WisdomUnit.

        Args:
            wisdom_unit: The WisdomUnit to validate (must be committed, have T+, T-, A+, A-)
            text: Optional context for evaluation

        Returns:
            ControlStatementsCheckResult with estimation node and coherence status

        Raises:
            ValueError: If WisdomUnit is not committed or missing required pole components
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not wisdom_unit.is_committed:
            raise ValueError("WisdomUnit must be committed before validation")

        if not wisdom_unit.is_complete():
            raise ValueError("WisdomUnit must be complete (have all 6 positions)")

        # Get pole statements
        t_plus = wisdom_unit.get_component(POSITION_T_PLUS)
        t_minus = wisdom_unit.get_component(POSITION_T_MINUS)
        a_plus = wisdom_unit.get_component(POSITION_A_PLUS)
        a_minus = wisdom_unit.get_component(POSITION_A_MINUS)

        # Build control statements
        stmt_1 = f'"{t_plus.statement}" without "{a_plus.statement}" yields "{t_minus.statement}"'
        stmt_2 = f'"{a_plus.statement}" without "{t_plus.statement}" yields "{a_minus.statement}"'

        # Evaluate both statements in parallel using isolated conversations
        result_1, result_2 = await asyncio.gather(
            self._evaluate_control_statement(stmt_1, text),
            self._evaluate_control_statement(stmt_2, text),
        )

        # Create estimation node
        avg_score = (result_1.coherence_score + result_2.coherence_score) / 2
        estimation = ConceptualCoherenceEstimation(
            value=avg_score,
            t_plus_without_a_plus_yields_t_minus=result_1.coherence_score,
            a_plus_without_t_plus_yields_a_minus=result_2.coherence_score,
        )
        estimation.set_target(wisdom_unit)

        # Create rationale explaining the evaluation
        status = "COHERENT" if estimation.is_coherent else "NOT COHERENT"
        rationale_text = (
            f"Conceptual Coherence Evaluation: {status}\n\n"
            f"T+ without A+ yields T- (score={result_1.coherence_score:.2f}):\n"
            f"  {stmt_1}\n"
            f"  Reasoning: {result_1.reasoning}\n\n"
            f"A+ without T+ yields A- (score={result_2.coherence_score:.2f}):\n"
            f"  {stmt_2}\n"
            f"  Reasoning: {result_2.reasoning}\n\n"
            f"Average: {avg_score:.2f} (threshold: {CC_THRESHOLD})"
        )
        rationale = Rationale(text=rationale_text)
        rationale.set_explanation_target(wisdom_unit)
        rationale.commit()
        self._report.node_created(rationale)

        # Commit estimation with rationale as provider
        estimation.set_provider(rationale)
        estimation.commit()
        self._report.node_created(estimation)

        result = ControlStatementsCheckResult(
            estimation=estimation,
            rationale=rationale,
            t_plus_without_a_plus_yields_t_minus_statement=stmt_1,
            t_plus_without_a_plus_yields_t_minus_reasoning=result_1.reasoning,
            a_plus_without_t_plus_yields_a_minus_statement=stmt_2,
            a_plus_without_t_plus_yields_a_minus_reasoning=result_2.reasoning,
        )

        self._build_report(result)
        return result

    async def _evaluate_control_statement(
        self,
        statement: str,
        text: str,
    ) -> CoherenceEvaluationDto:
        """Evaluate a single control statement for logical coherence."""
        context_section = f"<context>\n{text}\n</context>\n\n" if text else ""

        prompt = f"""{context_section}Rate the logical coherence of this control statement:

{statement}

The pattern "[Positive] without [Balancing factor] yields [Negative]" tests whether
the absence of a balancing positive pole naturally leads to the negative/shadow aspect.

Coherence scale:
- 0.9-1.0: Highly coherent, clear logical/causal relationship
- 0.7-0.9: Coherent, reasonable logical connection
- 0.5-0.7: Somewhat coherent, plausible but weak
- 0.3-0.5: Weak coherence, tenuous connection
- 0.0-0.3: Not coherent, no clear logical relationship"""

        conversation = ConversationFacilitator()
        return await conversation.submit(
            response_model=CoherenceEvaluationDto,
            user_content=prompt,
        )

    def _build_report(self, result: ControlStatementsCheckResult) -> None:
        """Build execution report from result."""
        est = result.estimation
        self._report.artifacts["t_plus_without_a_plus_yields_t_minus"] = est.t_plus_without_a_plus_yields_t_minus
        self._report.artifacts["a_plus_without_t_plus_yields_a_minus"] = est.a_plus_without_t_plus_yields_a_minus
        self._report.artifacts["average"] = est.value
        self._report.artifacts["is_coherent"] = result.is_coherent

        self._report.ok = True
        status = "COHERENT" if result.is_coherent else "NOT COHERENT"
        self._report.summary = (
            f"Control Statements Check: {status} "
            f"(T+\\A+→T-={est.t_plus_without_a_plus_yields_t_minus:.2f}, "
            f"A+\\T+→A-={est.a_plus_without_t_plus_yields_a_minus:.2f}, "
            f"avg={est.value:.2f})"
        )
