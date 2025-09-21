from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final

from pydantic import BaseModel, ConfigDict, Field, computed_field

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
        description="The final composite score (Pr(S) * R^alpha) for ranking."
    )

    rationales: list[Rationale] = Field(default_factory=list, description="Reasoning about this assessable instance")

    calculated_relevance: float | None = Field(default=None, description="Calculated relevance")
    calculated_probability: float | None = Field(default=None, description="Calculated probability")

    @computed_field
    @property
    def relevance(self) -> float | None:
        return self.calculated_relevance

    @computed_field
    @property
    def probability(self) -> float | None:
        return self.calculated_probability

    @property
    def best_rationale(self) -> Rationale | None:
        selected_r = None
        best_score = None
        for r in (self.rationales or []):
            r_score = r.calculate_score()
            if r_score is not None and (best_score is None or r_score > best_score):
                best_score = r_score
                selected_r = r
        return selected_r or (self.rationales[0] if self.rationales else None)

    @final
    def calculate_score(self, *, alpha: float = 1.0) -> float | None:
        """
        Calculates composite score: Score(X) = Pr(S) × R^α

        Two-layer weighting system:
        - rating: Domain expert weighting (applied during aggregation)
        - alpha: System-level parameter for relevance's importance

        Args:
            alpha: Relevance exponent
                < 1.0: De-emphasize expert context assessments
                = 1.0: Respect expert ratings fully (default)
                > 1.0: Amplify expert context assessments
        """
        # First, recursively calculate scores for all sub-assessables
        sub_assessables = self._get_sub_assessables()
        for sub_assessable in sub_assessables:
            sub_assessable.calculate_score(alpha=alpha)

        # Ensure that the overall probability has been calculated
        probability = self.calculate_probability()
        # Always calculate relevance, even if probability is None
        relevance = self.calculate_relevance()

        # Debug output for score calculation
        # import inspect
        # print(f"SCORE DEBUG {type(self).__name__}: probability={probability}, relevance={relevance}")

        if probability is None or relevance is None:
            # If still None, cannot calculate score
            score = None
        else:
            score = probability * (relevance ** alpha)

        self.score = score
        return self.score

    def calculate_relevance(self) -> float | None:
        """
        If not possible to calculate relevance, return 1.0 to have neutral impact on overall scoring.
        
        Normally this method shouldn't be called, as it's called by the `calculate_score` method.
        """
        all_relevances = []
        all_relevances.extend(self._calculate_relevance_of_rationales())
        all_relevances.extend(self._calculate_relevance_of_sub_elements_excl_rationales())
        
        if not all_relevances:
            relevance = None
        else:
            relevance = gm_with_zeros_and_nones_handled(all_relevances)

        # Save the state. Ratable leaves will override this and will not save, because it's only manual there.
        self.calculated_relevance = relevance
        return relevance

    @abstractmethod
    def calculate_probability(self) -> float | None: ...
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

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        return []

    def _calculate_relevance_of_rationales(self) -> list[float]:
        result: list[float] = []
        for rationale in (self.rationales or []):
            evidence = rationale.calculate_relevance()

            if evidence is not None:
                weighted = evidence * rationale.rating_or_default()
                if weighted > 0.0:  # SKIP zero (no hard veto from rationales)
                    result.append(weighted)
        return result