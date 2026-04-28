"""
Resolve the appropriate CausalitySequencer from a Cycle/Wheel intent string.

The intent stored on a Cycle is the assessment strategy:
- Known preset (e.g. "preset:balanced") -> specific sequencer subclass
- Free-form criteria text -> CausalitySequencerCriteria
- None/empty -> CausalitySequencerBalanced (default)
- "preset:auto" -> error (must be resolved upstream before storing on Cycle)
"""

from __future__ import annotations

from typing import Optional

from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.features.causality.causality_sequencer import (
    CausalitySequencer,
)

# Build lookup: maps lowercase preset values and short names to preset enum members
# e.g. "preset:balanced" -> BALANCED, "balanced" -> BALANCED
_PRESET_LOOKUP: dict[str, CausalityPreset] = {}
for _preset in CausalityPreset:
    _PRESET_LOOKUP[_preset.value.lower()] = _preset
    # Short name: strip "preset:" prefix
    _short = _preset.value.split(":", 1)[-1].lower()
    _PRESET_LOOKUP[_short] = _preset

# Maps preset enum members to their sequencer factory functions
_SEQUENCER_FACTORIES: dict[CausalityPreset, type] = {}


def _get_factories() -> dict[CausalityPreset, type]:
    """Lazy-load sequencer classes to avoid circular imports."""
    if not _SEQUENCER_FACTORIES:
        from dialectical_framework.features.causality.causality_sequencer_balanced import (
            CausalitySequencerBalanced,
        )
        from dialectical_framework.features.causality.causality_sequencer_desirable import (
            CausalitySequencerDesirable,
        )
        from dialectical_framework.features.causality.causality_sequencer_feasible import (
            CausalitySequencerFeasible,
        )
        from dialectical_framework.features.causality.causality_sequencer_realistic import (
            CausalitySequencerRealistic,
        )

        _SEQUENCER_FACTORIES[CausalityPreset.BALANCED] = CausalitySequencerBalanced
        _SEQUENCER_FACTORIES[CausalityPreset.DESIRABLE] = CausalitySequencerDesirable
        _SEQUENCER_FACTORIES[CausalityPreset.FEASIBLE] = CausalitySequencerFeasible
        _SEQUENCER_FACTORIES[CausalityPreset.REALISTIC] = CausalitySequencerRealistic
    return _SEQUENCER_FACTORIES


def resolve_sequencer(intent: Optional[str] = None) -> CausalitySequencer:
    """
    Resolve the appropriate CausalitySequencer from a Cycle/Wheel intent.

    Args:
        intent: The intent string stored on the Cycle/Wheel.
            - None/empty -> default balanced sequencer
            - Known preset value (e.g. "preset:balanced") or short name ("balanced")
            - "preset:auto" -> raises (must be resolved before storing on Cycle)
            - Any other string -> CausalitySequencerCriteria (free-form criteria)

    Returns:
        Configured CausalitySequencer instance

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
            "before storing on Cycle — it should never reach resolve_sequencer"
        )

    if preset_enum is not None:
        factories = _get_factories()
        return factories[preset_enum]()

    # Not a known preset — treat as free-form criteria text
    from dialectical_framework.features.causality.causality_sequencer_criteria import (
        CausalitySequencerCriteria,
    )

    return CausalitySequencerCriteria(criteria=intent)
