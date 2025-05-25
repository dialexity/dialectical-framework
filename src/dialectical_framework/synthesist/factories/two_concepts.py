import re
from typing import List

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class TwoConcepts(WheelBuilder):
    def __init__(self, *, theses: List[str] = None):
        if theses and len(theses) != 2:
            raise ValueError(f"TwoConcepts can have only two theses, got: {len(theses)}")

        if theses and any(not thesis or not thesis.strip() for thesis in theses):
            raise ValueError("All theses must be non-empty strings")

        self._theses = theses

    async def build(self, text: str, config: WheelBuilderConfig = None) -> List[Wheel]:
        analyst = ThoughtMapping(
            text=text,
            config=config
        )

        if not self._theses:
            cycles: List[Cycle] = await analyst.extract(2)
        else:
            cycles: List[Cycle] = await analyst.arrange(self._theses)

        # With two concepts we have only one possible cycle T1 -> T2 -> T1
        cycle = cycles[0]

        reasoner = ReasonFastAndSimple(
            text=text,
            config=config
        )
        wheel_wisdom_units = []
        for dc in cycle.dialectical_components:
            wu = await reasoner.think(thesis=dc.statement)
            wu.t.explanation = dc.explanation

            # Extract the numeric part of the alias; default to 0 when absent
            match = re.search(r"\d+", dc.alias)
            idx = int(match.group()) if match else 0
            if idx:
                wu.add_indexes_to_aliases(idx)

            wheel_wisdom_units.append(wu)

        w = Wheel(wheel_wisdom_units)
        w.add_cycle(cycle)
        return [w]