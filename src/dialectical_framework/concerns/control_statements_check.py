"""
ControlStatementsCheck: Concern for validating tetrad logical coherence.

Tests the logical coherence of a Perspective's tetrad structure using control statements.

Control statements (from paper Table 4):
- "T+ without A+ yields T-"
- "A+ without T+ yields A-"

Example (T=Love, A=Hate):
- "Bonding (T+) without Autonomy (A+) yields Enmeshment (T-)"
- "Autonomy (A+) without Bonding (T+) yields Alienation (A-)"

Each statement is evaluated for logical coherence (CC score 0.0-1.0).
A tetrad passes validation if both CC scores >= 0.7.

Creates a ConceptualCoherenceEstimation node attached to the Perspective,
with optional Rationale explaining the evaluation.

Usage:
    checker = ControlStatementsCheck()
    result = await checker.resolve(perspective=pp)

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

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.estimation import (
    CONCEPTUAL_COHERENCE_THRESHOLD, ConceptualCoherenceEstimation,
    DialecticalValidityEstimation)
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.perspective import (POSITION_A_MINUS,
                                                          POSITION_A_PLUS,
                                                          POSITION_T_MINUS,
                                                          POSITION_T_PLUS)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective


# --- DTOs ---


class CoherenceEvaluationDto(BaseModel):
    """Result of evaluating a single control statement (CC + DV).

    DESIGN FORK (revisit if scores correlate): CC and DV are scored in the SAME
    LLM call here (zero extra cost), while the paper [P1 S1.7] used separate
    prompts per metric. Same-call scoring risks the model anchoring one score
    on the other. If real-LLM checks against the paper's reference table
    (S1.7-1/-2: Orwellian DV≈0.0 with CC as high as 0.85 on some models;
    Buddhist DV≈0.9) show CC and DV tracking each other where the paper
    separates them, split DV into its own call (+2 calls per perspective).
    """

    coherence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Logical coherence score (0.0-1.0). >= 0.7 is considered coherent.",
    )
    reasoning: str = Field(description="Brief explanation of the coherence assessment")
    dialectical_validity: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Dialectical Validity (DV, 0.0-1.0), judged INDEPENDENTLY of coherence. "
            "1.0 = the statement expresses a natural, balanced, generative dialectical "
            "relationship: the concepts occupy comparable semantic levels, the two "
            "positive poles genuinely complement one another, and the predicted "
            "pathology arises naturally from the absence of its complementary "
            "counterpart. 0.0 = forced, artificial, or dialectically distorted: "
            "semantically mismatched concepts, one pole arbitrarily privileged, or "
            "outcomes relying on coercion, ideology, arbitrary conventions, or "
            "implausible reasoning rather than natural system dynamics. Ignore "
            "factual correctness; evaluate only the quality of the dialectical "
            "relationship as a generative principle."
        ),
    )
    dv_reasoning: str = Field(
        description="Brief explanation of the dialectical-validity assessment"
    )


# --- Result ---


@dataclass
class ControlStatementsCheckResult:
    """Result of control statements check.

    Contains the estimation node and coherence scores.
    For uncommitted WUs, estimation/rationale are created but not committed.
    """

    estimation: ConceptualCoherenceEstimation
    dv_estimation: DialecticalValidityEstimation
    rationale: Rationale

    # Control statement details for transparency
    t_plus_without_a_plus_yields_t_minus_statement: str
    t_plus_without_a_plus_yields_t_minus_score: float
    t_plus_without_a_plus_yields_t_minus_reasoning: str
    a_plus_without_t_plus_yields_a_minus_statement: str
    a_plus_without_t_plus_yields_a_minus_score: float
    a_plus_without_t_plus_yields_a_minus_reasoning: str
    # DV per statement (annotation only — never gates; see DialecticalValidityEstimation)
    t_plus_without_a_plus_yields_t_minus_dv: float
    a_plus_without_t_plus_yields_a_minus_dv: float

    @property
    def is_coherent(self) -> bool:
        """True if both control statements pass the coherence threshold."""
        return self.estimation.is_coherent


# --- Concern ---


class ControlStatementsCheck(ReasonableConcern[ControlStatementsCheckResult]):
    """
    Concern for validating tetrad logical coherence using control statements.

    Tests two control statements:
    1. "{T+} without {A+} yields {T-}" - Does lacking A+ cause T to become T-?
    2. "{A+} without {T+} yields {A-}" - Does lacking T+ cause A to become A-?

    Both scores must be >= 0.7 for the tetrad to be considered coherent.

    Creates:
    - ConceptualCoherenceEstimation node attached to the Perspective
    - Rationale node explaining the evaluation
    """

    def __init__(self) -> None:
        pass

    async def resolve(
        self,
        perspective: Perspective,
        text: str = "",
    ) -> ControlStatementsCheckResult:
        """
        Validate the conceptual coherence of a Perspective's tetrad.

        Creates a ConceptualCoherenceEstimation node if PP is committed.
        For uncommitted WUs, returns coherence scores without creating nodes.

        Args:
            perspective: The Perspective to validate (must be complete with all 6 positions)
            text: Optional context for evaluation

        Returns:
            ControlStatementsCheckResult with coherence status and optional estimation node

        Raises:
            ValueError: If Perspective is missing required components
        """

        if not perspective.is_complete():
            raise ValueError("Perspective must be complete (have all 6 positions)")

        # Get aspect statements
        t_plus = perspective.get_component(POSITION_T_PLUS)
        t_minus = perspective.get_component(POSITION_T_MINUS)
        a_plus = perspective.get_component(POSITION_A_PLUS)
        a_minus = perspective.get_component(POSITION_A_MINUS)

        # Build control statements
        stmt_1 = f'"{t_plus.prompt_text}" without "{a_plus.prompt_text}" yields "{t_minus.prompt_text}"'
        stmt_2 = f'"{a_plus.prompt_text}" without "{t_plus.prompt_text}" yields "{a_minus.prompt_text}"'

        # Evaluate both statements in parallel using isolated conversations
        result_1, result_2 = await asyncio.gather(
            self._evaluate_control_statement(stmt_1, text),
            self._evaluate_control_statement(stmt_2, text),
        )

        # Create estimation and rationale nodes
        avg_score = (result_1.coherence_score + result_2.coherence_score) / 2
        avg_dv = (result_1.dialectical_validity + result_2.dialectical_validity) / 2

        estimation = ConceptualCoherenceEstimation(
            value=avg_score,
            t_plus_without_a_plus_yields_t_minus=result_1.coherence_score,
            a_plus_without_t_plus_yields_a_minus=result_2.coherence_score,
        )
        dv_estimation = DialecticalValidityEstimation(
            value=avg_dv,
            t_plus_without_a_plus_yields_t_minus=result_1.dialectical_validity,
            a_plus_without_t_plus_yields_a_minus=result_2.dialectical_validity,
        )
        status = "COHERENT" if estimation.is_coherent else "NOT COHERENT"

        rationale_text = (
            f"Conceptual Coherence Evaluation: {status}\n\n"
            f"T+ without A+ yields T- (CC={result_1.coherence_score:.2f}, DV={result_1.dialectical_validity:.2f}):\n"
            f"  {stmt_1}\n"
            f"  Reasoning: {result_1.reasoning}\n"
            f"  DV reasoning: {result_1.dv_reasoning}\n\n"
            f"A+ without T+ yields A- (CC={result_2.coherence_score:.2f}, DV={result_2.dialectical_validity:.2f}):\n"
            f"  {stmt_2}\n"
            f"  Reasoning: {result_2.reasoning}\n"
            f"  DV reasoning: {result_2.dv_reasoning}\n\n"
            f"Coherence requires both CC scores >= {CONCEPTUAL_COHERENCE_THRESHOLD} (average: {avg_score:.2f}).\n"
            f"DV (dialectical naturalness, avg {avg_dv:.2f}) annotates only — no threshold."
        )
        rationale = Rationale(text=rationale_text)

        # Only commit and attach if PP is committed
        if perspective.is_committed:
            estimation.set_target(perspective)
            dv_estimation.set_target(perspective)
            rationale.set_explanation_target(perspective)
            rationale.commit()
            self._report.node_created(rationale)

            estimation.set_provider(rationale)
            estimation.commit()
            self._report.node_created(estimation)

            dv_estimation.set_provider(rationale)
            dv_estimation.commit()
            self._report.node_created(dv_estimation)

        result = ControlStatementsCheckResult(
            estimation=estimation,
            dv_estimation=dv_estimation,
            rationale=rationale,
            t_plus_without_a_plus_yields_t_minus_statement=stmt_1,
            t_plus_without_a_plus_yields_t_minus_score=result_1.coherence_score,
            t_plus_without_a_plus_yields_t_minus_reasoning=result_1.reasoning,
            a_plus_without_t_plus_yields_a_minus_statement=stmt_2,
            a_plus_without_t_plus_yields_a_minus_score=result_2.coherence_score,
            a_plus_without_t_plus_yields_a_minus_reasoning=result_2.reasoning,
            t_plus_without_a_plus_yields_t_minus_dv=result_1.dialectical_validity,
            a_plus_without_t_plus_yields_a_minus_dv=result_2.dialectical_validity,
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

        prompt = f"""{context_section}Rate this control statement on two independent scales:

