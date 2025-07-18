from __future__ import annotations


from pydantic import BaseModel
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
        default="",
        description="The explanation how the dialectical component (statement) is derived.",
    )

    def is_same(self, other: DialecticalComponent) -> bool:
        """
        Determines if the current object is equal to another object based on their attributes.

        This method compares the `alias` and `statement` attributes of the current object
        with those of another object to check if they are identical.

        Args:
            other: The object to compare against the current object.

        Returns:
            bool: True if both `alias` and `statement` attributes of the objects are
            the same, otherwise False.
        """
        return self == other or self.alias == other.alias and self.statement == other.statement

    def pretty(self, dialectical_component_label: str | None = None, *, skip_explanation = False) -> str:
        if not dialectical_component_label:
            dialectical_component_label = self.alias
        result = f"{dialectical_component_label} = {self.statement}"
        if self.explanation and not skip_explanation:
            result = f"{result}\nExplanation: {self.explanation}"
        return result

    def __str__(self):
        return self.pretty()
