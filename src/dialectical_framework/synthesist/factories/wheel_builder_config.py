from anthropic import BaseModel


class WheelBuilderConfig(BaseModel):
    component_length: int = 2
