"""
WisdomUnitValidation: Validates a WisdomUnit's tetrad structure.

Runs two validation checks:
1. Control Statements Check - Tests logical coherence via control statements (LLM)
2. Empirical Synthesis - Checks pole complementarities (computed property)

A WisdomUnit passes validation if:
- Both control statement scores >= 0.7 (conceptually coherent)
- Empirical conditions are met (synthesis is possible)

Usage:
    validator = WisdomUnitValidation()
    result = await validator.execute(wisdom_unit=wu, text="optional context")

    if result.is_valid:
        print("WisdomUnit is valid")
    else:
        print(f"Validation failed: {result.failure_reasons}")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from dialectical_framework.agents.brainstorming.capabilities.control_statements_check import (
    ControlStatementsCheck,
    ControlStatementsCheckResult,
)
from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


# --- Result ---

@dataclass
class WisdomUnitValidationResult:
    """Result of WisdomUnit validation."""

    control_statements: ControlStatementsCheckResult
    is_empirically_valid: Optional[bool]

    # Aggregated failure reasons
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """True if both validations pass."""
        return (
            self.control_statements.is_coherent
            and self.is_empirically_valid is True
        )

    @property
    def is_conceptually_coherent(self) -> bool:
        """True if control statements check passes."""
        return self.control_statements.is_coherent


# --- Capability ---

class WisdomUnitValidation(ExecutableCapability[WisdomUnitValidationResult]):
    """
    Validates a WisdomUnit's tetrad structure.

    Runs two validation checks:
    1. Control Statements Check - Uses LLM to evaluate control statements
    2. Empirical Synthesis - Uses WisdomUnit.is_positive_synthesis_empirically_possible

    Validation passes if:
    - Both control statement scores >= 0.7 (logically coherent)
    - Empirical conditions are met (balanced differentials, pole thresholds)
    """

    def __init__(self) -> None:
        self._cs_capability = ControlStatementsCheck()

    async def execute(
        self,
        wisdom_unit: WisdomUnit,
        text: str = "",
    ) -> WisdomUnitValidationResult:
        """
        Validate a WisdomUnit's tetrad structure.

        Args:
            wisdom_unit: The WisdomUnit to validate (must be committed and complete)
            text: Optional context for control statements evaluation

        Returns:
            WisdomUnitValidationResult with validation results

        Raises:
            ValueError: If WisdomUnit is not committed or not complete
        """
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not wisdom_unit.is_committed:
            raise ValueError("WisdomUnit must be committed before validation")

        if not wisdom_unit.is_complete():
            raise ValueError("WisdomUnit must be complete (have all 6 positions)")

        failure_reasons: list[str] = []

        # Run control statements check (LLM-based)
        cs_result = await self._cs_capability.execute(
            wisdom_unit=wisdom_unit,
            text=text,
        )

        if not cs_result.is_coherent:
            est = cs_result.estimation
            failure_reasons.append(
                f"Conceptual coherence failed: "
                f"T+\\A+→T-={est.t_plus_without_a_plus_yields_t_minus:.2f}, "
                f"A+\\T+→A-={est.a_plus_without_t_plus_yields_a_minus:.2f} (both must be >= 0.7)"
            )

        # Check empirical synthesis (computed property)
        is_empirically_valid = wisdom_unit.is_positive_synthesis_empirically_possible

        if is_empirically_valid is None:
            failure_reasons.append("Empirical synthesis: missing complementarity data")
        elif not is_empirically_valid:
            failure_reasons.append("Empirical synthesis: conditions not met")

        result = WisdomUnitValidationResult(
            control_statements=cs_result,
            is_empirically_valid=is_empirically_valid,
            failure_reasons=failure_reasons,
        )

        self._build_report(result)
        return result

    def _build_report(self, result: WisdomUnitValidationResult) -> None:
        """Build execution report from result."""
        cs = result.control_statements.estimation

        self._report.artifacts["is_valid"] = result.is_valid
        self._report.artifacts["t_plus_without_a_plus_yields_t_minus"] = cs.t_plus_without_a_plus_yields_t_minus
        self._report.artifacts["a_plus_without_t_plus_yields_a_minus"] = cs.a_plus_without_t_plus_yields_a_minus
        self._report.artifacts["cs_coherent"] = result.is_conceptually_coherent
        self._report.artifacts["es_valid"] = result.is_empirically_valid

        if result.failure_reasons:
            self._report.artifacts["failure_reasons"] = result.failure_reasons

        self._report.ok = True
        status = "VALID" if result.is_valid else "INVALID"
        self._report.summary = (
            f"WisdomUnit Validation: {status} "
            f"(CS={result.is_conceptually_coherent}, ES={result.is_empirically_valid})"
        )
