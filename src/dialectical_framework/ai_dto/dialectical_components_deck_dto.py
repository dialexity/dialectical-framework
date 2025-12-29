from __future__ import annotations

from pydantic import BaseModel, Field

from dialectical_framework.ai_dto.dialectical_component_dto import \
    DialecticalComponentDto


class DialecticalComponentsDeckDto(BaseModel):
    dialectical_components: list[DialecticalComponentDto] = Field(
        ...,
        description="A list of dialectical components. It can be empty when no dialectical components are found. It might also be filled with only one dialectical component if only one is to be found.",
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
        Extract all aliases from the dialectical components.

        Returns:
            List of alias strings (e.g., ["T", "A", "T+", "A-"])
        """
        return [dc.alias for dc in self.dialectical_components]

    def get_by_alias(self, alias: str) -> DialecticalComponentDto:
        """
        Retrieve a component by its alias.

        Args:
            alias: The alias to search for (e.g., "T", "A", "T+")

        Returns:
            The DialecticalComponentDto with matching alias

        Raises:
            StopIteration: If no component with given alias is found
        """
        return next(filter(lambda d: d.alias == alias, self.dialectical_components))

    def rearrange_by_aliases(
        self, ordered_aliases: list[str], mutate: bool = False
    ) -> list[DialecticalComponentDto]:
        """
        Reorder components according to a specified alias sequence.

        This method reorders the dialectical components to match the order
        specified in `ordered_aliases`. Duplicates in the alias list are
        removed (first occurrence wins).

        Args:
            ordered_aliases: List of aliases in desired order (e.g., ["T", "A", "T+"])
            mutate: If True, modifies the internal list in place. If False, returns new list.

        Returns:
            The reordered list of DialecticalComponentDto objects

        Example:
            >>> deck.rearrange_by_aliases(["A", "T", "T+"], mutate=True)
            # deck.dialectical_components is now reordered as [A, T, T+]
        """
        # Use dict to maintain first occurrence order while removing duplicates
        unique_aliases = dict.fromkeys(ordered_aliases)

        sorted_components = []
        for alias in unique_aliases:
            component = next(
                (c for c in self.dialectical_components if c.alias == alias), None
            )
            if component:
                sorted_components.append(component)

        if mutate:
            # mutate the existing list in place instead of rebinding the attribute
            self.dialectical_components[:] = sorted_components
            return self.dialectical_components
        else:
            return sorted_components