{statement}

The pattern "[Positive] without [Balancing factor] yields [Negative]" tests whether
the absence of a balancing positive aspect naturally leads to the negative/shadow aspect.

1. Conceptual Coherence (CC) — is the statement logically meaningful?
- 0.9-1.0: Highly coherent, clear logical/causal relationship
- 0.7-0.9: Coherent, reasonable logical connection
- 0.5-0.7: Somewhat coherent, plausible but weak
- 0.3-0.5: Weak coherence, tenuous connection
- 0.0-0.3: Not coherent, no clear logical relationship

2. Dialectical Validity (DV) — is the dialectical relationship natural, judged
independently of coherence? A statement can be perfectly coherent yet dialectically
distorted (e.g. one pole arbitrarily privileged, outcomes enforced by coercion or
ideology rather than natural system dynamics). 1.0 = natural, balanced, generative;
0.0 = forced, artificial, distorted. Ignore factual correctness; evaluate only the
quality of the dialectical relationship as a generative principle."""

        conversation = ConversationFacilitator()
        return await conversation.submit(
            response_model=CoherenceEvaluationDto,
            user_content=prompt,
        )

    def _build_report(self, result: ControlStatementsCheckResult) -> None:
        """Build execution report from result."""
        score_1 = result.t_plus_without_a_plus_yields_t_minus_score
        score_2 = result.a_plus_without_t_plus_yields_a_minus_score
        avg_score = (score_1 + score_2) / 2

        dv_1 = result.t_plus_without_a_plus_yields_t_minus_dv
        dv_2 = result.a_plus_without_t_plus_yields_a_minus_dv
        avg_dv = (dv_1 + dv_2) / 2

        self._report.artifacts["t_plus_without_a_plus_yields_t_minus"] = score_1
        self._report.artifacts["a_plus_without_t_plus_yields_a_minus"] = score_2
        self._report.artifacts["average"] = avg_score
        self._report.artifacts["is_coherent"] = result.is_coherent
        self._report.artifacts["dialectical_validity"] = avg_dv

        self._report.ok = True
        status = "COHERENT" if result.is_coherent else "NOT COHERENT"
        self._report.summary = (
            f"Control Statements Check: {status} "
            f"(T+\\A+→T-={score_1:.2f}, "
            f"A+\\T+→A-={score_2:.2f}, "
            f"avg={avg_score:.2f}, DV={avg_dv:.2f})"
        )
