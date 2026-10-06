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
from typing import TYPE_CHECKING, Optional, Sequence

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


class TetradCoherenceDto(BaseModel):
    """One tetrad's two control statements, from the JOINT call.

    No DV field, deliberately. DV is an annotation that only `resolve`
    persists (`DialecticalValidityEstimation`) and nothing reads it when
    choosing among drafts — `SketchVerdict` has no DV term — so asking for it
    here would buy output tokens and nothing else. A draft that goes on to be
    persisted is scored by `resolve` afterwards, DV and all.
    """

    tetrad: int = Field(
        description=(
            "The number of the tetrad this verdict scores, exactly as labelled "
            "in the request."
        )
    )
    t_plus_without_a_plus_yields_t_minus: float = Field(
        ge=0.0,
        le=1.0,
        description="Conceptual Coherence (0.0-1.0) of that tetrad's statement (a).",
    )
    a_plus_without_t_plus_yields_a_minus: float = Field(
        ge=0.0,
        le=1.0,
        description="Conceptual Coherence (0.0-1.0) of that tetrad's statement (b).",
    )
    reasoning: str = Field(
        description=(
            "One sentence on the weaker of that tetrad's two statements. A note, "
            "not an essay."
        )
    )


class JointCoherenceEvaluationDto(BaseModel):
    """Every tetrad of one request, scored in one call."""

    verdicts: list[TetradCoherenceDto] = Field(
        description=(
            "One entry per tetrad in the request, in the request's order. Score "
            "every tetrad; omit none."
        )
    )


@dataclass(frozen=True)
class TetradTexts:
    """The four aspect texts of one tetrad — all the control statements need.

    What `score_texts_many` takes, so a caller holding several drafts as text
    cannot mix up the order of four positional strings.
    """

    t_plus: str
    t_minus: str
    a_plus: str
    a_minus: str


def control_statements(
    *, t_plus: str, t_minus: str, a_plus: str, a_minus: str
) -> tuple[str, str]:
    """The paper's two control statements, built from four texts.

    One builder for all three askers (`resolve` off a committed Perspective,
    `score_texts` and `score_texts_many` off bare texts) so the quoting cannot
    drift: a verdict taken before persistence and one taken after must be the
    same question asked of the same words.
    """
    return (
        f'"{t_plus}" without "{a_plus}" yields "{t_minus}"',
        f'"{a_plus}" without "{t_plus}" yields "{a_minus}"',
    )


# --- Shared prompt text ---
#
# Written once because two prompts ask for it: one statement at a time
# (`_evaluate_control_statement`, for `resolve` and `score_texts`) and all of
# several tetrads at once (`score_texts_many`). Re-typed inline the scales
# would drift, and a verdict from one prompt is ranked against a verdict from
# the other (`concerns/tetrad_candidates.py`).

_PATTERN = """The pattern "[Positive] without [Balancing factor] yields [Negative]" tests whether
the absence of a balancing positive aspect naturally leads to the negative/shadow aspect."""

_CC_SCALE = """Conceptual Coherence (CC) — is the statement logically meaningful?
- 0.9-1.0: Highly coherent, clear logical/causal relationship
- 0.7-0.9: Coherent, reasonable logical connection
- 0.5-0.7: Somewhat coherent, plausible but weak
- 0.3-0.5: Weak coherence, tenuous connection
- 0.0-0.3: Not coherent, no clear logical relationship"""

