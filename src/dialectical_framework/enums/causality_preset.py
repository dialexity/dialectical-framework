from __future__ import annotations

from enum import Enum


class CausalityPreset(str, Enum):
    """Preset intents for Cycle dynamics (So What? level)."""

    REALISTIC = "preset:realistic"
    DESIRABLE = "preset:desirable"
    FEASIBLE = "preset:feasible"
    BALANCED = "preset:balanced"
