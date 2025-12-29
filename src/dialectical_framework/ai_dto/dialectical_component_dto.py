from __future__ import annotations

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

    def set_human_friendly_index(self, index: int) -> None:
        """
        Update the alias to include a human-friendly index number.

        For index=0, strips any existing number from alias (e.g., "T1" → "T").
        For index>0, appends or updates the number (e.g., "T" → "T1", "T1" → "T2").

        Args:
            index: The 1-based index to set (0 means no index/single component)

        Example:
            >>> dto = DialecticalComponentDto(alias="T", statement="Democracy")
            >>> dto.set_human_friendly_index(1)
            >>> dto.alias
            "T1"
            >>> dto.set_human_friendly_index(0)
            >>> dto.alias
            "T"
        """
        # Strip any existing number from the alias
        base_alias = ''.join(c for c in self.alias if not c.isdigit())

        if index == 0:
            # No index for single component
            self.alias = base_alias
        else:
            # Add the index number
            self.alias = f"{base_alias}{index}"

    def get_human_friendly_index(self) -> int:
        """
        Extract the human-friendly index from the alias.

        Returns:
            The numeric index from the alias (e.g., "T1" → 1, "T" → 0)

        Example:
            >>> dto = DialecticalComponentDto(alias="T2", statement="Democracy")
            >>> dto.get_human_friendly_index()
            2
            >>> dto = DialecticalComponentDto(alias="T", statement="Freedom")
            >>> dto.get_human_friendly_index()
            0
        """
        # Extract digits from the end of the alias
        digits = ''.join(c for c in self.alias if c.isdigit())
        return int(digits) if digits else 0