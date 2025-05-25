import re
from typing import List

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.analyst.wheel_mutator import WheelMutator
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.factories.single_concept import SingleConcept
from dialectical_framework.synthesist.factories.two_concepts import TwoConcepts
from dialectical_framework.synthesist.factories.wheel_builder import WheelBuilder
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class GenericWheelBuilder(WheelBuilder):
    def __init__(self, *, target_wu_count: int = 3, theses: List[str] = None):
        super().__init__()

        self._theses = None
        if theses:
            theses = [thesis for thesis in theses if thesis and thesis.strip()]
            self._theses = theses

        if len(theses) > 0:
            self._target_wu_count = len(theses)
        else:
            self._target_wu_count = max(1, target_wu_count, len(theses))

    async def build(self, text: str, config: WheelBuilderConfig = None) -> Wheel:
        if self._target_wu_count == 2:
            decorated = TwoConcepts(theses=self._theses)
            return await decorated.build(text, config)
        elif self._target_wu_count == 1:
            decorated = SingleConcept(thesis=self._theses[0] if self._theses else None)
            return await decorated.build(text, config)

        analyst = ThoughtMapping(
            text=text,
            config=config
        )

        if not self._theses:
            cycles: List[Cycle] = await analyst.extract(self._target_wu_count)
        else:
            cycles: List[Cycle] = await analyst.arrange(self._theses)

        # The first one is the highest probability
        cycle1 = cycles[0]

        reasoner = ReasonFastAndSimple(
            text=text,
            config=config
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

