from typing import List

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.analyst.wheel_constructor import WheelMutator
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

        cycles: List[Cycle] = await analyst.extract(2)
        # The first one is the highest probability
        cycle = cycles[0]

        reasoner = ReasonFastAndSimple(
            text=text,
            component_length=config.component_length,
        )

        wheel_wisdom_units = []
        for dc in cycle.dialectical_components:
            wu = await reasoner.think(thesis=dc.statement)
            wheel_wisdom_units.append(wu)

        cycles: List[Cycle] = await analyst.resequence_with_blind_spots(ordered_wisdom_units=wheel_wisdom_units)
        # The first one is the highest probability
        cycle = cycles[0]

        wm = WheelMutator(wisdom_units=wheel_wisdom_units)
        wm.rearrange_by_causal_sequence(cycle)

        return Wheel(wm.wisdom_units)

    async def build_multiple(self, text: str, config: WheelBuilderConfig = None) -> List[Wheel]:
        if not config:
            config = WheelBuilderConfig()

        analyst = ThoughtMapping(
            text=text,
            component_length=config.component_length
        )

        cycles: List[Cycle] = await analyst.extract(2)
        wheels: List[Wheel] = []
        for cycle in cycles:
            reasoner = ReasonFastAndSimple(
                text=text,
                component_length=config.component_length,
            )
            wheel_wisdom_units = []
            for dc in cycle.dialectical_components:
                wu = await reasoner.think(thesis=dc.statement)
                wheel_wisdom_units.append(wu)

            wm = WheelMutator(wisdom_units=wheel_wisdom_units)
            wm.rearrange_by_causal_sequence(cycle)

            wheels.append(Wheel(wm.wisdom_units))

        return wheels

