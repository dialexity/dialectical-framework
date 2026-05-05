"""
TransformationAudit: Concern for auditing transformation feasibility.

Evaluates the practical feasibility of each transition within a Transformation,
creating critique Rationales and FeasibilityEstimations. This serves as the
self-evaluation layer — assessing whether the generated wisdom is actionable.

Usage:
    service = TransformationAudit()
    results = await service.resolve(transformation)
    for result in results:
        print(f"{result.position}: feasibility={result.feasibility}")
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from dialectical_framework.agents.conversation_facilitator import \
    ConversationFacilitator
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.agents.reasonable_concern import \
    ReasonableConcern
from dialectical_framework.graph.estimation_manager import EstimationManager
from dialectical_framework.graph.nodes.estimation import FeasibilityEstimation
from dialectical_framework.graph.nodes.rationale import Rationale
from dialectical_framework.graph.nodes.transformation import (
    POSITION_AC_PLUS, POSITION_RE_PLUS, POSITION_AC_MINUS, POSITION_RE_MINUS,
    POSITION_AC, POSITION_RE,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition


SYSTEM_PROMPT = """You are a practical feasibility auditor for dialectical transformations.

Your role is to critically evaluate whether a proposed transition step is actually implementable
in real-world conditions. You are not evaluating the theoretical soundness — you are evaluating
whether someone could actually DO this.

## Assessment Criteria

- **Resource requirements** (time, money, skills, infrastructure)
- **Political/social resistance** or support factors
- **Structural barriers** or enabling conditions
- **Timeline realism** for achieving the transition
- **Precedent cases** where similar transitions succeeded or failed
- **Contextual constraints** specific to the situation described

## Feasibility Scale

- **0.0-0.2:** Practically impossible under current conditions
- **0.3-0.4:** Extremely difficult, would require major systemic changes
- **0.5-0.6:** Challenging but achievable with significant effort and favorable conditions
- **0.7-0.8:** Moderately feasible with proper planning and resources
- **0.9-1.0:** Highly achievable under current or near-term conditions

Be honest and critical. Most transformations are in the 0.4-0.7 range.
"""


class TransitionAuditDto(BaseModel):
    """LLM response for a single transition feasibility audit."""

    feasibility: float = Field(
        ge=0.0, le=1.0,
        description="Practical feasibility score (0.0-1.0)"
    )
    key_factors: str = Field(
        description="2-3 most critical factors affecting feasibility"
    )
    argumentation: str = Field(
        description="Concise explanation referencing context and evidence"
    )
    success_conditions: str = Field(
        description="What would need to be true for this to succeed"
    )


class TransformationAuditResultDto(BaseModel):
    """Result of auditing one transition position."""

    position: str = Field(description="Position label (e.g., Ac+, Re+)")
    feasibility: float = Field(description="Feasibility score")
    key_factors: str
    argumentation: str
    success_conditions: str


class TransformationAudit(
    ReasonableConcern[list[TransformationAuditResultDto]]
):
    """
    Concern for auditing transformation feasibility.

    Evaluates Ac+ and Re+ transitions (the positive action/reflection paths)
    for practical feasibility, creating critique Rationales that provide
    FeasibilityEstimations on the transition nodes.

    Only audits Ac+ and Re+ by default — these are the actionable paths.
    The negative positions (Ac-, Re-) are failure mode descriptions,
    not action prescriptions, so feasibility doesn't apply the same way.
    """

    def __init__(self) -> None:
        self._conversation = ConversationFacilitator()

    async def resolve(
        self,
        transformation: Transformation,
        input_text: str = "",
        audit_all: bool = False,
    ) -> list[TransformationAuditResultDto]:
        """
        Audit a Transformation's transitions for practical feasibility.

        Args:
            transformation: The Transformation to audit
            input_text: Optional source content for context
            audit_all: If True, audit all 6 positions. Default: only Ac+ and Re+.

        Returns:
            List of audit results with feasibility scores
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)
        self._conversation.set_system_prompt(SYSTEM_PROMPT)

        positions = self._collect_positions(transformation, audit_all)
        if not positions:
            self._report.summary = "No positions to audit"
            return []

        results: list[TransformationAuditResultDto] = []
        estimation_manager = EstimationManager()

        for position_label, transition, rationale in positions:
            audit = await self._audit_transition(
                transition, rationale, input_text
            )
            if not audit:
                continue

            # Create critique Rationale
            critique = Rationale(
                text=(
                    f"**Key Factors:** {audit.key_factors}\n\n"
                    f"**Argumentation:** {audit.argumentation}\n\n"
                    f"**Conditions for Success:** {audit.success_conditions}"
                ),
            )
            critique.set_critiques_target(rationale)
            critique.commit()
            self._report.node_created(critique)

            # Store FeasibilityEstimation on the transition
            estimation_manager.upsert_estimation(
                transition,
                FeasibilityEstimation,
                audit.feasibility,
                provider=critique,
            )

            results.append(TransformationAuditResultDto(
                position=position_label,
                feasibility=audit.feasibility,
                key_factors=audit.key_factors,
                argumentation=audit.argumentation,
                success_conditions=audit.success_conditions,
            ))

        self._report.artifacts["positions_audited"] = len(results)
        self._report.artifacts["avg_feasibility"] = (
            sum(r.feasibility for r in results) / len(results) if results else 0
        )
        self._report.summary = (
            f"Audited {len(results)} positions, "
            f"avg feasibility={self._report.artifacts['avg_feasibility']:.2f}"
        )

        return results

    def _collect_positions(
        self,
        transformation: Transformation,
        audit_all: bool,
    ) -> list[tuple[str, Transition, Rationale]]:
        """Collect (position_label, transition, rationale) tuples to audit."""
        positions_to_check = [
            (POSITION_AC_PLUS, transformation.ac_plus),
            (POSITION_RE_PLUS, transformation.re_plus),
        ]
        if audit_all:
            positions_to_check.extend([
                (POSITION_AC, transformation.ac),
                (POSITION_RE, transformation.re),
                (POSITION_AC_MINUS, transformation.ac_minus),
                (POSITION_RE_MINUS, transformation.re_minus),
            ])

        results = []
        for label, rel_manager in positions_to_check:
            result = rel_manager.get()
            if not result:
                continue
            transition, _ = result
            rationale = transition.best_rationale
            if not rationale:
                continue
            results.append((label, transition, rationale))

        return results

    async def _audit_transition(
        self,
        transition: Transition,
        rationale: Rationale,
        input_text: str,
    ) -> Optional[TransitionAuditDto]:
        """Run feasibility audit on a single transition."""
        source_result = transition.source.get()
        target_result = transition.target.get()
        if not source_result or not target_result:
            return None

        source_text = source_result[0].prompt_text
        target_text = target_result[0].prompt_text

        context_section = (
            f"<context>\n{input_text}\n</context>\n\n" if input_text else ""
        )

        prompt = f"""{context_section}Evaluate the practical feasibility of this transition:

**From:** "{source_text}"
**To:** "{target_text}"

**Proposed path:** {rationale.text}

Assess whether this transition is practically implementable in real-world conditions.
Consider resource requirements, barriers, resistance factors, and timeline realism."""

        try:
            return await self._conversation.isolate().submit(
                response_model=TransitionAuditDto,
                user_content=prompt,
            )
        except Exception:
            return None
