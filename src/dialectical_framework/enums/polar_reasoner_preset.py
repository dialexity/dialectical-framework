from __future__ import annotations

from enum import Enum


class PolarReasonerPreset(str, Enum):
    """Preset intents for Perspective/Transformation path (Now What? level)."""

    GENERAL_CONCEPTS = "preset:general_concepts"
    MAJOR_TENSION = "preset:major_tension"
    ACTION_REFLECTION = "preset:action_reflection"
