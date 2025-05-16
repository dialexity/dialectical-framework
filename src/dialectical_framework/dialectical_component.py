from openai import BaseModel
from pydantic import Field


class DialecticalComponent(BaseModel):
    alias: str = Field(
        ...,
        description="The user friendly name of the dialectical component such as T, A, T+, A+, etc.",
    )
    statement: str = Field(
        ...,
        description="The dialectical component value that is provided after analysis.",
    )
    explanation: str = Field(
        ...,
        description="The explanation how the dialectical component (statement) is derived.",
    )

    @classmethod
    def from_str(cls, alias: str, statement: str, explanation: str = ""):
        return cls(alias=alias, statement=statement, explanation=explanation)

    def pretty(self, dialectical_component_label: str | None = None, *, skip_explanation = False) -> str:
        if not dialectical_component_label:
            dialectical_component_label = self.alias
        result = f"{dialectical_component_label} = {self.statement}"
        if self.explanation and not skip_explanation:
            result = f"{result}\nExplanation: {self.explanation}"
        return result

    def __str__(self):
        return self.pretty()
