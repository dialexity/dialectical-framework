"""
PerspectiveValidation: Validates a Perspective's tetrad structure.

Runs two validation checks:
1. Control Statements Check - Tests logical coherence via control statements (LLM)
2. Empirical Inequalities - Checks aspect complementarities for synthesis viability

A Perspective passes validation if:
- Both control statement scores >= 0.7 (conceptually coherent)
- Empirical inequalities are satisfied (synthesis is possible)

Empirical Inequalities:
    1. diff_t ≈ diff_a ≥ 0.1 (balanced differentials, tolerance=0.15)
    2. KS(T+) > 0.4 and KS(A+) > 0.4 (positive aspects above threshold)
    3. KS(T-) < 0.6 and KS(A-) < 0.6 (negative aspects below threshold)

    Where:
    - diff_t = KS(T+) - KS(T-) — quality gap on T-side
    - diff_a = KS(A+) - KS(A-) — quality gap on A-side
    - KS = complementarity_s = (complementarity_t + complementarity_a) / 2

Usage:
    validator = PerspectiveValidation()
    result = await validator.execute(perspective=pp, text="optional context")

    if result.is_valid:
        print("Perspective is valid")
    else:
        print(f"Validation failed: {result.failure_reasons}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from dialectical_framework.agents.executable_capability import \
    ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.features.control_statements_check import (
    ControlStatementsCheck, ControlStatementsCheckResult)
from dialectical_framework.graph.relationships.polarity_relationship import \
    AspectRelationship

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective


# --- Thresholds ---

# Minimum differential (diff_t, diff_a) for valid synthesis
DIFFERENTIAL_MINIMUM = 0.1

# Maximum difference between diff_t and diff_a for balanced tetrad
DIFFERENTIAL_BALANCE_TOLERANCE = 0.15

# Positive aspects (T+, A+) must have KS above this threshold
POSITIVE_ASPECT_KS_MINIMUM = 0.4

# Negative aspects (T-, A-) must have KS below this threshold
NEGATIVE_ASPECT_KS_MAXIMUM = 0.6


# --- Result ---


@dataclass
class EmpiricalInequalitiesResult:
    """Result of empirical inequalities validation.

    Raw values (KS, diff_t, diff_a) are available on Perspective.
    """

    is_valid: Optional[bool] = None  # None if data missing
    failure_reasons: list[str] = field(default_factory=list)


@dataclass
class PerspectiveValidationResult:
    """Result of Perspective validation."""

    control_statements: ControlStatementsCheckResult
    empirical_inequalities: EmpiricalInequalitiesResult

    # Aggregated failure reasons from all checks
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if both validations pass."""
        return (
            self.control_statements.is_coherent
            and self.empirical_inequalities.is_valid is True
        )

    @property
    def is_conceptually_coherent(self) -> bool:
        """True if control statements check passes."""
        return self.control_statements.is_coherent

    @property
    def is_empirically_valid(self) -> Optional[bool]:
        """True if empirical inequalities check passes."""
        return self.empirical_inequalities.is_valid


# --- Capability ---


