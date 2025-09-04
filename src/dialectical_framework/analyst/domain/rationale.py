from __future__ import annotations

from statistics import geometric_mean
from typing import Optional, List

from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent
from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.wheel import Wheel


class Rationale(Assessable):
    text: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None)
    theses: List[DialecticalComponent] = Field(default_factory=list, description="Theses of the rationale text.")
    wheels: List[Wheel] = Field(default_factory=list, description="Wheels that are digging deeper into the rationale.")

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Calculate contextual fidelity by aggregating wheel fidelities and critique fidelities.
        No need to pass context - it's already embedded in the dialectical components.
        """
        all_scores = []

        # Collect fidelities from this rationale's wheels
        for wheel in self.wheels:
            wheel_fidelity = wheel.calculate_contextual_fidelity(mutate=mutate)
            if wheel_fidelity is not None and wheel_fidelity > 0.0:
                all_scores.append(wheel_fidelity)

        # Collect fidelities from critiques recursively
        for critique in self.opinions:
            critique_fidelity = critique.calculate_contextual_fidelity(mutate=mutate)
            if critique_fidelity is not None and critique_fidelity > 0.0:
                all_scores.append(critique_fidelity)

        if not all_scores:
            score = 1.0  # Neutral if no dialectical analysis available
        else:
            score = geometric_mean(all_scores)

        if mutate:
            self.contextual_fidelity = score
        return score

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        """
        Calculate probability from wheels in this rationale and recursively from critiques.
        """
        probabilities_list: List[float] = []

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
        for critique in r.opinions:
            self._collect_wheel_probabilities_recursively(critique, probabilities_list, mutate=mutate)
