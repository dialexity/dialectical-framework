from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, final

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
            sub_assessable.calculate_score(alpha=alpha)
        
        # Ensure that the overall probability has been calculated
        probability = self.calculate_probability()
        # Always calculate contextual fidelity, even if probability is None
        cf_w = self.calculate_contextual_fidelity()
        
        if probability is None or cf_w is None:
            # If still None, cannot calculate score
            score = None
        else:
            score = probability * (cf_w ** alpha)

        self.score = score
        return self.score

    def calculate_contextual_fidelity(self) -> float | None:
        """
        If not possible to calculate contextual fidelity, return 1.0 to have neutral impact on overall scoring.
        
        Normally this method shouldn't be called, as it's called by the `calculate_score` method.
        """
        all_fidelities = []
        all_fidelities.extend(self._calculate_contextual_fidelity_for_rationales())
        all_fidelities.extend(self._calculate_contextual_fidelity_for_sub_elements_excl_rationales())
        
        if not all_fidelities:
            fidelity = None
        else:
            fidelity = gm_with_zeros_and_nones_handled(all_fidelities)

        # Save the state. Ratable leaves will override this and will not save, because it's only manual there.
        self.contextual_fidelity = fidelity

        return fidelity

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

    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self) -> list[float]:
        return []

    def _calculate_contextual_fidelity_for_rationales(self) -> list[float]:
        result: list[float] = []
        for rationale in (self.rationales or []):
            evidence = rationale.calculate_contextual_fidelity()

            if evidence is not None:
                weighted = evidence * rationale.rating_or_default()
                if weighted > 0.0:  # SKIP zero (no hard veto from rationales)
                    result.append(weighted)
        return result