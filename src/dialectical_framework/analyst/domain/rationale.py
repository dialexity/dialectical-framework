from __future__ import annotations

from typing import Optional

from pydantic import Field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.protocols.ratable import Ratable
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled
from dialectical_framework.wheel import Wheel

class Rationale(Ratable):
    headline: Optional[str] = Field(default=None)
    summary: Optional[str] = Field(default=None)
    text: Optional[str] = Field(default=None)
    theses: list[str] = Field(default_factory=list, description="Theses of the rationale text.")
    wheels: list[Wheel] = Field(default_factory=list, description="Wheels that are digging deeper into the rationale.")

    def _hard_veto_on_own_zero(self) -> bool:
        """
        Why not veto Rationale by default

        Rationale is commentary/evidence, not structure. It can be refuted by critiques or outweighed by spawned wheels. One mistaken rationale with CF=0 shouldn’t nuke the parent.

        You already have a safe “off” switch: set rationale.rating = 0 → its contribution is ignored without collapsing CF to 0.

        True veto belongs at structural leaves (Components, Transitions), where “this is contextually impossible” should indeed zero things.
        """
        return False

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        result.extend(self.wheels)
        return result

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

    def calculate_evidence_probability(self, *, mutate: bool = True) -> float | None:
        parts: list[float] = []

        # 1) Wheels spawned by this rationale
        for wheel in self.wheels:
            p = wheel.calculate_probability(mutate=mutate)
            if p is not None:
                parts.append(p)

        # 2) Critiques as rationales (include their full probability, not just their wheels)
        for critique in self.rationales:
            p = critique.calculate_evidence_probability(mutate=mutate)
            if p is not None:
                parts.append(p)

        # Child-first: if children exist, use them
        return gm_with_zeros_and_nones_handled(parts) if parts else None

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        probability = self.calculate_evidence_probability(mutate=True)

        if probability is None:
            return 1.0

        if mutate:
            self.probability = probability
        return probability

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Return CF of this rationale from its own CF + children (wheels/critiques),
        but DO NOT apply rationale.rating here. The parent will weight once.
        """
        parts: list[float] = []

        # child rationales (critiques): they themselves must also NOT self-weight their rating
        parts.extend(v for v in (self._calculate_contextual_fidelity_for_rationales(mutate=mutate) or [])
                     if v is not None and v > 0.0)

        # wheels spawned by this rationale (unrated here)
        parts.extend(
            v for v in (self._calculate_contextual_fidelity_for_sub_elements_excl_rationales(mutate=mutate) or [])
            if v is not None and v > 0.0)

        # include own intrinsic CF UNWEIGHTED (no rating here)
        if self.contextual_fidelity is not None:
            own_cf = self.contextual_fidelity
            if own_cf == 0.0 and not self._hard_veto_on_own_zero():
                # ignore zero (no veto) – acts like “no contribution”
                pass
            elif own_cf > 0.0:
                parts.append(own_cf)

        fidelity = gm_with_zeros_and_nones_handled(parts) if parts else 1.0

        # optional cache: only if no manual CF was provided
        if mutate and self.contextual_fidelity is None:
            self.contextual_fidelity = fidelity
        return fidelity
