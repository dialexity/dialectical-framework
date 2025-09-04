from pydantic import ConfigDict

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
