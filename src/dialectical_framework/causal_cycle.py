from typing import List

from openai import BaseModel
from pydantic import Field


class CausalCycle(BaseModel):
    # Comment on the model is a hint to AI how to render the output. It may work better than Field(..., description=...)
    """
    Causal circular sequence of statements, where each statement is referenced by
    """
    aliases: List[str] = Field(
        ...,
        description="Aliases (not the explicit statements) arranged in the circular causality sequence (cycle) where the last element points to the first",
    )
    probability: float = Field(default=0, description="The probability 0 to 1 of the arranged cycle to exist in reality.")
    reasoning_explanation: str = Field(default="", description="Explanation why/how this cycle might occur.")
    argumentation: str = Field(default="", description="Circumstances or contexts where this cycle would be most applicable or useful.")
