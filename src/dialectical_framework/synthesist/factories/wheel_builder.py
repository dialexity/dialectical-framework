from __future__ import annotations

import re
from typing import List, Self, Union, Dict

from dialectical_framework.cycle import Cycle
from dialectical_framework.synthesis import Synthesis, ALIAS_S_PLUS, ALIAS_S_MINUS
from dialectical_framework.synthesist.dialectical_reasoner import DialecticalReasoner
from dialectical_framework.synthesist.factories.config_wheel_builder import ConfigWheelBuilder
from dialectical_framework.synthesist.reason_fast_and_simple import ReasonFastAndSimple
from dialectical_framework.synthesist.thought_mapper import ThoughtMapper
from dialectical_framework.wheel import Wheel, WheelSegmentReference
from dialectical_framework.wisdom_unit import WisdomUnit


class WheelBuilder:
    def __init__(self, *, text: str = "", config: ConfigWheelBuilder | DialecticalReasoner = None):
        if not config or isinstance(config, ConfigWheelBuilder):
            self.__reasoner: DialecticalReasoner = ReasonFastAndSimple(
                text=text,
                config=config or ConfigWheelBuilder(),
            )
        elif isinstance(config, DialecticalReasoner):
            self.__reasoner = config
            if not text:
                text = self.__reasoner.text
            self.__reasoner.load(text=text)

        self.__text = text

        self.__config = self.__reasoner.config
        self.__analyst = ThoughtMapper(
            text=self.__text,
            config=self.__config
        )
        self.__wheels: List[Wheel] = []

    @property
    def reasoner(self) -> DialecticalReasoner:
        return self.__reasoner

    @property
    def wheel_permutations(self) -> List[Wheel]:
        return self.__wheels

    @property
    def text(self) -> str | None:
        return self.__text

    @property
    def config(self) -> ConfigWheelBuilder:
        return self.__config

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
            cycles: List[Cycle] = await self.__analyst.map(wu_count)
        else:
            cycles: List[Cycle] = await self.__analyst.arrange(theses)

        return cycles

    async def build_wheel_permutations(self, *, theses: List[Union[str, None]] = None, t_cycle: Cycle = None) -> List[Wheel]:
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

        cycles: List[Cycle] = await self.__analyst.arrange(wheel_wisdom_units)

        wheels = []
        for cycle in cycles:
            w = Wheel(_rearrange_by_causal_sequence(wheel_wisdom_units, cycle, mutate=False),
                t_cycle=t_cycle,
                ta_cycle=cycle
            )
            wheels.append(w)

        # Save results for reference
        self.__wheels = wheels
        return self.wheel_permutations

    async def calculate_syntheses(self, wheel: Wheel, at: WheelSegmentReference | List[WheelSegmentReference] = None):
        if wheel not in self.wheel_permutations:
            raise ValueError(f"Wheel permutation {wheel} not found in available wheels")

        wisdom_units = []

        if at is None:
            # Calculate for each
            wisdom_units = wheel.wisdom_units
        elif isinstance(at, list):
            # Calculate for some
            for ref in at:
                wisdom_units.append(wheel.wisdom_unit_at(ref))
        else:
            # Calculate for one
            wisdom_units.append(wheel.wisdom_unit_at(at))

        for wu in wisdom_units:
            ss = await self.reasoner.find_synthesis(wu)
            wu.synthesis = Synthesis(
                t_plus=ss.get_by_alias(ALIAS_S_PLUS),
                t_minus = ss.get_by_alias(ALIAS_S_MINUS)
            )
            # Keep indexing as it was on the original wu
            match = re.search(r"\d+", wu.t.alias)
            idx = int(match.group()) if match else 0
            if idx:
                wu.synthesis.add_indexes_to_aliases(idx)

    async def redefine(self, modified_statement_per_alias: Dict[str, str]) -> List[Wheel]:
        """
            We can give component statements by alias, e.g., T1 = "New thesis 1", A2+ = "New positive side of antithesis 2"

            Returns a list of wheels with modified statements (updating the internal state)
        """
        if not self.wheel_permutations:
            raise ValueError("No wheels have been built yet")
        if modified_statement_per_alias:
            wheels = []
            for wheel in self.wheel_permutations:
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
                    # No modifications were made, so preserve the original wheel
                    wheels.append(wheel)
                else:
                    # Recalculate cycles
                    analyst = ThoughtMapper(
                        text=self.text,
                        config=self.config
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
                        w = Wheel(_rearrange_by_causal_sequence(wheel_wisdom_units, cycle, mutate=False),
                          t_cycle=t_cycle,
                          ta_cycle=cycle,
                        )
                        wheels.append(w)
            self.__wheels = wheels

        return self.wheel_permutations

    @classmethod
    def load(cls, *, text: str, config: ConfigWheelBuilder = None, wheels: List[Wheel] = None) -> Self:
        instance = cls(text=text, config=config)
        if wheels is not None:
            instance.__wheels = wheels
        return instance

def _rearrange_by_causal_sequence(wisdom_units: List[WisdomUnit], cycle: Cycle, mutate: bool = True) -> List[WisdomUnit]:
    """
    We expect the cycle to be on the middle ring where theses and antitheses reside.
    This way we can swap the wisdom unit oppositions if necessary.
    """
    all_aliases = []
    if cycle.causality_direction == "clockwise":
        for dc in cycle.dialectical_components:
            all_aliases.append(dc.alias)
    else:
        for dc in reversed(cycle.dialectical_components):
            all_aliases.append(dc.alias)

    unique_aliases = dict.fromkeys(all_aliases)

    if len(unique_aliases) != 2*len(wisdom_units):
        raise ValueError("Not all aliases are present in the causal sequence")

    wu_sorted = []
    wu_processed = []
    for alias in unique_aliases:
        for wu in wisdom_units:
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

    if len(wu_sorted) != len(wisdom_units):
        raise ValueError("Not all wisdom units were mapped in the causal sequence")

    if mutate:
        wisdom_units[:] = wu_sorted
        return wisdom_units
    else:
        return wu_sorted