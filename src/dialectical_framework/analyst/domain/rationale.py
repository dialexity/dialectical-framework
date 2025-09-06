from __future__ import annotations

from statistics import geometric_mean
from typing import Optional

from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.protocols.ratable import Ratable
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
        """
        Calculate probability from wheels in this rationale and recursively from critiques.
        """
        probabilities_list: list[float] = []

        # Collect from this rationale's own wheels
        self._collect_wheel_probabilities_recursively(self, probabilities_list, mutate=mutate)

        # Base case: no wheels available, use directly assigned probability
        probability = self.probability

        if probabilities_list:
            # Recursive case: derive from wheel probabilities
            probability = geometric_mean(probabilities_list)

        if mutate:
            self.probability = probability
        return probability

    def _collect_wheel_probabilities_recursively(self, r: Rationale, probabilities_list: list, mutate: bool = True):
        """
        Recursively collect probabilities from all wheels in rationale and its critiques.
        """

        # Collect from this rationale's wheels
        for wheel in r.wheels:
            wheel_prob = wheel.calculate_probability(mutate=mutate)
            if wheel_prob is not None and wheel_prob > 0.0:
                probabilities_list.append(wheel_prob)

        # Recursively collect from critiques
        for critique in r.rationales:
            self._collect_wheel_probabilities_recursively(critique, probabilities_list, mutate=mutate)
