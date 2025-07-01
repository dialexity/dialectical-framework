from __future__ import annotations

from enum import Enum

from anthropic import BaseModel
from pydantic import Field

from dialectical_framework.brain import Brain
from dialectical_framework.utils.config import Config


DEFAULT_COMPONENT_LENGTH = 3

class CausalityType(str, Enum):
    REALISTIC = "realistic"
    DESIRABLE = "desirable"
    FEASIBLE = "feasible"
    BALANCED = "balanced"

class ConfigWheelBuilder(BaseModel):

    model_config = {
        "arbitrary_types_allowed": True
    }

    component_length: int = DEFAULT_COMPONENT_LENGTH
    causality_type: CausalityType = CausalityType.BALANCED

    brain: Brain = Field(default_factory=lambda: Brain(ai_model=Config.MODEL, ai_provider=Config.PROVIDER))

    def __str__(self):
        return f"{self.__class__}(component_length={self.component_length}, brain={self.brain})"