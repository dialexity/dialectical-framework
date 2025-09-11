
from pydantic import BaseModel, Field

from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent


class DialecticalComponentsDeck(BaseModel):
    dialectical_components: list[DialecticalComponent] = Field(
        ...,
        description="A list of dialectical components. It can be empty when no dialectical components are found. It might also be filled with only one dialectical component if only one is to be found.",
    )

    def get_aliases_as_cycle_str(self) -> str:
        aliases = self.get_aliases()

        if len(aliases) < 2:
            return ""
        else:
            # Create a simple cycle: first → second → third → ... → first
            cycle_parts = aliases + [aliases[0]]  # Add first element at the end
            return " → ".join(cycle_parts) + "..."

    def get_aliases(self) -> list[str]:
        return [dc.alias for dc in self.dialectical_components]

    def get_by_alias(self, alias: str) -> DialecticalComponent:
        return next(filter(lambda d: d.alias == alias, self.dialectical_components))

    def rearrange_by_aliases(
        self, ordered_aliases: list[str], mutate: bool = False
    ) -> list[DialecticalComponent]:
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
