from typing import List

from pydantic import BaseModel
from pydantic import Field

from dialectical_framework.dialectical_component import DialecticalComponent


class DialecticalComponentsDeck(BaseModel):
    dialectical_components: List[DialecticalComponent] = Field(
        ...,
        description="A list of dialectical components. It can be empty when no dialectical components are found. It might also be filled with only one dialectical component if only one is to be found.",
    )

    def get_by_alias(self, alias: str) -> DialecticalComponent:
        return next(filter(lambda d: d.alias == alias, self.dialectical_components))

    def get_sorted_by_example(self, ordered_aliases: list[str], mutate: bool = False) -> List[DialecticalComponent]:
        # Use dict to maintain first occurrence order while removing duplicates
        unique_aliases = dict.fromkeys(ordered_aliases)

        sorted_components = []
        for alias in unique_aliases:
            component = next((c for c in self.dialectical_components if c.alias == alias), None)
            if component:
                sorted_components.append(component)

        if mutate:
            # mutate the existing list in place instead of rebinding the attribute
            self.dialectical_components[:] = sorted_components
            return self.dialectical_components
        else:
            return sorted_components
