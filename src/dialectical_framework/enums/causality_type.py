from __future__ import annotations

from enum import Enum


class CausalityType(str, Enum):
    REALISTIC = "realistic"
    DESIRABLE = "desirable"
    FEASIBLE = "feasible"
    BALANCED = "balanced"
