from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, final, List

from pydantic import ConfigDict, Field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING:
    pass

DEFAULT_CONFIDENCE = 0.5

class Ratable(Assessable, ABC):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    rating: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Importance/quality rating."
    )
    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Credibility/reputation/confidence used when aggregating probabilities at Transition."
    )

    def rating_or_default(self) -> float:
        """
        The default rating is 1.0 when None.
        It's a convenient thing, this way we can estimate higher level CFs and propagate them up and down.
        """
        return self.rating if self.rating is not None else 1.0

    def confidence_or_default(self) -> float:
        """
        The default confidence is 0.5 when None. This is a rather technical thing, we are never 100% sure, so 0.5 is ok.
        """
        return self.confidence if self.confidence is not None else DEFAULT_CONFIDENCE

    def _hard_veto_on_own_zero(self) -> bool:
        """Default True (structural leaves: DC, Transition). Rationale overrides to False."""
        return True

    def _apply_own_rating_in_cf(self) -> bool:
        """Apply leaf.rating to the leaf's own manual CF inside evidence? True for DC/Transition; False for Rationale."""
        return True

    def calculate_contextual_fidelity(self) -> float | None:
        """
        We are not saving CF here because it's Ratable - only manual value allowed.
        """
        parts: List[float] = []

        # 1) Rated child rationales (helper already applies rationale.rating exactly once)
        parts.extend(
            v for v in (self._calculate_contextual_fidelity_for_rationales() or [])
            if v is not None and v > 0.0
        )

        # 2) Leaf-specific sub-elements (default none; Rationale overrides to include wheels)
        parts.extend(
            v for v in (self._calculate_contextual_fidelity_for_sub_elements_excl_rationales() or [])
            if v is not None and v > 0.0
        )

        # 3) Own manual CF
        own_cf = self.contextual_fidelity
        if own_cf is not None:
            if own_cf == 0.0 and self._hard_veto_on_own_zero():
                return 0.0  # explicit veto
            if own_cf > 0.0:
                val = own_cf * (self.rating_or_default() if self._apply_own_rating_in_cf() else 1.0)
                if val > 0.0:
                    parts.append(val)

        # Don't fallback to 1.0 to not improve scores for free
        return gm_with_zeros_and_nones_handled(parts) if parts else None

    # Default: no extra sub-elements on generic leaves
    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self) -> list[float]:
        return []
