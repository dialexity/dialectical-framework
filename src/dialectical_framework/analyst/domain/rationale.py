from __future__ import annotations

from typing import Optional

from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.ratable import Ratable
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.wheel import Wheel


class Rationale(Ratable):
    headline: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None)
    text: Optional[str] = Field(default=None)
    theses: list[DialecticalComponent] = Field(default_factory=list, description="Theses of the rationale text.")
    wheels: list[Wheel] = Field(default_factory=list, description="Wheels that are digging deeper into the rationale.")

    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, *, mutate: bool = True) -> list[float]:
        """
        CF(rationale) is evidence-driven:
          - If there is child evidence (wheels/critiques), aggregate it.
          - Otherwise, fall back to the rationale's own CF × rating (via get_fidelity()).
        Do NOT apply self.get_rating() to child wheels; the parent that consumes this
        rationale will apply rationale.rating to CF(rationale).
        """
        parts: list[float] = []

        # Wheels spawned by this rationale — include as-is (no rating here)
        for wheel in self.wheels:
            w_cf = wheel.calculate_contextual_fidelity(mutate=mutate)
            if w_cf is not None and w_cf > 0.0:
                parts.append(w_cf)

        return parts

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        parts: list[float] = []

        # 1) Wheels spawned by this rationale
        for wheel in self.wheels:
            p = wheel.calculate_probability(mutate=mutate)
            if p is not None and p > 0.0:
                parts.append(p)

        # 2) Critiques as rationales (include their full probability, not just their wheels)
        for r in self.rationales:
            p = r.calculate_probability(mutate=mutate)
            if p is not None and p > 0.0:
                parts.append(p)

        # Child-first: if children exist, use them; else fallback to manual
        probability = gm_with_zeros_and_nones_handled(parts) if parts else self.probability

        if mutate:
            self.probability = probability
        return probability

