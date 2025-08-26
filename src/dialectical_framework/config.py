from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from dialectical_framework.enums.causality_type import CausalityType


class Config(BaseModel):
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,  # Makes all fields immutable after construction
    )

    component_length: int
    causality_type: CausalityType
