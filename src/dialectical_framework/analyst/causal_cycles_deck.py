from typing import List

from openai import BaseModel
from pydantic import Field

from dialectical_framework.analyst.causal_cycle import CausalCycle


class CausalCyclesDeck(BaseModel):
    causal_cycles: List[CausalCycle] = Field(
        ...,
        description="A list of causal circular sequences (cycles). It might also be filled with only one if only one is to be found.",
    )
