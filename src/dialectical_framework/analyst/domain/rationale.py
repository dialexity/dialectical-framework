from __future__ import annotations

from typing import Optional, List

from pydantic import Field

from dialectical_framework.protocols.ratable import Ratable
from dialectical_framework.synthesist.domain.wheel import Wheel
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled


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

    def _apply_own_rating_in_cf(self) -> bool:
        return False  # parent applies rationale.rating

    def calculate_probability(self) -> float | None:
        # Prefer manual if present; else use evidence; else None
        parts: List[float] = []

        if self.probability is not None:
            if self._hard_veto_on_own_zero() and self.probability == 0:
                return self.probability
            if self.probability > 0.0:
                parts.append(self.probability)

        # Wheels spawned by this rationale
        for w in (self.wheels or []):
            p = w.calculate_probability()
            if p is not None:
                parts.append(p)

        # Child rationales (critiques) - aggregate their probabilities too
        for child_rationale in (self.rationales or []):
            p = child_rationale.calculate_probability()
            if p is None:
                continue
            if p > 0.0:
                parts.append(p)

        # Don't fall back to 1.0 to not improve scores for free
        self.calculated_probability = gm_with_zeros_and_nones_handled(parts) if parts else None
        return self.probability

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        parts = []
        # Wheels spawned by this rationale — include as-is
        for w in (self.wheels or []):
            cf = w.calculate_relevance()
            if cf is not None:
                if self._hard_veto_on_own_zero() and cf == 0.0:
                    parts.append(cf)
                if cf > 0:
                    parts.append(cf)
        return parts