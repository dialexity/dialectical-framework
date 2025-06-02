from __future__ import annotations

import re
from abc import ABC
from typing import List, Self, Union, Dict

from dialectical_framework.analyst.thought_mapping import ThoughtMapping
from dialectical_framework.analyst.wheel_helper import WheelHelper
from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesist.dialectical_reasoning import DialecticalReasoning
from dialectical_framework.synthesist.factories.wheel_builder_config import WheelBuilderConfig
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.wheel import Wheel
from dialectical_framework.wisdom_unit import WisdomUnit


class WheelBuilder(ABC):
    def __init__(self, *, text: str = None, config: WheelBuilderConfig = None):
        self._config = config or WheelBuilderConfig()
        self._text = text
        # TODO: This should be pluggable/configurable?
        self._reasoner: DialecticalReasoning = ReasonFastAndSimple(
            text=text,
            config=config,
        )
        self._analyst = ThoughtMapping(
            text=self.text,
            config=self._config
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

    async def t_cycles(self, *, theses: List[Union[str, None]] = None) -> List[Cycle]:
        wu_count = len(theses) if theses else 1
        theses = [t for t in theses or [] if t and t.strip()] or None  # how
        if theses and len(theses) != wu_count:
            raise ValueError(f"Expected {wu_count} theses, got {len(theses)}")
        elif not theses:
            theses = None
            # wu_count amount of theses will be generated automatically

        if wu_count == 1:
            if not theses:
                theses = [await self.reasoner.find_thesis()]


        if not theses:
            cycles: List[Cycle] = await self._analyst.extract(wu_count)
        else:
            cycles: List[Cycle] = await self._analyst.arrange(theses)

        return cycles

    async def build(self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None) -> List[Wheel]:
        if t_cycle is None:
            cycles: List[Cycle] = await self.t_cycles(theses=theses)
            # The first one is the highest probability
            t_cycle = cycles[0]


        wheel_wisdom_units = []
        for dc in t_cycle.dialectical_components:
            wu = await self.reasoner.think(thesis=dc.statement)
            wu.t.explanation = dc.explanation

            # Extract the numeric part of the alias; default to 0 when absent
            match = re.search(r"\d+", dc.alias)
            idx = int(match.group()) if match else 0
            if idx:
                wu.add_indexes_to_aliases(idx)

            wheel_wisdom_units.append(wu)

        cycles: List[Cycle] = await self._analyst.arrange(wheel_wisdom_units)

        wheels = []
        for cycle in cycles:
            wm = WheelHelper(wisdom_units=wheel_wisdom_units)
            w = Wheel(wm.rearrange_by_causal_sequence(cycle, mutate=False))
            w.cycle = cycle
            wheels.append(w)

        # Save results for reference
        self._wheels = wheels
        return self._wheels

    async def redefine(self, modified_statement_per_alias: Dict[str, str]) -> List[Wheel]:
        """
            We can give component statements by alias, e.g., T1 = "New thesis 1", A2+ = "New positive side of antithesis 2"

            Returns a list of wheels with modified statements (updating the internal state)
        """
        if not self.wheels:
            raise ValueError("No wheels have been built yet")
        if modified_statement_per_alias:
            wheels = []
            for wheel in self.wheels:
                new_wisdom_units: List[WisdomUnit] = []
                is_dirty = False
                for wu in wheel.wisdom_units:
                    modifications = {}
                    for field, alias in wu.field_to_alias.items():
                        dc = wu.get(alias)
                        if not dc: continue
                        if dc.alias in modified_statement_per_alias:
                            modifications[field] = modified_statement_per_alias[dc.alias]
                    if modifications:
                        is_dirty = True
                        wu_redefined = await self.reasoner.redefine(original=wu, **modifications)
                        # Keep indexing as it was on the original wu
                        match = re.search(r"\d+", wu.t.alias)
                        idx = int(match.group()) if match else 0
                        if idx:
                            wu_redefined.add_indexes_to_aliases(idx)
                    else:
                        wu_redefined = wu
                    new_wisdom_units.append(wu_redefined)
                if not is_dirty:
                    wheels.append(Wheel(new_wisdom_units))
                else:
                    # Recalculate cycles
                    analyst = ThoughtMapping(
                        text=self.text,
                        config=self._config
                    )

                    theses: List[str] = []
                    for nwu in new_wisdom_units:
                        if nwu.t.alias.startswith("T"):
                            theses.append(nwu.t.statement)
                        else:
                            theses.append(nwu.a.statement)

                    t_cycles: List[Cycle] = await analyst.arrange(theses)
                    # TODO: we should do this for each t_cycle, not the first one only. Refactor
                    t_cycle = t_cycles[0]

                    wheel_wisdom_units = []
                    for dc in t_cycle.dialectical_components:
                        for nwu in new_wisdom_units:
                            if dc.alias in nwu.t.alias:
                                wheel_wisdom_units.append(nwu)
                            elif dc.alias in nwu.a.alias:
                                wheel_wisdom_units.append(nwu.swap_segments(mutate=True))

                    cycles: List[Cycle] = await analyst.arrange(wheel_wisdom_units)

                    for cycle in cycles:
                        wm = WheelHelper(wisdom_units=wheel_wisdom_units)
                        w = Wheel(wm.rearrange_by_causal_sequence(cycle, mutate=False))
                        w.cycle = cycle
                        wheels.append(w)
            self._wheels = wheels

        return self._wheels

    @classmethod
    def load(cls, *, text: str, config: WheelBuilderConfig = None, wheels: List[Wheel] = None) -> Self:
        instance = cls(text=text, config=config)
        if wheels is not None:
            instance._wheels = wheels
        return instance