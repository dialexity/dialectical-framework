"""
Resolve the appropriate CausalityEstimator from a Cycle/Wheel intent string.

The intent stored on a Cycle is the assessment strategy:
- Known preset (e.g. "preset:balanced") -> specific estimator subclass
- Free-form criteria text -> CausalityEstimatorCriteria
- None/empty -> CausalityEstimatorBalanced (default)
- "preset:auto" -> error (must be resolved upstream before storing on Cycle)
"""

from __future__ import annotations

from typing import Optional

from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.features.causality.causality_estimator import (
    CausalityEstimator,
)

# Build lookup: maps lowercase preset values and short names to preset enum members
# e.g. "preset:balanced" -> BALANCED, "balanced" -> BALANCED
_PRESET_LOOKUP: dict[str, CausalityPreset] = {}
for _preset in CausalityPreset:
    _PRESET_LOOKUP[_preset.value.lower()] = _preset
    # Short name: strip "preset:" prefix
    _short = _preset.value.split(":", 1)[-1].lower()
    _PRESET_LOOKUP[_short] = _preset

# Maps preset enum members to their estimator factory functions
_ESTIMATOR_FACTORIES: dict[CausalityPreset, type] = {}


def _get_factories() -> dict[CausalityPreset, type]:
    """Lazy-load estimator classes to avoid circular imports."""
    if not _ESTIMATOR_FACTORIES:
        from dialectical_framework.features.causality.causality_estimator_balanced import (
            CausalityEstimatorBalanced,
        )
        from dialectical_framework.features.causality.causality_estimator_desirable import (
            CausalityEstimatorDesirable,
        )
        from dialectical_framework.features.causality.causality_estimator_feasible import (
            CausalityEstimatorFeasible,
        )
        from dialectical_framework.features.causality.causality_estimator_realistic import (
            CausalityEstimatorRealistic,
        )

        _ESTIMATOR_FACTORIES[CausalityPreset.BALANCED] = CausalityEstimatorBalanced
        _ESTIMATOR_FACTORIES[CausalityPreset.DESIRABLE] = CausalityEstimatorDesirable
        _ESTIMATOR_FACTORIES[CausalityPreset.FEASIBLE] = CausalityEstimatorFeasible
        _ESTIMATOR_FACTORIES[CausalityPreset.REALISTIC] = CausalityEstimatorRealistic
    return _ESTIMATOR_FACTORIES


def resolve_estimator(intent: Optional[str] = None) -> CausalityEstimator:
    """
    Resolve the appropriate CausalityEstimator from a Cycle/Wheel intent.

    Args:
        intent: The intent string stored on the Cycle/Wheel.
            - None/empty -> default balanced estimator
            - Known preset value (e.g. "preset:balanced") or short name ("balanced")
            - "preset:auto" -> raises (must be resolved before storing on Cycle)
            - Any other string -> CausalityEstimatorCriteria (free-form criteria)

    Returns:
        Configured CausalityEstimator instance

    Raises:
        ValueError: If intent is "preset:auto" (unresolved)
    """
    if not intent:
        factories = _get_factories()
        return factories[CausalityPreset.BALANCED]()

    # Check if it's a known preset
    preset_enum = _PRESET_LOOKUP.get(intent.lower())

    if preset_enum == CausalityPreset.AUTO:
        raise ValueError(
            "preset:auto must be resolved by the caller (e.g. BuildWheels) "
            "before storing on Cycle — it should never reach resolve_estimator"
        )

    if preset_enum is not None:
        factories = _get_factories()
        return factories[preset_enum]()

    # Not a known preset — treat as free-form criteria text
    from dialectical_framework.features.causality.causality_estimator_criteria import (
        CausalityEstimatorCriteria,
    )

    return CausalityEstimatorCriteria(criteria=intent)