_DV_SCALE = """Dialectical Validity (DV) — is the dialectical relationship natural, judged
independently of coherence? A statement can be perfectly coherent yet dialectically
distorted (e.g. one pole arbitrarily privileged, outcomes enforced by coercion or
ideology rather than natural system dynamics). 1.0 = natural, balanced, generative;
0.0 = forced, artificial, distorted. Ignore factual correctness; evaluate only the
quality of the dialectical relationship as a generative principle."""


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
        stmt_1, stmt_2 = control_statements(
            t_plus=t_plus.prompt_text,
            t_minus=t_minus.prompt_text,
            a_plus=a_plus.prompt_text,
            a_minus=a_minus.prompt_text,
        )

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

    async def score_texts(
        self,
        *,
        t_plus: str,
        t_minus: str,
        a_plus: str,
        a_minus: str,
        text: str = "",
    ) -> tuple[CoherenceEvaluationDto, CoherenceEvaluationDto]:
        """The two control statements on bare texts — no Perspective, no graph.

        What `resolve` does after reading the four aspects off a committed
        node, for a caller holding ONE tetrad as text and wanting DV with it.
        Built by the same statement builder as `resolve`, so a verdict here is
        the same question as the one asked after persistence.

        Not what best-of-N selection uses: a field of drafts goes through
        `score_texts_many`, which asks once for all of them and leaves DV out
        (nothing in selection reads it). Two statements, two calls, both with
        reasoning, is the shape that made judging a third of a card's cost.
        """
        stmt_1, stmt_2 = control_statements(
            t_plus=t_plus, t_minus=t_minus, a_plus=a_plus, a_minus=a_minus
        )
        return await asyncio.gather(
            self._evaluate_control_statement(stmt_1, text),
            self._evaluate_control_statement(stmt_2, text),
        )

    async def score_texts_many(
        self,
        tetrads: Sequence[TetradTexts],
        *,
        text: str = "",
    ) -> list[Optional[TetradCoherenceDto]]:
        """Several tetrads' control statements, all in ONE call.

        What `score_texts` asks for one draft at a time, asked for a whole
        best-of-N field at once. Measured reason (2026-10-06, the first app's
        real entry points through `utils/call_census.py`): per-statement calls
        made judging 6 of the 11 provider calls behind one card and ~3.3k of
        its ~5.1k output tokens — about a third of the card's cost — because
        each call spent ~550 output tokens of reasoning on one sentence. One
        call with a short note per tetrad replaces six.

        The question is unchanged and so is its discipline: the judge sees
        only each tetrad's four aspects (never the thesis or antithesis, see
        `concerns/tetrad_candidates.py`), the statements are built by the same
        builder `resolve` uses, and the prompt forbids comparing the drafts —
        selection stays among independent draws. CC only; `TetradCoherenceDto`
        says why DV is not asked for here.

        Fail-soft per tetrad: a verdict the model omits, or labels with a
        number that is out of range or already filled, comes back `None` for
        that tetrad rather than shifting every later one onto the wrong draft.
        """
        if not tetrads:
            return []

        blocks = []
        for n, tetrad in enumerate(tetrads, 1):
            stmt_a, stmt_b = control_statements(
                t_plus=tetrad.t_plus,
                t_minus=tetrad.t_minus,
                a_plus=tetrad.a_plus,
                a_minus=tetrad.a_minus,
            )
            blocks.append(f"Tetrad {n}:\n(a) {stmt_a}\n(b) {stmt_b}")

        context_section = f"<context>\n{text}\n</context>\n\n" if text else ""
        joined = "\n\n".join(blocks)
        prompt = f"""{context_section}Rate the control statements of {len(tetrads)} tetrads. Each tetrad has two statements, (a) and (b).

{joined}

{_PATTERN}

Rate every statement on one scale:

{_CC_SCALE}

Score each tetrad on its own, against the pattern above and nothing else. These are independent drafts: do not compare them with each other, do not rank them, do not pick a best, and do not let one tetrad's wording move another's score. The order they appear in carries no information. Return one verdict per tetrad, labelled with that tetrad's number."""

        conversation = ConversationFacilitator()
        result = await conversation.submit(
            response_model=JointCoherenceEvaluationDto,
            user_content=prompt,
        )

        placed: list[Optional[TetradCoherenceDto]] = [None] * len(tetrads)
        for verdict in result.verdicts:
            index = verdict.tetrad - 1
            if 0 <= index < len(placed) and placed[index] is None:
                placed[index] = verdict
        return placed

    async def _evaluate_control_statement(
        self,
        statement: str,
        text: str,
    ) -> CoherenceEvaluationDto:
        """Evaluate a single control statement for logical coherence."""
        context_section = f"<context>\n{text}\n</context>\n\n" if text else ""

        prompt = f"""{context_section}Rate this control statement on two independent scales:

{statement}

{_PATTERN}

1. {_CC_SCALE}

2. {_DV_SCALE}"""

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
