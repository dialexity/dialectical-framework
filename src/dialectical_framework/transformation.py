from pydantic import ConfigDict

from dialectical_framework.spiral import Spiral
from dialectical_framework.wisdom_unit import WisdomUnit


class Transformation(Spiral, WisdomUnit):
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
    )
