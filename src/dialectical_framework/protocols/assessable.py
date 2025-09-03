from abc import ABC, abstractmethod
from typing import final

from pydantic import Field, BaseModel, ConfigDict


class Assessable(ABC, BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    score: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="The final composite score (Pr(S) * CF_S^alpha) for ranking this cycle."
    )

    contextual_fidelity: float | None = Field(default=None, description="How well it's related to the context")

    probability: float | None = Field(
        default=None,
        ge=0.0, le=1.0,
        description="The normalized probability (Pr(S)) of the cycle to exist in reality.",
    )

    @final
    def calculate_score(self, *, alpha: float = 1.0, mutate: bool = True) -> float | None:
        """
        Calculates the final composite score using the formula: Score(X) = Pr(S) × CF_X^α.
        This method also recalculates probability and contextual fidelity to have fresh values,
        so it's the main statistical "recalculation" method.
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
    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        """
        Calculates the overall probability as the multiplication of all transition probabilities.
        Transitions with None or 0.0 probability are skipped (treated as irrelevant).
        If no transitions have positive probabilities, returns None.

        Normally this method shouldn't be called, as it's called by the `calculate_score` method.
        """
