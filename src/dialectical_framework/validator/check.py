from pydantic import BaseModel, Field


class Check(BaseModel):
    valid: float = Field(
        ...,
        description="For boolean checks, Yes = 1, No = 0 (or True = 1, False = 0). Otherwise it's a float between 0 and 1.",
    )
    explanation: str = Field(
        ...,
        description="A brief explanation how the check was performed to get the resulting value.",
    )
