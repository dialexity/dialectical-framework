from pydantic import BaseModel, ConfigDict, Field


class ReciprocalSolutionDto(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )
    problem: str | None = Field(default=None, description="Problem statement")
    linear_action: str | None = Field(
        default=None, description="Solution(s) that transforms T- into A+"
    )
    dialectical_reflection: str | None = Field(
        default=None, description="Complementary solution(s) that transforms A- into T+"
    )
    linear_action_probability: float = Field(
        default=0,
        description="The probability 0 to 1 of the transition.",
    )
    dialectical_reflection_probability: float = Field(
        default=0,
        description="The probability 0 to 1 of the transition.",
    )

    def __str__(self):
        str_pieces = []
        if self.problem:
            str_pieces.append(f"Problem: {self.problem}")
        if self.linear_action:
            str_pieces.append(f"Linear action: {self.linear_action}")
        if self.dialectical_reflection:
            str_pieces.append(f"Dialectical reflection: {self.dialectical_reflection}")
        return "\n".join(str_pieces)
