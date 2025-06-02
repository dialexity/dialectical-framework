from typing import List

from openai import BaseModel
from pydantic import Field

from dialectical_framework.cycle import Cycle
from dialectical_framework.wisdom_unit import WisdomUnit


class WheelHelper(BaseModel):
    wisdom_units: List[WisdomUnit] = Field(
        ...,
        description="A list of wisdom units, i.e. a list of sets of interdependent dialectical components",
    )

    def rearrange_by_causal_sequence(self, cycle: Cycle, mutate: bool = True):
        """
        We expect the cycle to be on the middle ring where theses and antitheses reside.
        This way we can swap the wisdom unit oppositions if necessary.
        """
        all_aliases = []
        if cycle.causality_direction == "counterclockwise":
            for dc in reversed(cycle.dialectical_components):
                all_aliases.append(dc.alias)
        else:
            for dc in cycle.dialectical_components:
                all_aliases.append(dc.alias)

        unique_aliases = dict.fromkeys(all_aliases)

        if len(unique_aliases) != 2*len(self.wisdom_units):
            raise ValueError("Not all aliases are present in the causal sequence")

        wu_sorted = []
        wu_processed = []
        for alias in unique_aliases:
            for wu in self.wisdom_units:
                if any(item is wu for item in wu_processed):
                    continue
                if wu.t.alias == alias:
                    wu_sorted.append(wu)
                    wu_processed.append(wu)
                    break
                if wu.a.alias == alias:
                    wu_sorted.append(wu.swap_segments(mutate=mutate))
                    wu_processed.append(wu)
                    break

        if len(wu_sorted) != len(self.wisdom_units):
            raise ValueError("Not all wisdom units were mapped in the causal sequence")

        if mutate:
            self.wisdom_units[:] = wu_sorted
            return self.wisdom_units
        else:
            return wu_sorted