from __future__ import annotations

from abc import ABC
from typing import TYPE_CHECKING, final, List

from pydantic import ConfigDict, Field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING: # Conditionally import Rationale for type checking only
    pass

class Ratable(Assessable, ABC):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    rating: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Importance/quality rating."
    )

    confidence: float | None = Field(
        default=None, ge=0.0, le=1.0,
        description="Credibility/reputation/confidence of the expert making probability assessments. Used for weighing probabilities (applied during aggregation)")

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
        return self.confidence if self.confidence is not None else 0.5

    def _hard_veto_on_own_zero(self) -> bool:
        return True  # default for DC and Transition

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Leaves combine:
          - own intrinsic CF × own rating (if present; 0 may be a hard veto by policy),
          - rated rationale CFs (weighted in the base helper),
          - any subclass sub-elements (e.g., Rationale's wheels), unrated here.
        Neutral fallback = 1.0. Parent rating never reweights children.
        """
        own_cf = self.contextual_fidelity
        own_rating = self.rating_or_default()

        # 1) Hard veto on intrinsic CF == 0, independent of rating (policy-controlled)
        if own_cf is not None and own_cf == 0.0 and self._hard_veto_on_own_zero():
            # Do NOT overwrite the manual CF field; return veto as the effective value
            return 0.0

        # 2) Collect child contributions (already filtered/weighted by helpers)
        parts: List[float] = []
        parts.extend(v for v in (self._calculate_contextual_fidelity_for_rationales(mutate=mutate) or [])
                     if v is not None and v > 0.0)
        parts.extend(
            v for v in (self._calculate_contextual_fidelity_for_sub_elements_excl_rationales(mutate=mutate) or [])
            if v is not None and v > 0.0)

        # 3) Include own positive contribution if present
        if own_cf is not None and own_cf > 0.0 and own_rating > 0.0:
            parts.append(own_cf * own_rating)

        # 4) Aggregate or neutral fallback
        fidelity = gm_with_zeros_and_nones_handled(parts) if parts else 1.0

        # 5) Cache only if there was no manual CF provided (don't clobber human input)
        if mutate and own_cf is None:
            self.contextual_fidelity = fidelity

        return fidelity