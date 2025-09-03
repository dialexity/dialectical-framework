from __future__ import annotations

from enum import Enum


class Predicate(str, Enum):
    CAUSES = "causes"
    CONSTRUCTIVELY_CONVERGES_TO = "constructively_converges_to"
    TRANSFORMS_TO = "transforms_to"
