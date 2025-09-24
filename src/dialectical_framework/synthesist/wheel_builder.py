from __future__ import annotations

from typing import Dict, Union

from dependency_injector.wiring import Provide

from dialectical_framework.ai_dto.dto_mapper import (map_from_dto,
                                                     map_list_from_dto)
from dialectical_framework.analyst.domain.cycle import Cycle
from dialectical_framework.synthesist.domain.dialectical_component import DialecticalComponent
from dialectical_framework.synthesist.domain.dialectical_components_deck import \
    DialecticalComponentsDeck
from dialectical_framework.enums.di import DI
from dialectical_framework.protocols.causality_sequencer import \
    CausalitySequencer
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.thesis_extractor import ThesisExtractor
from dialectical_framework.synthesist.domain.synthesis import (ALIAS_S_MINUS, ALIAS_S_PLUS, Synthesis)
from dialectical_framework.synthesist.polarity.polarity_reasoner import \
    PolarityReasoner
from dialectical_framework.synthesist.domain.wheel import Wheel, WheelSegmentReference
from dialectical_framework.synthesist.domain.wheel_segment import ALIAS_T
from dialectical_framework.synthesist.domain.wisdom_unit import WisdomUnit


class WheelBuilder(SettingsAware):
    def __init__(
        self,
        thesis_extractor: ThesisExtractor = Provide[DI.thesis_extractor],
        causality_sequencer: CausalitySequencer = Provide[DI.causality_sequencer],
        polarity_reasoner: PolarityReasoner = Provide[DI.polarity_reasoner],
        *,
        text: str = "",
        wheels: list[Wheel] = None,
    ):
        self.__text = text
        self.__wheels: list[Wheel] = wheels or []

        # TODO: reloading singletons isn't very good design here, because we're guessing the parameters...

        self.__extractor = thesis_extractor
        self.__extractor.reload(text=text)

        self.__sequencer = causality_sequencer
        self.__sequencer.reload(text=text)

        self.__reasoner = polarity_reasoner
        self.__reasoner.reload(text=text)

    @property
    def wheel_permutations(self) -> list[Wheel]:
        return self.__wheels

    @property
    def text(self) -> str | None:
        return self.__text

    @property
    def extractor(self) -> ThesisExtractor:
        return self.__extractor

    @property
    def reasoner(self) -> PolarityReasoner:
        return self.__reasoner

    @property
    def sequencer(self) -> CausalitySequencer:
        return self.__sequencer

    async def t_cycles(self, *, theses: list[Union[str, None]] = None) -> list[Cycle]:
        if theses is None:
            # No theses provided, generate one automatically
            t = await self.extractor.extract_single_thesis()
            t.alias = ALIAS_T
            theses = [t]
        else:
            # Handle mixed None and str values
            final_theses: list[DialecticalComponent | None] = []
            none_positions = []

            # First pass: collect provided theses and identify positions that need generation
            for i, thesis in enumerate(theses):
                if thesis is None or (isinstance(thesis, str) and not thesis.strip()):
                    none_positions.append(i)
                    final_theses.append(None)  # Placeholder
                else:
                    provided_thesis = DialecticalComponent(
                        alias=f"{ALIAS_T}",
                        statement=thesis,
                    )
                    provided_thesis.set_human_friendly_index(i + 1)
                    final_theses.append(provided_thesis)

            known_theses = [t.statement for t in final_theses if t is not None]

            # Generate all missing theses at once if needed
            if none_positions:
                if len(none_positions) == 1:
                    # Single thesis case: place at the correct original position
                    pos = none_positions[0]
                    generated_thesis = await self.extractor.extract_single_thesis(not_like_these=known_theses)
                    generated_thesis.alias = ALIAS_T
                    generated_thesis.set_human_friendly_index(pos + 1)
                    final_theses[pos] = generated_thesis
                else:
                    # Multiple theses case - extract all missing ones at once
                    t_deck = await self.extractor.extract_multiple_theses(count=len(none_positions), not_like_these=known_theses)
                    generated_theses = t_deck.dialectical_components

                    # Place generated theses in their correct positions
                    for i, pos in enumerate(none_positions):
                        if i < len(generated_theses):
                            generated_theses[i].alias = ALIAS_T
                            generated_theses[i].set_human_friendly_index(pos + 1)
                            final_theses[pos] = generated_theses[i]

                    # Backfill any remaining None (it's a precaution, in case fewer were generated than requested)
                    for pos in none_positions:
                        if final_theses[pos] is None:
                            generated_thesis = await self.extractor.extract_single_thesis(not_like_these=known_theses)
                            generated_thesis.alias = ALIAS_T
                            generated_thesis.set_human_friendly_index(pos + 1)
                            final_theses[pos] = generated_thesis

            theses = final_theses

        cycles: list[Cycle] = await self.__sequencer.arrange(theses)
        return cycles

    async def build_wheel_permutations(
        self, *, theses: list[Union[str, None]] = None, t_cycle: Cycle = None
    ) -> list[Wheel]:
        """
        TODO: theses are used only when t_cycle is not provided. should be single param or so. Refactor
        IMPORTANT: t_cycle is the "path" we take for permutations. If not provided, we'll take the most likely path.
        Do not confuse it with building all wheels for all "paths"
        """
        if t_cycle is None:
            cycles: list[Cycle] = await self.t_cycles(theses=theses)
            # The first one is the highest probability
            t_cycle = cycles[0]

        wheel_wisdom_units = []
        for dc in t_cycle.dialectical_components:
            wu = await self.reasoner.think(thesis=dc.statement)
            if dc.rationales:
                wu.t.rationales.extend(dc.rationales)

            idx = dc.get_human_friendly_index()
            if idx:
                wu.add_indexes_to_aliases(idx)

            wheel_wisdom_units.append(wu)

        cycles: list[Cycle] = await self.__sequencer.arrange(wheel_wisdom_units)

        wheels = []
        for cycle in cycles:
            w = Wheel(
                # copy entities that are shared across the wheels, they should be independent
                [wu.model_copy(deep=True) for wu in _rearrange_by_causal_sequence(wheel_wisdom_units, cycle, mutate=False)],
                t_cycle=t_cycle.model_copy(deep=True),
                ta_cycle=cycle,
            )
            w.calculate_score()
            wheels.append(w)

        # Save results for reference
        self.__wheels = wheels
        return self.wheel_permutations

    async def calculate_syntheses(
        self,
        *,
        wheel: Wheel,
        at: WheelSegmentReference | list[WheelSegmentReference] = None,
    ):
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
            ss_deck_dto = await self.reasoner.find_synthesis(wu)
            ss_deck = DialecticalComponentsDeck(dialectical_components=map_list_from_dto(ss_deck_dto.dialectical_components, DialecticalComponent))
            wu.synthesis = Synthesis(
                t_plus=ss_deck.get_by_alias(ALIAS_S_PLUS),
                t_minus=ss_deck.get_by_alias(ALIAS_S_MINUS),
            )
            idx = wu.t.get_human_friendly_index()
            if idx:
                wu.synthesis.add_indexes_to_aliases(idx)

        wheel.calculate_score()


    async def redefine(
        self, *, modified_statement_per_alias: Dict[str, str]
    ) -> list[Wheel]:
        """
        We can give component statements by alias, e.g., T1 = "New thesis 1", A2+ = "New positive side of antithesis 2"

        Returns a list of wheels with modified statements (updating the internal state)
        """
        if not self.wheel_permutations:
            raise ValueError("No wheels have been built yet")
        if modified_statement_per_alias:
            wheels: list[Wheel] = []
            for wheel in self.wheel_permutations:
                new_wisdom_units: list[WisdomUnit] = []
                is_dirty = False
                for wu in wheel.wisdom_units:
                    modifications = {}
                    for field, alias in wu.field_to_alias.items():
                        dc = wu.get(alias)
                        if not dc:
                            continue
                        if dc.alias in modified_statement_per_alias:
                            modifications[field] = modified_statement_per_alias[
                                dc.alias
                            ]
                    if modifications:
                        is_dirty = True
                        wu_redefined = await self.reasoner.redefine(
                            original=wu, **modifications
                        )
                        idx = wu.t.get_human_friendly_index()
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
                    analyst = self.__sequencer

                    theses: list[str] = []
                    for nwu in new_wisdom_units:
                        if nwu.t.alias.startswith("T"):
                            theses.append(nwu.t.statement)
                        else:
                            theses.append(nwu.a.statement)

                    t_cycles: list[Cycle] = await analyst.arrange(theses)
                    # TODO: we should do this for each t_cycle, not the first one only. Refactor
                    t_cycle = t_cycles[0]

                    wheel_wisdom_units = []
                    for dc in t_cycle.dialectical_components:
                        for nwu in new_wisdom_units:
                            if dc.alias in nwu.t.alias:
                                wheel_wisdom_units.append(nwu)
                            elif dc.alias in nwu.a.alias:
                                wheel_wisdom_units.append(
                                    nwu.swap_segments(mutate=True)
                                )

                    cycles: list[Cycle] = await analyst.arrange(wheel_wisdom_units)

                    for cycle in cycles:
                        w = Wheel(
                            _rearrange_by_causal_sequence(
                                wheel_wisdom_units, cycle, mutate=False
                            ),
                            t_cycle=t_cycle,
                            ta_cycle=cycle,
                        )
                        wheels.append(w)
            self.__wheels = wheels

        for wheel in self.wheel_permutations:
            wheel.calculate_score()

        return self.wheel_permutations


def _rearrange_by_causal_sequence(
    wisdom_units: list[WisdomUnit], cycle: Cycle, mutate: bool = True
) -> list[WisdomUnit]:
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

    if len(unique_aliases) != 2 * len(wisdom_units):
        wu_aliases = [wu.t.alias for wu in wisdom_units] + [
            wu.a.alias for wu in wisdom_units
        ]
        raise ValueError(
            f"Not all aliases are present in the causal sequence. wisdom_unit_aliases={wu_aliases}, cycle_aliases={all_aliases}"
        )

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
