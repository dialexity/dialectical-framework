from __future__ import annotations

from abc import ABC
from statistics import geometric_mean
from typing import TYPE_CHECKING, final

from pydantic import ConfigDict, Field

from dialectical_framework.protocols.assessable import Assessable

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

    def get_rating(self) -> float:
        return self.rating if self.rating is not None else 0.5

    @final
    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        Leaves combine:
          - own intrinsic CF × own rating (if present; 0 is a hard veto),
          - rated rationale CFs (weighted by rationale.rating in base helper).
        Neutral fallback = 1.0. Parent rating never reweights children.
        """
        parts = [v for v in self._calculate_contextual_fidelity_for_rationales(mutate=mutate) if
                 v is not None and v > 0.0]
        parts.extend(
                [v for v in self._calculate_contextual_fidelity_for_sub_elements_excl_rationales(mutate=mutate) if
                 v is not None and v > 0.0])

        own_rating = self.get_rating()
        own_cf = self.contextual_fidelity

        if own_cf is not None and own_rating > 0.0:
            # Handle own contribution explicitly to support '0' veto without passing zero into geometric_mean
            own_val = own_cf * own_rating
            if own_val == 0.0:
                fidelity = 0.0
                if mutate:
                    self.contextual_fidelity = fidelity
                return fidelity
            else:
                # Always include own CF, because Ratable is a "leaf"
                parts.append(own_val)

        if not parts:
            fidelity = 1.0  # neutral if no contributing evidence or rating==0 and no children
        else:
            fidelity = geometric_mean(parts)

        if mutate:
            self.contextual_fidelity = fidelity
        return fidelity
