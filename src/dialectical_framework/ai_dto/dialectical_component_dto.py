from pydantic import BaseModel, Field


class DialecticalComponentDto(BaseModel):
    alias: str = Field(
        ...,
        description="The user friendly name of the dialectical component such as T, A, T+, A+, etc.",
    )
    statement: str = Field(
        ...,
        description="The dialectical component value that is provided after analysis.",
    )
    explanation: str = Field(
        default="",
        description="The explanation how the dialectical component (statement) is derived.",
    )