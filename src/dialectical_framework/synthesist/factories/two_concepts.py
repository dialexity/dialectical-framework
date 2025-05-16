import re
from typing import List

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class TwoConcepts(WheelBuilder):
    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        if not config:
            config = WheelBuilderConfig()

        analyst = ThoughtMapping(
            text=text,
            component_length=config.component_length
        )

        cycles: List[Cycle] = await analyst.extract(2)
        # With two concepts we have only one possible cycle T1 -> T2 -> T1
        cycle = cycles[0]

        reasoner = ReasonFastAndSimple(
            text=text,
            component_length=config.component_length,
        )
        wheel_wisdom_units = []
        for dc in cycle.dialectical_components:
            wu = await reasoner.think(thesis=dc.statement)
            wu.t.explanation = dc.explanation

            # Extract numeric part of the alias; default to 0 when absent
            match = re.search(r"\d+", dc.alias)
            idx = int(match.group()) if match else 0
            if idx:
                wu.add_indexes_to_aliases(idx)

            wheel_wisdom_units.append(wu)

        w = Wheel(wheel_wisdom_units)
        w.add_significant_cycle(cycle)
        if len(cycles) > 1:
            w.add_alternative_cycle(cycles[1:])
        return w