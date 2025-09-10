from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

if TYPE_CHECKING: # Conditionally import Rationale for type checking only
    from dialectical_framework.analyst.domain.rationale import Rationale

class Assessable(BaseModel, ABC):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    score: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="The final composite score (Pr(S) * CF_S^alpha) for ranking."
    )

    contextual_fidelity: float | None = Field(default=None, description="Grounding in the initial context")

    probability: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="The normalized probability (Pr(S)) of the cycle to exist in reality.",
    )

    rationales: list[Rationale] = Field(default_factory=list, description="Reasoning about this assessable instance")

    @property
    def best_rationale(self) -> Rationale | None:
        if self.rationales and len(self.rationales) > 1:
            return self.rationales[0]

        selected_r = None
        best_score = None  # use None sentinel

        for r in self.rationales or []:
            r_score = r.calculate_score(mutate=False)
            if r_score is not None and (best_score is None or r_score > best_score):
                best_score = r_score
                selected_r = r

        if selected_r is not None:
            return selected_r
        # fallback: first rationale if present
        return self.rationales[0] if self.rationales else None

    @final
    def calculate_score(self, *, alpha: float = 1.0, mutate: bool = True) -> float | None:
        """
        Calculates composite score: Score(X) = Pr(S) × CF_X^α

        Two-layer weighting system:
        - rating: Domain expert weighting (applied during aggregation)
        - alpha: System-level parameter for contextual fidelity importance

        Args:
            alpha: Contextual fidelity exponent
                < 1.0: De-emphasize expert context assessments
                = 1.0: Respect expert ratings fully (default)
                > 1.0: Amplify expert context assessments
        """
        # First, recursively calculate scores for all sub-assessables
        sub_assessables = self._get_sub_assessables()
        for sub_assessable in sub_assessables:
            sub_assessable.calculate_score(alpha=alpha, mutate=mutate)
        
        # Ensure that the overall probability has been calculated
        probability = self.calculate_probability(mutate=mutate)
        # Always calculate contextual fidelity, even if probability is None
        cf_w = self.calculate_contextual_fidelity(mutate=mutate)
        
        if probability is None:
            # If still None, cannot calculate score
            score = None
        else:
            score = probability * (cf_w ** alpha)

        if mutate:
            self.score = score

        return self.score

    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float:
        """
        If not possible to calculate contextual fidelity, return 1.0 to have neutral impact on overall scoring.
        
        Normally this method shouldn't be called, as it's called by the `calculate_score` method.
        """
        all_fidelities = []
        all_fidelities.extend(self._calculate_contextual_fidelity_for_rationales())
        all_fidelities.extend(self._calculate_contextual_fidelity_for_sub_elements_excl_rationales())
        
        if not all_fidelities:
            fidelity = 1.0  # Neutral impact if no components with positive scores
        else:
            fidelity = gm_with_zeros_and_nones_handled(all_fidelities)

        if mutate:
            self.contextual_fidelity = fidelity

        return fidelity

    @abstractmethod
    def calculate_probability(self, *, mutate: bool = True) -> float | None: ...
    """
    Normally this method shouldn't be called, as it's called by the `calculate_score` method.
    """

    def _get_sub_assessables(self) -> list[Assessable]:
        """
        Returns all direct sub-assessable elements contained within this assessable.
        Used for recursive score calculation.
        """
        # IMPORTANT: we must work on a copy, to avoid filling rationales list with garbage
        return [*self.rationales]

    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, *, mutate: bool = True) -> list[float]:
        return []

    @final
    def _calculate_contextual_fidelity_for_rationales(self, *, mutate: bool = True) -> list[float]:
        fids: list[float] = []
        if self.rationales:
            for rationale in self.rationales:
                # IMPORTANT: use the evidence view to avoid 1.0 fallback inflation
                evidence_cf = rationale.calculate_contextual_fidelity_evidence(mutate=mutate)

                if evidence_cf is not None and evidence_cf > 0.0:
                    weighted = evidence_cf * rationale.rating_or_default()
                    if weighted > 0.0:  # skip non-positives after weighting
                        fids.append(weighted)
        return fids

    def _calculate_probability_for_sub_elements_excl_rationales(self, *, mutate: bool = True) -> list[float]:
        return []