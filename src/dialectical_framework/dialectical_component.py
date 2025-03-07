from openai import BaseModel
from pydantic import Field


class DialecticalComponent(BaseModel):
    statement: str = Field(..., description="The dialectical component that is provided after analysis.")
    explanation: str = Field(..., description="The explanation how the dialectical component (statement) is derived.")

    @classmethod
    def from_str(cls, statement: str, explanation: str = ""):
        return cls(
            statement=statement,
            explanation=explanation
        )