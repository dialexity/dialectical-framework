from pydantic import ConfigDict

from dialectical_framework import Assessable
from dialectical_framework.analyst.domain.spiral import Spiral
from dialectical_framework.wisdom_unit import WisdomUnit


class Transformation(
    Spiral,  # THIS MUST BE first, so that AssessableCycle is taken by MRO
    WisdomUnit # THIS MUST BE second
):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        result.extend(Spiral._get_sub_assessables(self))
        result.extend(WisdomUnit._get_sub_assessables(self))
        return result

    def _calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, *, mutate: bool = True) -> list[float]:
        parts1 = Spiral._calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, mutate=mutate)
        parts2 = WisdomUnit._calculate_contextual_fidelity_for_sub_elements_excl_rationales(self, mutate=mutate)
        return parts1 + parts2

    def calculate_probability(self, *, mutate: bool = True) -> float | None:
        # Use the cycle rule from Spiral: product of internal transitions
        prob = Spiral.calculate_probability(self, mutate=mutate)  # explicit to avoid MRO confusion
        if mutate:
            self.probability = prob
        return prob
