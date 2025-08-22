from __future__ import annotations

from enum import Enum


class DialecticalReasoningMode(str, Enum):
    GENERAL_CONCEPTS = "general_concepts"
    MAJOR_TENSION = "major_tension"
    ACTION_REFLECTION = "action_reflection"
