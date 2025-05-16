from typing import List, Literal

from openai import BaseModel
from pydantic import Field, ConfigDict

from dialectical_framework.dialectical_component import DialecticalComponent


class Cycle(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
    )

    causality_direction: Literal["clockwise", "counterclockwise"] = Field(default="clockwise", description="The direction of causality in the ring.")
    dialectical_components: List[DialecticalComponent] = Field(
        ...,
        description="Dialectical components arranged in the circular causality sequence (cycle)",
    )
    probability: float = Field(default=0, description="The probability 0 to 1 of the cycle to exist in reality.")
    reasoning_explanation: str = Field(default="", description="Explanation why/how this cycle might occur.")
    argumentation: str = Field(default="", description="Circumstances or contexts where this cycle would be most applicable or useful.")

    def pretty(self, *, skip_dialectical_component_explanation = False) -> str:
        if self.causality_direction == "clockwise":
            aliases = [dc.alias for dc in self.dialectical_components]
        else:
            aliases = [dc.alias for dc in reversed(self.dialectical_components)]

        output = [" → ".join(aliases) + f" | Probability: {self.probability}"]

        if self.causality_direction == "clockwise":
            for dc in self.dialectical_components:
                output.append(dc.pretty(skip_explanation=skip_dialectical_component_explanation))
        else:
            for dc in reversed(self.dialectical_components):
                output.append(dc.pretty(skip_explanation=skip_dialectical_component_explanation))

        output.append(f"Reasoning: {self.reasoning_explanation}")
        output.append(f"Argumentation: {self.argumentation}")

        return "\n".join(output)

    def __str__(self):
        return self.pretty()
