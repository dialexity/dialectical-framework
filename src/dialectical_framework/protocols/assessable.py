from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING: # Conditionally import Rationale for type checking only
    from dialectical_framework.analyst.domain.rationale import Rationale



class Assessable(ABC, BaseModel):
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

    rating: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Importance/quality rating of the rationale, used for weighing fidelity scores (applied during aggregation)."
    )
    confidence: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Credibility/reputation/confidence of the expert making probability assessments. Used for weighing probabilities (applied during aggregation)")

    rationales: list[Rationale] = Field(default_factory=list, description="Reasoning about this assessable instance")

    @property
    def best_rationale(self) -> Rationale | None:
        selected_r = None
        score = None
        for r in self.rationales:
            r_score = r.calculate_score(mutate=False)
            if r_score is not None and r_score > score:
                score = r_score
                selected_r = r

        if score is not None:
            return selected_r
        else:
            if self.rationales:
                return self.rationales[0]
            else:
                return None

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
        # Ensure that the overall probability has been calculated
        probability = self.calculate_probability(mutate=mutate)
        if probability is None:
            # If still None, cannot calculate score
            score = None
        else:
            cf_w = self.calculate_contextual_fidelity(mutate=mutate)
            score = probability * (cf_w ** alpha)

        if mutate:
            self.score = score

        return self.score

    @abstractmethod
    def calculate_contextual_fidelity(self, *, mutate: bool = True) -> float: ...
    """
    If not possible to calculate contextual fidelity, return 1.0 to have neutral impact on overall scoring.
    
    Normally this method shouldn't be called, as it's called by the `calculate_score` method.
    """

    @abstractmethod
    def calculate_probability(self, *, mutate: bool = True) -> float | None: ...
    """
    Normally this method shouldn't be called, as it's called by the `calculate_score` method.
    """

    def _calculate_contextual_fidelity_for_rationale_rated(self, *, mutate: bool = True) -> list[float]:
        all_fidelities: list[float] = []
        if self.rationales:
            for rationale in self.rationales:
                rationale_fidelity = rationale.calculate_contextual_fidelity(mutate=mutate)

                # Check if rationale_fidelity is valid (not None and > 0.0)
                if rationale_fidelity is not None and rationale_fidelity > 0.0:
                    rationale_fidelity = rationale_fidelity * rationale.rating

                    # Check again after weighting, in case rating makes it zero
                    if rationale_fidelity > 0.0:
                        all_fidelities.append(rationale_fidelity)
        return all_fidelities