class PerspectiveValidation(ExecutableCapability[PerspectiveValidationResult]):
    """
    Validates a Perspective's tetrad structure.

    Runs two validation checks:
    1. Control Statements Check - Uses LLM to evaluate control statements
    2. Empirical Inequalities - Checks aspect complementarities for synthesis viability

    Validation passes if:
    - Both control statement scores >= 0.7 (logically coherent)
    - Empirical inequalities are satisfied (balanced differentials, aspect thresholds)
    """

    def __init__(self) -> None:
        self._cs_capability = ControlStatementsCheck()

    async def execute(
        self,
        perspective: Perspective,
        text: str = "",
    ) -> PerspectiveValidationResult:
        """
        Validate a Perspective's tetrad structure.

        Args:
            perspective: The Perspective to validate (must be committed and complete)
            text: Optional context for control statements evaluation

        Returns:
            PerspectiveValidationResult with validation results

        Raises:
            ValueError: If Perspective is not committed or not complete
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not perspective.is_committed:
            raise ValueError("Perspective must be committed before validation")

        if not perspective.is_complete():
            raise ValueError("Perspective must be complete (have all 6 positions)")

        failure_reasons: list[str] = []

        # Run control statements check (LLM-based)
        cs_result = await self._cs_capability.execute(
            perspective=perspective,
            text=text,
        )

        if not cs_result.is_coherent:
            est = cs_result.estimation
            failure_reasons.append(
                f"Conceptual coherence failed: "
                f"T+\\A+→T-={est.t_plus_without_a_plus_yields_t_minus:.2f}, "
                f"A+\\T+→A-={est.a_plus_without_t_plus_yields_a_minus:.2f} (both must be >= 0.7)"
            )

        # Run empirical inequalities check
        ei_result = self._check_empirical_inequalities(perspective)
        failure_reasons.extend(ei_result.failure_reasons)

        result = PerspectiveValidationResult(
            control_statements=cs_result,
            empirical_inequalities=ei_result,
            failure_reasons=failure_reasons,
        )

        self._build_report(result)
        return result

    def _get_aspect_ks(self, perspective: Perspective, position: str) -> Optional[float]:
        """Get complementarity_s (KS) for an aspect position."""
        manager = perspective.get_relationship_manager_by_position(position)
        result = manager.get()
        if not result:
            return None
        _, rel = result
        if isinstance(rel, AspectRelationship):
            return rel.complementarity_s
        return None

    def _check_empirical_inequalities(
        self,
        perspective: Perspective,
    ) -> EmpiricalInequalitiesResult:
        """
        Check empirical inequalities for synthesis viability.

        Conditions:
        1. diff_t ≈ diff_a ≥ 0.1 (balanced differentials)
        2. KS(T+) > 0.4 and KS(A+) > 0.4 (positive aspects threshold)
        3. KS(T-) < 0.6 and KS(A-) < 0.6 (negative aspects threshold)
        """
        from dialectical_framework.graph.nodes.perspective import (
            POSITION_A_MINUS, POSITION_A_PLUS, POSITION_T_MINUS,
            POSITION_T_PLUS)

        failure_reasons: list[str] = []

        # Get KS values for all aspects
        ks_t_plus = self._get_aspect_ks(perspective, POSITION_T_PLUS)
        ks_t_minus = self._get_aspect_ks(perspective, POSITION_T_MINUS)
        ks_a_plus = self._get_aspect_ks(perspective, POSITION_A_PLUS)
        ks_a_minus = self._get_aspect_ks(perspective, POSITION_A_MINUS)

        # Calculate differentials (use Perspective properties)
        diff_t = perspective.diff_t
        diff_a = perspective.diff_a

        # Check for missing data
        if any(ks is None for ks in [ks_t_plus, ks_t_minus, ks_a_plus, ks_a_minus]):
            failure_reasons.append(
                "Empirical inequalities: missing complementarity data"
            )
            return EmpiricalInequalitiesResult(
                is_valid=None,
                failure_reasons=failure_reasons,
            )

        is_valid = True

        # Condition 2: Positive aspects KS > 0.4
        if ks_t_plus <= POSITIVE_ASPECT_KS_MINIMUM:
            failure_reasons.append(
                f"Positive aspect threshold: KS(T+)={ks_t_plus:.2f} must be > {POSITIVE_ASPECT_KS_MINIMUM}"
            )
            is_valid = False
        if ks_a_plus <= POSITIVE_ASPECT_KS_MINIMUM:
            failure_reasons.append(
                f"Positive aspect threshold: KS(A+)={ks_a_plus:.2f} must be > {POSITIVE_ASPECT_KS_MINIMUM}"
            )
            is_valid = False

        # Condition 3: Negative aspects KS < 0.6
        if ks_t_minus >= NEGATIVE_ASPECT_KS_MAXIMUM:
            failure_reasons.append(
                f"Negative aspect threshold: KS(T-)={ks_t_minus:.2f} must be < {NEGATIVE_ASPECT_KS_MAXIMUM}"
            )
            is_valid = False
        if ks_a_minus >= NEGATIVE_ASPECT_KS_MAXIMUM:
            failure_reasons.append(
                f"Negative aspect threshold: KS(A-)={ks_a_minus:.2f} must be < {NEGATIVE_ASPECT_KS_MAXIMUM}"
            )
            is_valid = False

        # Condition 1: diff_t ≈ diff_a ≥ 0.1
        if diff_t < DIFFERENTIAL_MINIMUM:
            failure_reasons.append(
                f"Differential minimum: diff_t={diff_t:.2f} must be >= {DIFFERENTIAL_MINIMUM}"
            )
            is_valid = False
        if diff_a < DIFFERENTIAL_MINIMUM:
            failure_reasons.append(
                f"Differential minimum: diff_a={diff_a:.2f} must be >= {DIFFERENTIAL_MINIMUM}"
            )
            is_valid = False

        # Check differential balance
        if diff_t is not None and diff_a is not None:
            diff_balance = abs(diff_t - diff_a)
            if diff_balance > DIFFERENTIAL_BALANCE_TOLERANCE:
                failure_reasons.append(
                    f"Differential balance: |diff_t - diff_a|={diff_balance:.2f} "
                    f"must be <= {DIFFERENTIAL_BALANCE_TOLERANCE}"
                )
                is_valid = False

        return EmpiricalInequalitiesResult(
            is_valid=is_valid,
            failure_reasons=failure_reasons,
        )

    def _build_report(self, result: PerspectiveValidationResult) -> None:
        """Build execution report from result."""
        cs = result.control_statements.estimation
        ei = result.empirical_inequalities

        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["t_plus_without_a_plus_yields_t_minus"] = (
            cs.t_plus_without_a_plus_yields_t_minus
        )
        self._report.artifacts["a_plus_without_t_plus_yields_a_minus"] = (
            cs.a_plus_without_t_plus_yields_a_minus
        )
        self._report.artifacts["cs_coherent"] = result.is_conceptually_coherent
        self._report.artifacts["ei_valid"] = ei.is_valid

        if result.failure_reasons:
            self._report.artifacts["failure_reasons"] = result.failure_reasons

        self._report.ok = True
        status = "VALID" if result.is_valid else "INVALID"
        self._report.summary = (
            f"Perspective Validation: {status} "
            f"(CS={result.is_conceptually_coherent}, EI={ei.is_valid})"
        )
