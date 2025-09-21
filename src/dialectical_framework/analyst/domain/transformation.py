from __future__ import annotations

from pydantic import ConfigDict, Field

from dialectical_framework.protocols.assessable import Assessable
from dialectical_framework.analyst.domain.spiral import Spiral
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


class Transformation(Spiral):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )

    ac_re: WisdomUnit = Field(..., description="Action-reflection wisdom unit")

    def _get_sub_assessables(self) -> list[Assessable]:
        result = super()._get_sub_assessables()
        result.append(self.ac_re)
        return result

    def _calculate_relevance_of_sub_elements_excl_rationales(self) -> list[float]:
        parts = []
        parts.extend(super()._calculate_relevance_of_sub_elements_excl_rationales())

        relevance = self.ac_re.calculate_relevance()
        if relevance is not None:
            parts.append(relevance)
        return parts