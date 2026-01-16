from __future__ import annotations

import logging
from typing import Dict, Union

from dependency_injector.wiring import Provide

logger = logging.getLogger(__name__)

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.graph_mapper import component_from_dto
from dialectical_framework.enums.di import DI
from dialectical_framework.protocols.causality_sequencer import CausalitySequencer
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.polarity_extractor import PolarityExtractor

# Graph-native models
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.synthesis import Synthesis
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.wisdom_unit import (
    WisdomUnit,
    POSITION_T,
    POSITION_S_PLUS,
    POSITION_S_MINUS,
)
from dialectical_framework.graph.scoring.tarorank import TaroRank

from dialectical_framework.synthesist.polarity.polarity_reasoner import PolarityReasoner


class WheelBuilder(SettingsAware):
    def __init__(
        self,
        polarity_extractor: PolarityExtractor = Provide[DI.polarity_extractor],
        causality_sequencer: CausalitySequencer = Provide[DI.causality_sequencer],
        polarity_reasoner: PolarityReasoner = Provide[DI.polarity_reasoner],
        tarorank: TaroRank = Provide[DI.tarorank],
        *,
        text: str = "",
        wheels: list[Wheel] = None,
    ):
        self.__text = text
        self.__wheels: list[Wheel] = wheels or []

        # TODO: reloading singletons isn't very good design here, because we're guessing the parameters...

        self.__extractor = polarity_extractor
        self.__extractor.reload(text=text)

        self.__sequencer = causality_sequencer
        self.__sequencer.reload(text=text)

        self.__reasoner = polarity_reasoner
        self.__reasoner.reload(text=text)

        self.__tarorank = tarorank

    @property
    def wheel_permutations(self) -> list[Wheel]:
        return self.__wheels

    @property
    def text(self) -> str | None:
        return self.__text

    @property
    def extractor(self) -> PolarityExtractor:
        return self.__extractor

    @property
    def reasoner(self) -> PolarityReasoner:
        return self.__reasoner

    @property
    def sequencer(self) -> CausalitySequencer:
        return self.__sequencer

    @property
    def scorer(self) -> TaroRank:
        return self.__tarorank

    async def t_cycles(self, *, theses: list[Union[str, DialecticalComponent, None]] = None) -> list[Cycle]:
        """
        Generate T-cycles from provided or auto-generated theses.

        Args:
            theses: List of thesis inputs (strings, graph components, or None for auto-generation)

        Returns:
            List of Cycle objects arranged by causality sequencer
        """
        if theses is None:
            # No theses provided, generate one automatically
            t_dto = await self.extractor.extract_single_thesis()
            t = component_from_dto(t_dto)  # Convert DTO → graph node
            theses = [t]
        else:
            # Handle mixed None, str, and DialecticalComponent values
            final_theses: list[DialecticalComponent | None] = []
            none_positions = []

            # First pass: collect provided theses and identify positions that need generation
            for i, thesis in enumerate(theses):
                if thesis is None or (isinstance(thesis, str) and not thesis.strip()):
                    none_positions.append(i)
                    final_theses.append(None)  # Placeholder
                else:
                    if isinstance(thesis, str):
                        # Create graph node from string
                        provided_thesis = DialecticalComponent(statement=thesis)
                        provided_thesis.save()
                    else:  # thesis is already DialecticalComponent (graph node)
                        provided_thesis = thesis
                    final_theses.append(provided_thesis)

            known_theses = [t.statement for t in final_theses if t is not None]

            # Generate all missing theses at once if needed
            if none_positions:
                if len(none_positions) == 1:
                    # Single thesis case: place at the correct original position
                    pos = none_positions[0]
                    generated_thesis_dto = await self.extractor.extract_single_thesis(not_like_these=known_theses)
                    generated_thesis = component_from_dto(generated_thesis_dto)  # Convert DTO → graph node
                    final_theses[pos] = generated_thesis
                else:
                    # Multiple theses case - extract all missing ones at once
                    t_deck_dto = await self.extractor.extract_multiple_theses(
                        count=len(none_positions),
                        not_like_these=known_theses
                    )
                    generated_thesis_dtos = t_deck_dto.dialectical_components

                    # Place generated theses in their correct positions
                    for i, pos in enumerate(none_positions):
                        if i < len(generated_thesis_dtos):
                            generated_thesis = component_from_dto(generated_thesis_dtos[i])  # Convert DTO → graph node
                            final_theses[pos] = generated_thesis

                    # Backfill any remaining None (precaution in case fewer were generated than requested)
                    for pos in none_positions:
                        if final_theses[pos] is None:
                            generated_thesis_dto = await self.extractor.extract_single_thesis(not_like_these=known_theses)
                            generated_thesis = component_from_dto(generated_thesis_dto)  # Convert DTO → graph node
                            final_theses[pos] = generated_thesis

            theses = final_theses

        cycles: list[Cycle] = await self.__sequencer.arrange(theses)
        return cycles

    async def build_wheel_permutations(
        self, *, theses: Union[list[str | DialecticalComponent | None], list[tuple[str | DialecticalComponent | None, str | DialecticalComponent | None]]] = None, t_cycle: Cycle = None
    ) -> list[Wheel]:
        """
        IMPORTANT: t_cycle is the "path" we take for permutations. If not provided, we'll take the most likely path.
        Do not confuse it with building all wheels for all "paths"

        The tuple in the thesis list is used to provide antithesis for the thesis, where the first element is the thesis, the second is the antithesis.
        """
        if t_cycle is None:
            cycles: list[Cycle] = await self.t_cycles(theses=[t[0] if isinstance(t, tuple) else t for t in theses])
            # The first one is the highest probability
            t_cycle = cycles[0]

        wheel_wisdom_units = []
        for dc in t_cycle.dialectical_components:
            # Find antithesis from tuples if provided
            antithesis = None
            if isinstance(theses, list):
                # Handle special case: single tuple with (None, xxx)
                if len(theses) == 1 and isinstance(theses[0], tuple) and theses[0][0] is None:
                    antithesis = theses[0][1]
                else:
                    # Regular case: search for matching thesis in tuples
                    for t in theses:
                        if isinstance(t, tuple):
                            if isinstance(t[0], DialecticalComponent):
                                # Compare by UID (graph-native components are same if UIDs match)
                                if dc.uid == t[0].uid:
                                    antithesis = t[1]
                                    break
                            elif isinstance(t[0], str) and dc.statement == t[0]:
                                antithesis = t[1]
                                break

            wu = await self.reasoner.think(thesis=dc, antithesis=antithesis)
            wheel_wisdom_units.append(wu)

        cycles: list[Cycle] = await self.__sequencer.arrange(wheel_wisdom_units)

        # Create wheels for each TA-cycle permutation
        # In graph-native, multiple wheels can share the same WisdomUnit nodes
        # The different TA-cycles represent different analytical interpretations
        wheels = []
        for cycle in cycles:
            # Create wheel node
            w = Wheel()
            w.save()

            # Connect wisdom units (all cycles use same WUs, different interpretations)
            # IMPORTANT: WUs must be connected BEFORE cycles (validated by connect_t_cycle/connect_ta_cycle)
            for wu in wheel_wisdom_units:
                w.wisdom_units.connect(wu)

            # Connect cycles (T-cycle is the primary path, TA-cycle is the permutation)
            # Uses validated methods that ensure cycle WUs are already in this wheel
            w.connect_t_cycle(t_cycle)
            w.connect_ta_cycle(cycle)

            # Set human-friendly indices on wisdom units if multiple WUs
            if len(wheel_wisdom_units) > 1:
                for idx, wu in enumerate(wheel_wisdom_units, start=1):
                    wu.set_human_friendly_index(idx)

            wheels.append(w)

        # Score all wheels
        for wheel in wheels:
            self.scorer.calculate_score(wheel)

        # Save results for reference
        self.__wheels = wheels
        return self.wheel_permutations

    async def calculate_syntheses(
        self,
        *,
        wheel: Wheel,
        at: Union[WisdomUnit, list[WisdomUnit], None] = None,
    ) -> list[Synthesis]:
        """
        Calculate synthesis for wisdom units in the wheel.

        For each WisdomUnit:
        1. Calls reasoner.find_synthesis() to get S+ and S- components
        2. Creates Synthesis node
        3. Connects S+ and S- components to Synthesis
        4. Connects Synthesis to WisdomUnit

        Args:
            wheel: The Wheel containing wisdom units to synthesize
            at: Optional selector for specific WUs:
                - None: Synthesize ALL WUs (default)
                - WisdomUnit: Synthesize only this WU
                - list[WisdomUnit]: Synthesize only these WUs

        Returns:
            List of created Synthesis nodes

        Raises:
            ValueError: If wheel not built by this WheelBuilder

        Example:
            # Synthesize all WUs
            syntheses = await wheel_builder.calculate_syntheses(wheel=wheel)

            # Synthesize specific WU
            wus = [wu for wu, _ in wheel.wisdom_units.all()]
            syntheses = await wheel_builder.calculate_syntheses(wheel=wheel, at=wus[0])

            # Synthesize multiple WUs
            syntheses = await wheel_builder.calculate_syntheses(wheel=wheel, at=[wus[0], wus[1]])
        """
        # Validation: ensure wheel belongs to this builder
        if wheel not in self.__wheels:
            raise ValueError(f"Wheel not found in this WheelBuilder's wheels. Build the wheel first.")

        # Determine which WUs to synthesize
        if at is None:
            # Synthesize all WUs in the wheel
            wisdom_units = [wu for wu, _ in wheel.wisdom_units.all()]
        elif isinstance(at, list):
            # Synthesize specific WUs (list)
            wisdom_units = at
        else:
            # Synthesize single WU
            wisdom_units = [at]

        syntheses: list[Synthesis] = []

        # Iterate through selected wisdom units
        for wu in wisdom_units:
            # Call reasoner to find synthesis components (returns DTO)
            synthesis_deck_dto = await self.reasoner.find_synthesis(wu)

            # Convert DTOs to graph components
            if len(synthesis_deck_dto.dialectical_components) < 2:
                # Skip if we don't have both S+ and S-
                continue

            # Extract S+ and S- from the deck (should have exactly 2 components)
            synthesis_components = [component_from_dto(dto) for dto in synthesis_deck_dto.dialectical_components]

            # Identify S+ and S- by alias (may be indexed like S2+, S2-)
            # Use DialecticalComponentDto to compute the expected indexed alias
            wu_index = wu.get_human_friendly_index()
            s_plus_alias_dto = DialecticalComponentDto(alias=POSITION_S_PLUS, statement="")
            s_minus_alias_dto = DialecticalComponentDto(alias=POSITION_S_MINUS, statement="")
            s_plus_alias_dto.set_human_friendly_index(wu_index)
            s_minus_alias_dto.set_human_friendly_index(wu_index)

            try:
                s_plus_dto = synthesis_deck_dto.get_by_alias(s_plus_alias_dto.alias)
                s_minus_dto = synthesis_deck_dto.get_by_alias(s_minus_alias_dto.alias)
            except KeyError:
                # Fallback to non-indexed aliases if indexed not found
                try:
                    s_plus_dto = synthesis_deck_dto.get_by_alias(POSITION_S_PLUS)
                    s_minus_dto = synthesis_deck_dto.get_by_alias(POSITION_S_MINUS)
                except KeyError as e:
                    # Skip if S+ or S- not found in the synthesis deck
                    logger.warning(f"Skipping synthesis for WU {wu.uid}: {e}")
                    continue

            s_plus_comp = component_from_dto(s_plus_dto)
            s_minus_comp = component_from_dto(s_minus_dto)

            # Create Synthesis node
            synthesis = Synthesis()
            synthesis.save()

            # Connect S+ and S- to Synthesis with appropriate relationship types
            from dialectical_framework.graph.relationships.polarity_relationship import (
                SPlusRelationship,
                SMinusRelationship,
            )

            synthesis.s_plus.connect(s_plus_comp, relationship=SPlusRelationship(alias=s_plus_alias_dto.alias))
            synthesis.s_minus.connect(s_minus_comp, relationship=SMinusRelationship(alias=s_minus_alias_dto.alias))

            # Connect Synthesis to WisdomUnit
            synthesis.wisdom_unit.connect(wu)

            # Set human-friendly index if WU has one
            if wu_index > 0:
                synthesis.set_human_friendly_index(wu_index)

            syntheses.append(synthesis)

        # Note: Scoring is caller's responsibility.
        # Call scorer.calculate_score(wheel, force=True) after all modifications are complete.
        return syntheses


    async def redefine(
        self, *, modified_statement_per_alias: Dict[str, str]
    ) -> list[Wheel]:
        """
        Redefine component statements by alias.

        Creates new wheels with redefined wisdom units. The original wheels
        and wisdom units are not modified.

        Optimization: If no WUs in a wheel need modification, the original
        wheel is preserved (no cycle recalculation).

        Args:
            modified_statement_per_alias: Map from alias to new statement.
                Examples:
                - "T1": "New thesis 1"
                - "A2+": "New positive side of antithesis 2"
                - "T": "New thesis" (for single WU wheels)

        Returns:
            List of new wheels with redefined wisdom units

        Example:
            new_wheels = await wheel_builder.redefine(
                modified_statement_per_alias={
                    "T1": "Remote work increases autonomy",
                    "A2+": "Async communication enables deep work"
                }
            )
        """
        import re

        if not modified_statement_per_alias:
            # No modifications requested - return originals (is_dirty optimization)
            return self.__wheels

        if not self.__wheels:
            raise ValueError("No wheels available to redefine. Call build_wheel_permutations() first.")

        # Parse aliases to extract position and index
        # Examples: "T1" → (1, "t"), "A2+" → (2, "a_plus"), "T" → (0, "t")
        def parse_alias(alias: str) -> tuple[int, str]:
            """Parse alias to extract WU index and position name."""
            # Extract numeric index if present
            match = re.search(r"(\d+)", alias)
            wu_index = int(match.group(1)) if match else 0

            # Extract base position (strip numbers)
            base_alias = re.sub(r"\d+", "", alias)

            # Map alias to position name
            alias_to_position = {
                "T": "t",
                "T+": "t_plus",
                "T-": "t_minus",
                "A": "a",
                "A+": "a_plus",
                "A-": "a_minus",
            }

            position = alias_to_position.get(base_alias)
            if not position:
                raise ValueError(f"Invalid alias: {alias}. Expected format: T, T+, T-, A, A+, A-, or with numbers (T1, A2+, etc.)")

            return wu_index, position

        # Group modifications by WU index
        modifications_by_wu: Dict[int, Dict[str, str]] = {}
        for alias, statement in modified_statement_per_alias.items():
            wu_index, position = parse_alias(alias)
            if wu_index not in modifications_by_wu:
                modifications_by_wu[wu_index] = {}
            modifications_by_wu[wu_index][position] = statement

        # Create new wheels with redefined WUs
        new_wheels: list[Wheel] = []

        # Cache for recalculated cycles (calculated once per unique WU set)
        recalculated_cycles_cache: dict[tuple[str, ...], tuple[list[Cycle], list[Cycle]]] = {}

        for wheel in self.__wheels:
            # Get wisdom units from this wheel (ordered by their indices)
            wus = sorted(
                [wu for wu, _ in wheel.wisdom_units.all()],
                key=lambda wu: wu.get_human_friendly_index()
            )

            # Check if ANY WU in this wheel needs modification (is_dirty optimization)
            needs_modification = False
            for wu in wus:
                wu_index = wu.get_human_friendly_index()
                if wu_index in modifications_by_wu:
                    needs_modification = True
                    break

            if not needs_modification:
                # No modifications for this wheel - preserve original (is_dirty optimization)
                new_wheels.append(wheel)
                continue

            # Redefine affected WUs
            new_wus: list[WisdomUnit] = []

            for wu in wus:
                wu_index = wu.get_human_friendly_index()

                if wu_index in modifications_by_wu:
                    # Redefine this WU with new statements
                    kwargs = modifications_by_wu[wu_index]
                    new_wu = await self.reasoner.redefine(original=wu, **kwargs)
                    new_wus.append(new_wu)
                else:
                    # Keep original WU (no changes)
                    new_wus.append(wu)

            # Second-level optimization: If no WUs actually changed after redefine,
            # preserve the original wheel (avoid expensive cycle recalculation).
            # reasoner.redefine() returns original WU (same UID) if nothing changed.
            original_wu_uids = [wu.uid for wu in wus]
            new_wu_uids = [wu.uid for wu in new_wus]

            if original_wu_uids == new_wu_uids:
                # Nothing changed - preserve original wheel
                new_wheels.append(wheel)
                continue

            # Recalculate cycles since components have changed
            # Use cache to avoid redundant LLM calls (multiple wheels may share same WUs)
            wu_cache_key = tuple(wu.uid for wu in new_wus)

            if wu_cache_key not in recalculated_cycles_cache:
                # Calculate cycles for this WU set
                thesis_components = [wu.get_component(POSITION_T) for wu in new_wus if wu.get_component(POSITION_T)]
                recalculated_t_cycles = await self.sequencer.arrange(thesis_components)
                recalculated_ta_cycles = await self.sequencer.arrange(new_wus)
                recalculated_cycles_cache[wu_cache_key] = (recalculated_t_cycles, recalculated_ta_cycles)
            else:
                # Reuse cached cycles
                recalculated_t_cycles, recalculated_ta_cycles = recalculated_cycles_cache[wu_cache_key]

            # Find matching T-cycle and TA-cycle for this original wheel
            # Match by structure (alias ordering) to maintain 1-to-1 correspondence
            original_t_cycle_result = wheel.t_cycle.get()
            original_ta_cycle_result = wheel.ta_cycle.get()

            if not original_t_cycle_result or not original_ta_cycle_result:
                raise ValueError(f"Original wheel {wheel.uid} missing cycles")

            original_t_cycle, _ = original_t_cycle_result
            original_ta_cycle, _ = original_ta_cycle_result

            # Helper function to extract alias sequence from a cycle
            def get_alias_sequence(cycle: Cycle, wisdom_units: list[WisdomUnit]) -> list[str]:
                """Extract ordered list of aliases from cycle components."""
                aliases = []
                for comp in cycle.dialectical_components:
                    # Try each WU until we find the one containing this component
                    for wu in wisdom_units:
                        try:
                            alias = comp.get_alias(wu)
                            aliases.append(alias)
                            break  # Found it, move to next component
                        except ValueError:
                            continue  # Not in this WU, try next
                return aliases

            # Get alias sequences for original cycles
            original_wus = [wu for wu, _ in wheel.wisdom_units.all()]
            original_t_aliases = get_alias_sequence(original_t_cycle, original_wus)
            original_ta_aliases = get_alias_sequence(original_ta_cycle, original_wus)

            # Helper function to check if two alias sequences represent the same structure (allowing rotation)
            def is_same_alias_structure(seq1: list[str], seq2: list[str]) -> bool:
                """Check if sequences are the same allowing rotation."""
                if len(seq1) != len(seq2):
                    return False
                if set(seq1) != set(seq2):
                    return False
                if len(seq1) <= 1:
                    return True
                return any(
                    seq1 == seq2[i:] + seq2[:i]
                    for i in range(len(seq2))
                )

            # Find matching new T-cycle
            matching_t_cycle = None
            for new_t_cycle in recalculated_t_cycles:
                new_t_aliases = get_alias_sequence(new_t_cycle, new_wus)
                if is_same_alias_structure(original_t_aliases, new_t_aliases):
                    matching_t_cycle = new_t_cycle
                    break

            if not matching_t_cycle:
                # If no match found, use first one (highest probability)
                matching_t_cycle = recalculated_t_cycles[0] if recalculated_t_cycles else None

            # Find matching new TA-cycle
            matching_ta_cycle = None
            for new_ta_cycle in recalculated_ta_cycles:
                new_ta_aliases = get_alias_sequence(new_ta_cycle, new_wus)
                if is_same_alias_structure(original_ta_aliases, new_ta_aliases):
                    matching_ta_cycle = new_ta_cycle
                    break

            if not matching_ta_cycle:
                # If no match found, use first one (highest probability)
                matching_ta_cycle = recalculated_ta_cycles[0] if recalculated_ta_cycles else None

            # Create exactly one new wheel that corresponds to this original wheel
            new_wheel = Wheel()
            new_wheel.save()

            # Connect wisdom units (must be done BEFORE cycles)
            for wu in new_wus:
                new_wheel.wisdom_units.connect(wu)

            # Connect matched cycles (validated to ensure WUs are in wheel)
            if matching_t_cycle:
                new_wheel.connect_t_cycle(matching_t_cycle)
            if matching_ta_cycle:
                new_wheel.connect_ta_cycle(matching_ta_cycle)

            new_wheels.append(new_wheel)

        # Note: Scoring is caller's responsibility.
        # Call scorer.calculate_score(wheel) after all modifications are complete.

        # Update internal wheels list
        self.__wheels = new_wheels
        return new_wheels
