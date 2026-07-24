from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.agents.execution_report import Effect


@dataclass(frozen=True, slots=True)
class GraphEvent:
    """A graph mutation event scoped by `sid`, ready for fan-out."""

    sid: str
    effect: Effect
    timestamp: float
