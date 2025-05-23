import re
from typing import List

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.analyst.wheel_mutator import WheelMutator
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class MultipleConcepts(WheelBuilder):
    def __init__(self, how_many: int = 3):
        super().__init__()
        if how_many < 3:
            raise ValueError("Use a different factory for less than 3 concepts")
        self._how_many = how_many

    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        if not config:
            config = WheelBuilderConfig()

        analyst = ThoughtMapping(
            text=text,
            component_length=config.component_length
        )

        cycles: List[Cycle] = await analyst.extract(self._how_many)
        # The first one is the highest probability
        cycle1 = cycles[0]

        reasoner = ReasonFastAndSimple(
            text=text,
            component_length=config.component_length,
        )

        wheel_wisdom_units = []
        for dc in cycle1.dialectical_components:
            wu = await reasoner.think(thesis=dc.statement)
            wu.t.explanation = dc.explanation

            # Extract numeric part of the alias; default to 0 when absent
            match = re.search(r"\d+", dc.alias)
            idx = int(match.group()) if match else 0
            if idx:
                wu.add_indexes_to_aliases(idx)

            wheel_wisdom_units.append(wu)

        cycles: List[Cycle] = await analyst.resequence_with_blind_spots(ordered_wisdom_units=wheel_wisdom_units)
        # The first one is the highest probability
        cycle2 = cycles[0]

        wm = WheelMutator(wisdom_units=wheel_wisdom_units)
        wm.rearrange_by_causal_sequence(cycle2)

        w = Wheel(wm.wisdom_units)
        w.add_significant_cycle([cycle1, cycle2])
        if len(cycles) > 1:
            w.add_alternative_cycle(cycles[1:])
        return w

