
from pydantic import BaseModel, Field

from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.analyst.domain.spiral import Spiral
from dialectical_framework.analyst.domain.transformation import Transformation
from dialectical_framework.synthesist.domain.wheel import Wheel


class Interpretation(BaseModel):
    wheel: Wheel
    coherence: float = Field(default=0.0, description="geometric mean of all cycle probabilities")
    t_cycle: Cycle
    ta_cycle: Cycle
    spiral: Spiral
    transformations: list[Transformation]