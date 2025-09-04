
from pydantic import BaseModel, Field

from dialectical_framework.ai_dto.causal_cycle_dto import CausalCycleDto


class CausalCyclesDeckDto(BaseModel):
    causal_cycles: list[CausalCycleDto] = Field(
        ...,
        description="A list of causal circular sequences (cycles). It might also be filled with only one if only one is to be found.",
    )
