
from pydantic import BaseModel, Field


class CausalCycleAssessmentDto(BaseModel):
    probability: float = Field(
        default=0,
        description="The probability 0 to 1 of the arranged cycle to exist in reality.",
    )
    reasoning_explanation: str = Field(
        default="", description="Explanation why/how this cycle might occur."
    )
    argumentation: str = Field(
        default="",
        description="Circumstances or contexts where this cycle would be most applicable or useful.",
    )
