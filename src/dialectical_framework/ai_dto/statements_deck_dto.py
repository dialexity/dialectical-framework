from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.ai_dto.statement_dto import \
    StatementDto


class StatementsDeckDto(BaseModel):
    statements: list[StatementDto] = Field(
        ...,
        description="A list of dialectical statements. It can be empty when no statements are found. It might also be filled with only one statement if only one is to be found.",
    )

    def get_aliases_as_cycle_str(self) -> str:
        """
        Generate a cycle string representation from component aliases.

        Returns:
            A string like "T → A → T+ → T" showing the cycle of aliases,
            or empty string if less than 2 components.

        Example:
            >>> deck.get_aliases_as_cycle_str()
            "T → A → T+ → A- → T..."
        """
        aliases = self.get_aliases()

        if len(aliases) < 2:
            return ""
        else:
            # Create a simple cycle: first → second → third → ... → first
            cycle_parts = aliases + [aliases[0]]  # Add first element at the end
            return " → ".join(cycle_parts) + "..."

    def get_aliases(self) -> list[str]:
        """
        Extract all aliases from the statements.

        Returns:
            List of alias strings (e.g., ["T", "A", "T+", "A-"])
        """
        return [dc.alias for dc in self.statements]

    def get_by_alias(self, alias: str) -> StatementDto:
        """
        Retrieve a statement by its alias.

        Args:
            alias: The alias to search for (e.g., "T", "A", "T+")

        Returns:
            The StatementDto with matching alias

        Raises:
            KeyError: If no component with given alias is found
        """
        for dc in self.statements:
            if dc.alias == alias:
                return dc
        raise KeyError(f"No component with alias '{alias}' found. Available: {self.get_aliases()}")

    def rearrange_by_aliases(
        self, ordered_aliases: list[str], mutate: bool = False
    ) -> list[StatementDto]:
        """
        Reorder statements according to a specified alias sequence.

        This method reorders the statements to match the order
        specified in `ordered_aliases`. Duplicates in the alias list are
        removed (first occurrence wins).

        Args:
            ordered_aliases: List of aliases in desired order (e.g., ["T", "A", "T+"])
            mutate: If True, modifies the internal list in place. If False, returns new list.

        Returns:
            The reordered list of StatementDto objects

        Example:
            >>> deck.rearrange_by_aliases(["A", "T", "T+"], mutate=True)
            # deck.statements is now reordered as [A, T, T+]
        """
        # Use dict to maintain first occurrence order while removing duplicates
        unique_aliases = dict.fromkeys(ordered_aliases)

        sorted_components = []
        for alias in unique_aliases:
            component = next(
                (c for c in self.statements if c.alias == alias), None
            )
            if component:
                sorted_components.append(component)

        if mutate:
            # mutate the existing list in place instead of rebinding the attribute
            self.statements[:] = sorted_components
            return self.statements
        else:
            return sorted_components