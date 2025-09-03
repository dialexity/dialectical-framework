from typing import Union
from dialectical_framework.analyst.domain.rationale import Rationale


class Critique(Rationale):
    """A Critique represents a critical analysis that can recursively contain other critiques.

    The point_of_concern can be either a basic Rationale or another Critique,
    allowing for deep chains of critical analysis.
    """
    point_of_concern: Rationale
    score: float
