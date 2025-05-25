from anthropic import BaseModel
from pydantic import Field

from dialectical_framework.brain import Brain
from dialectical_framework.utils.config import Config


class WheelBuilderConfig(BaseModel):
    model_config = {
        "arbitrary_types_allowed": True
    }

    component_length: int = 3
    brain: Brain = Field(default_factory=lambda: Brain(ai_model=Config.MODEL, ai_provider=Config.PROVIDER))

    def __str__(self):
        return f"WheelBuilderConfig(component_length={self.component_length}, brain={self.brain})"