from pydantic import BaseModel, Field, ConfigDict


class ReciprocalSolution(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    linear_action: str | None = Field(default=None, description="Solution(s) that transforms T- into A+")
    dialectical_reflection: str | None = Field(default=None, description="Complementary solution(s) that transforms A- into T+")


