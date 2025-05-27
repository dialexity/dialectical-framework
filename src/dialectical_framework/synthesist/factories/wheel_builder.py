from __future__ import annotations

import re
from abc import ABC
from typing import List, Self, Union

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.analyst.wheel_mutator import WheelMutator
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel


class WheelBuilder(ABC):
    def __init__(self, *, text: str = None, config: WheelBuilderConfig = None):
        self._config = config or WheelBuilderConfig()
        self._text = text
        # TODO: This should be pluggable/configurable?
        self._reasoner: DialecticalReasoning = ReasonFastAndSimple(
            text=text,
            config=config,
        )
        self._wheels: List[Wheel] = []

    @property
    def reasoner(self) -> DialecticalReasoning:
        return self._reasoner

    @property
    def wheels(self) -> List[Wheel]:
        return self._wheels

    @property
    def text(self) -> str | None:
        return self._text

    async def build(self, *, theses: List[Union[str, None]] = None) -> List[Wheel]:
        wu_count  = len(theses) if theses else 1
        theses = [t for t in theses or [] if t and t.strip()] or None  # how
        if theses and len(theses) != wu_count:
            raise ValueError(f"Expected {wu_count} theses, got {len(theses)}")
        elif not theses:
            theses = None
            # wu_count amount of theses will be generated automatically

        if wu_count == 1:
            if not theses:
                theses = [await self.reasoner.find_thesis()]

        analyst = ThoughtMapping(
            text=self.text,
            config=self._config
        )

        if not theses:
            cycles: List[Cycle] = await analyst.extract(wu_count)
        else:
            # TODO: arrangements can be of different kinds, we need to rearchitect this part
            cycles: List[Cycle] = await analyst.arrange(theses)

        # TODO: we should actually resequence2 for all cycle1 possibilities, up to a user
        # The first one is the highest probability
        cycle1 = cycles[0]

        wheel_wisdom_units = []
        for dc in cycle1.dialectical_components:
            wu = await self.reasoner.think(thesis=dc.statement)
            wu.t.explanation = dc.explanation

            # Extract numeric part of the alias; default to 0 when absent
            match = re.search(r"\d+", dc.alias)
            idx = int(match.group()) if match else 0
            if idx:
                wu.add_indexes_to_aliases(idx)

            wheel_wisdom_units.append(wu)

        cycles2: List[Cycle] = await analyst.resequence_with_blind_spots(ordered_wisdom_units=wheel_wisdom_units)

        wheels = []
        for cycle2 in cycles2:
            wm = WheelMutator(wisdom_units=wheel_wisdom_units)
            w = Wheel(wm.rearrange_by_causal_sequence(cycle2, mutate=False))
            w.add_cycle([cycle1, cycle2])
            wheels.append(w)

        # Save results for reference
        self._wheels = wheels
        return wheels

    @classmethod
    def load(cls, *, text: str, config: WheelBuilderConfig = None, wheels: List[Wheel] = None) -> Self:
        instance = cls(text=text, config=config)
        if wheels is not None:
            instance._wheels = wheels
        return instance
