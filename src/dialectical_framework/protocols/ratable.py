from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, final, List

from pydantic import ConfigDict, Field, model_validator, computed_field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    pass

class Ratable(Assessable, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    rating: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Importance/quality rating."
    )

    manual_relevance: float | None = Field(default=None, description="Manual override for relevance")
    manual_probability: float | None = Field(default=None, description="Manual override for probability")

    @computed_field
    @property
    def relevance(self) -> float | None:
        if self.calculated_relevance is None:
            return self.manual_relevance
        else:
            return self.calculated_relevance

    @relevance.setter
    def relevance(self, value: float | None):
        self.manual_relevance = value
        self.calculated_relevance = None

    @computed_field
    @property
    def probability(self) -> float | None:
        if self.calculated_probability is None:
            return self.manual_probability
        else:
            return self.calculated_probability

    @probability.setter
    def probability(self, value: float | None):
        self.manual_probability = value
        self.calculated_probability = None

    @model_validator(mode='before')
    @classmethod
    def handle_constructor_args(cls, values):
        """Handle relevance and probability arguments passed to constructor"""
        if isinstance(values, dict):
            # If relevance is passed to constructor, put it in manual_relevance
            if 'relevance' in values:
                values['manual_relevance'] = values.pop('relevance')

            # If probability is passed to constructor, put it in manual_probability
            if 'probability' in values:
                values['manual_probability'] = values.pop('probability')

        return values

    def rating_or_default(self) -> float:
        """
        The default rating is 1.0 when None.
        It's a convenient thing, this way we can estimate higher level CFs and propagate them up and down.
        """
        return self.rating if self.rating is not None else 1.0

    def _hard_veto_on_own_zero(self) -> bool:
        """Default True (structural leaves: DC, Transition). Rationale overrides to False."""
        return True

    def _apply_own_rating_in_cf(self) -> bool:
        """Apply leaf.rating to the leaf's own manual CF inside evidence? True for DC/Transition; False for Rationale."""
        return True

    def calculate_probability(self) -> float | None:
        # Prefer manual if present; else use evidence; else None
        parts: List[float] = []

        if self.probability is not None:
            if self._hard_veto_on_own_zero() and self.probability == 0:
                return self.probability
            if self.probability > 0.0:
                parts.append(self.probability)

        # Child rationales (critiques) - aggregate their probabilities too
        for child_rationale in (self.rationales or []):
            p = child_rationale.calculate_probability()
            if p is None:
                continue
            if p > 0.0:
                parts.append(p)

        # Don't fallback to 1.0 to not improve scores for free
        self.calculated_probability = gm_with_zeros_and_nones_handled(parts) if parts else None
        return self.probability

    def calculate_relevance(self) -> float | None:
        parts: List[float] = []

        # 1) Rated child rationales (helper already applies rationale.rating exactly once)
        parts.extend(
            v for v in (self._calculate_relevance_of_rationales() or [])
            if v is not None
        )

        # 2) Leaf-specific sub-elements (default none; Rationale overrides to include wheels)
        parts.extend(
            v for v in (self._calculate_relevance_of_sub_elements_excl_rationales() or [])
            if v is not None
        )

        # 3) Own manual relevance
        own_r = self.manual_relevance
        if own_r is not None:
            if own_r == 0.0 and self._hard_veto_on_own_zero():
                return own_r  # explicit veto
            if own_r > 0.0:
                val = own_r * (self.rating_or_default() if self._apply_own_rating_in_cf() else 1.0)
                if val > 0.0:
                    parts.append(val)

        # Don't fallback to 1.0 to not improve scores for free
        self.calculated_relevance = gm_with_zeros_and_nones_handled(parts) if parts else None
        return self.relevance

    # Default: no extra sub-elements on generic leaves
    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        return []
