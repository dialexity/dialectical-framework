from typing import List

from pydantic import BaseModel, Field

from dialectical_framework.ai_structured_data.causal_cycle import CausalCycle


class CausalCyclesDeck(BaseModel):
    causal_cycles: List[CausalCycle] = Field(
        ...,
        description="A list of causal circular sequences (cycles). It might also be filled with only one if only one is to be found.",
    )
