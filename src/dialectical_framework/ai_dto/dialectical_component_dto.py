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
        For index>0, inserts or updates the number BEFORE any trailing signs (e.g., "T" → "T1", "T+" → "T1+", "Ac-" → "Ac1-").

        Format: Base + Number + Sign (e.g., T1+, Ac2-, Re3+)
        NOT: Base + Sign + Number (e.g., T+1, Ac-2, Re+3)

        Args:
            index: The 1-based index to set (0 means no index/single component)

        Example:
            >>> dto = DialecticalComponentDto(alias="T", statement="Democracy")
            >>> dto.set_human_friendly_index(1)
            >>> dto.alias
            "T1"
            >>> dto = DialecticalComponentDto(alias="Ac-", statement="Action")
            >>> dto.set_human_friendly_index(1)
            >>> dto.alias
            "Ac1-"
        """
        import re

        if index == 0:
            # Remove the last sequence of digits entirely
            self.alias = re.sub(r"(\d+)(?!.*\d)", "", self.alias)
        else:
            # Try to replace existing digits first
            if re.search(r"\d", self.alias):
                # Replace the last sequence of digits with the new index
                self.alias = re.sub(r"(\d+)(?!.*\d)", str(index), self.alias)
            else:
                # No digits exist, insert before any trailing signs
                match = re.search(r"([+-]+)$", self.alias)
                if match:
                    # Has trailing signs (+ or -), insert index before them
                    # Example: Ac- → Ac1-, Re+ → Re1+
                    base = self.alias[: match.start()]
                    signs = match.group(1)
                    self.alias = f"{base}{index}{signs}"
                else:
                    # No trailing signs, just append the index
                    # Example: T → T1, Ac → Ac1
                    self.alias = f"{self.alias}{index}"

    def get_human_friendly_index(self) -> int:
        """
        Extract the human-friendly index from the alias.

        Finds the LAST sequence of digits in the alias (e.g., "T1+" → 1, "Ac2-" → 2).

        Returns:
            The numeric index from the alias (e.g., "T1" → 1, "Ac2-" → 2, "T" → 0)

        Example:
            >>> dto = DialecticalComponentDto(alias="T2", statement="Democracy")
            >>> dto.get_human_friendly_index()
            2
            >>> dto = DialecticalComponentDto(alias="Ac1-", statement="Action")
            >>> dto.get_human_friendly_index()
            1
            >>> dto = DialecticalComponentDto(alias="T", statement="Freedom")
            >>> dto.get_human_friendly_index()
            0
        """
        import re
        # Find the last sequence of digits in the alias
        match = re.search(r"(\d+)(?!.*\d)", self.alias)
        return int(match.group(1)) if match else 0