from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Union

from dependency_injector.wiring import Provide

logger = logging.getLogger(__name__)

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.graph_mapper import component_from_dto
from dialectical_framework.enums.di import DI
from dialectical_framework.protocols.causality_sequencer import CausalitySequencer
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.protocols.polarity_finder import PolarityFinder
from dialectical_framework.protocols.thesis_extractor import ThesisExtractor

# Graph-native models
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
from dialectical_framework.graph.nodes.ideas import Ideas
from dialectical_framework.graph.nodes.input import Input
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.synthesis import Synthesis, POSITION_S_PLUS, POSITION_S_MINUS
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.nodes.wisdom_unit import (
    WisdomUnit,
    POSITION_T,
)
from dialectical_framework.graph.scoring.tarorank import TaroRank

from dialectical_framework.synthesist.polarity.polar_reasoner import PolarReasoner

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.brainstorm import Brainstorm


class WheelBuilder(SettingsAware):
    """
    Wheel builder that orchestrates SOA-ready extractor services.

    Accepts either:
    - source: Input or Ideas node (preferred)
    - text: Raw text (creates Input node automatically)
    """

    def __init__(
        self,
        thesis_extractor: ThesisExtractor = Provide[DI.thesis_extractor],
        polarity_finder: PolarityFinder = Provide[DI.polarity_finder],
        causality_sequencer: CausalitySequencer = Provide[DI.causality_sequencer],
        polar_reasoner: PolarReasoner = Provide[DI.polar_reasoner],
        tarorank: TaroRank = Provide[DI.tarorank],
        input_resolver: InputResolver = Provide[DI.input_resolver],
        *,
        source: Union[Input, Ideas, Brainstorm, None] = None,
        text: str | None = None,
        wheels: list[Wheel] = None,
    ):
        """
        Initialize WheelBuilder.

        Args:
            source: Input, Ideas, or Brainstorm node
            text: Direct text (creates Input node if no source provided)
            wheels: Pre-existing wheels (for continuation)
        """
        self.__source = source
        self.__text = text
        self.__input_source: Input | Ideas | None = None  # Lazy: Input/Ideas for extractors
        self.__resolved_text: str | None = None  # Lazy cache
        self.__wheels: list[Wheel] = wheels or []

        self.__thesis_extractor = thesis_extractor
        self.__polarity_finder = polarity_finder
        self.__sequencer = causality_sequencer
        self.__reasoner = polar_reasoner
        self.__tarorank = tarorank
        self.__input_resolver = input_resolver

    async def _get_input_source(self) -> Union[Input, Ideas]:
        """
        Get or create an Input/Ideas source for extractors.

        Priority:
        1. If source is Input or Ideas, use it directly
        2. If source is Brainstorm, get its first Input
        3. If text provided, create Input node with text as content
        """
        if self.__input_source is not None:
            return self.__input_source

        from dialectical_framework.graph.nodes.brainstorm import Brainstorm

        if isinstance(self.__source, (Input, Ideas)):
            self.__input_source = self.__source
        elif isinstance(self.__source, Brainstorm):
            # Get first Input from Brainstorm
            inputs = list(self.__source.inputs.all())
            if inputs:
                self.__input_source, _ = inputs[0]
            else:
                # No inputs in brainstorm - create one
                input_node = Input(content=self.__text or "")
                input_node.save()
                self.__source.inputs.connect(input_node)
                self.__input_source = input_node
        elif self.__text is not None:
            # Create Input from text
            input_node = Input(content=self.__text)
            input_node.save()
            self.__input_source = input_node
        else:
            # No source and no text - create empty Input
            input_node = Input(content="")
            input_node.save()
            self.__input_source = input_node

        return self.__input_source

    async def _get_text(self) -> str:
        """Lazily resolve and cache text content."""
        if self.__resolved_text is not None:
            return self.__resolved_text

        # Direct text takes precedence
        if self.__text is not None:
            self.__resolved_text = self.__text
            return self.__resolved_text

        # Resolve from source
        if self.__source is None:
            self.__resolved_text = ""
            return self.__resolved_text

        from dialectical_framework.graph.nodes.brainstorm import Brainstorm

        if isinstance(self.__source, Input):
            self.__resolved_text = await self.__input_resolver.resolve(self.__source)
        elif isinstance(self.__source, Ideas):
            input_result = self.__source.input.get()
            if input_result:
                input_node, _ = input_result
                self.__resolved_text = await self.__input_resolver.resolve(input_node)
            else:
                self.__resolved_text = ""
        elif isinstance(self.__source, Brainstorm):
            self.__resolved_text = await self.__input_resolver.resolve_all(self.__source)
        else:
            self.__resolved_text = ""

        return self.__resolved_text

    @property
    def wheel_permutations(self) -> list[Wheel]:
        return self.__wheels

    @property
    def text(self) -> str | None:
        """
        Return the direct text if provided.

        For resolved text (from source), use _get_text() which is async.
        This property is for backward compatibility with decorators.
        """
        return self.__text

    @property
    def source(self) -> Union[Input, Ideas, Brainstorm, None]:
        """Return the source node if provided."""
        return self.__source

    @property
    def input_resolver(self) -> InputResolver:
        """Return the input resolver."""
        return self.__input_resolver

    @property
    def thesis_extractor(self) -> ThesisExtractor:
        return self.__thesis_extractor

    @property
    def polarity_finder(self) -> PolarityFinder:
        return self.__polarity_finder

    @property
    def reasoner(self) -> PolarReasoner:
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
        source = await self._get_input_source()
        text = await self._get_text()

        if theses is None:
            # No theses provided, generate one automatically
            # Extractor returns graph node directly (already connected to source)
            t = await self.thesis_extractor.extract_single_thesis(source=source)
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
                        # Create graph node from string and connect to source
                        provided_thesis = DialecticalComponent(statement=thesis)
                        provided_thesis.save()
                        source.statements.connect(provided_thesis)
                    else:  # thesis is already DialecticalComponent (graph node)
                        provided_thesis = thesis
                    final_theses.append(provided_thesis)

            known_theses = [t.statement for t in final_theses if t is not None]

            # Generate all missing theses at once if needed
            if none_positions:
                if len(none_positions) == 1:
                    # Single thesis case: place at the correct original position
                    pos = none_positions[0]
                    generated_thesis = await self.thesis_extractor.extract_single_thesis(
                        source=source, not_like_these=known_theses
                    )
                    final_theses[pos] = generated_thesis
                else:
                    # Multiple theses case - extract all missing ones at once
                    generated_theses = await self.thesis_extractor.extract_multiple_theses(
                        source=source,
                        count=len(none_positions),
                        not_like_these=known_theses
                    )

                    # Place generated theses in their correct positions
                    for i, pos in enumerate(none_positions):
                        if i < len(generated_theses):
                            final_theses[pos] = generated_theses[i]

                    # Backfill any remaining None (precaution)
                    for pos in none_positions:
                        if final_theses[pos] is None:
                            generated_thesis = await self.thesis_extractor.extract_single_thesis(
                                source=source, not_like_these=known_theses
                            )
                            final_theses[pos] = generated_thesis

            theses = final_theses

        cycles: list[Cycle] = await self.__sequencer.arrange(theses, text=text)
        return cycles

    async def build_wheel_permutations(
        self, *, theses: Union[list[str | DialecticalComponent | None], list[tuple[str | DialecticalComponent | None, str | DialecticalComponent | None]]] = None, t_cycle: Cycle = None
    ) -> list[Wheel]:
        """
        IMPORTANT: t_cycle is the "path" we take for permutations. If not provided, we'll take the most likely path.
        Do not confuse it with building all wheels for all "paths"

        The tuple in the thesis list is used to provide antithesis for the thesis, where the first element is the thesis, the second is the antithesis.
        """
        source = await self._get_input_source()
        text = await self._get_text()

        if t_cycle is None:
            cycles: list[Cycle] = await self.t_cycles(theses=[t[0] if isinstance(t, tuple) else t for t in theses])
            # The first one is the highest probability
            t_cycle = cycles[0]

        # Create Nexus BEFORE building WUs so they can query sibling context
        nexus = Nexus()
        nexus.save()

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

            # Pass nexus for sibling context - WU will be connected to it
            wu = await self.reasoner.think(source=source, text=text, thesis=dc, antithesis=antithesis, nexus=nexus)
            wheel_wisdom_units.append(wu)

        cycles: list[Cycle] = await self.__sequencer.arrange(wheel_wisdom_units, text=text)

        # Set human-friendly indices on wisdom units if multiple WUs
        if len(wheel_wisdom_units) > 1:
            for idx, wu in enumerate(wheel_wisdom_units, start=1):
                wu.set_human_friendly_index(idx)

        # Connect cycles to Nexus (parent→child: Nexus has cycles)
        # T-cycle and TA-cycles all belong to the same Nexus
        nexus.cycles.connect(t_cycle)
        for cycle in cycles:
            if cycle.uid != t_cycle.uid:  # Don't double-connect t_cycle
                nexus.cycles.connect(cycle)

        # Create wheels for each TA-cycle permutation
        # Each wheel is a detailed implementation of a cycle arrangement
        wheels = []
        for cycle in cycles:
            # Create wheel node
            w = Wheel()
            w.save()

            # Create wheel-level transitions FIRST (ta_cycle level detail)
            # These are separate from cycle-level transitions
            # Wheel transitions follow the same component sequence
            # MUST be done before connecting to cycle (validation requires transitions)
            for trans in cycle.transitions:
                source_result = trans.source.get()
                target_result = trans.target.get()
                if source_result and target_result:
                    source_comp, _ = source_result
                    target_comp, _ = target_result

                    # Create new transition for wheel (separate object, same components)
                    wheel_trans = Transition()
                    wheel_trans.save()
                    wheel_trans.source.connect(source_comp)
                    wheel_trans.target.connect(target_comp)
                    wheel_trans.cycle.connect(w)  # Connect to wheel (CircularTopologyMixin)

            # Connect wheel to cycle (creates Cycle → HAS_WHEEL → Wheel)
            # This establishes: Wheel.cycle.get() returns this cycle
            # And: Cycle.wheels.all() includes this wheel
            # MUST be done after transitions exist (validation checks transitions)
            cycle.wheels.connect(w)

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
            wus = wheel.wisdom_units
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
            wisdom_units = wheel.wisdom_units
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
            text = await self._get_text()
            synthesis_deck_dto = await self.reasoner.find_synthesis(wu, text=text)

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

            # Connect Synthesis to Transformation (synthesis emerges from transformation)
            trans_result = wu.transformation.get()
            if trans_result:
                transformation = trans_result[0]
                synthesis.target.connect(transformation)
            else:
                logger.warning(f"WU {wu.uid} has no transformation - skipping synthesis connection")

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
            position = alias_to_position.get(base_alias, base_alias.lower())
            return (wu_index, position)

        text = await self._get_text()

        # Group modifications by WU index
        wu_modifications: Dict[int, Dict[str, str]] = {}
        for alias, statement in modified_statement_per_alias.items():
            wu_index, position = parse_alias(alias)
            if wu_index not in wu_modifications:
                wu_modifications[wu_index] = {}
            wu_modifications[wu_index][position] = statement

        new_wheels = []
        for wheel in self.__wheels:
            # Check if any WU in this wheel needs modification
            wus = wheel.wisdom_units
            wheel_is_dirty = False

            new_wus = []
            for wu in wus:
                wu_idx = wu.get_human_friendly_index()

                if wu_idx in wu_modifications:
                    mods = wu_modifications[wu_idx]

                    # Check if modifications actually change anything
                    has_changes = False
                    for pos, new_statement in mods.items():
                        current = wu.get_component(pos.upper().replace("_PLUS", "+").replace("_MINUS", "-"))
                        if current is None or current.statement != new_statement:
                            has_changes = True
                            break

                    if has_changes:
                        wheel_is_dirty = True
                        # Redefine WU
                        new_wu = await self.reasoner.redefine(original=wu, text=text, **mods)
                        new_wus.append(new_wu)
                    else:
                        # No actual changes - use original
                        new_wus.append(wu)
                else:
                    # No modifications for this WU - use original
                    new_wus.append(wu)

            if wheel_is_dirty:
                # Need to rebuild wheel with modified WUs
                # Recalculate cycles
                cycles: list[Cycle] = await self.__sequencer.arrange(new_wus, text=text)

                # Create new wheels
                for cycle in cycles:
                    w = Wheel()
                    w.save()

                    # Create wheel-level transitions
                    for trans in cycle.transitions:
                        source_result = trans.source.get()
                        target_result = trans.target.get()
                        if source_result and target_result:
                            source_comp, _ = source_result
                            target_comp, _ = target_result

                            wheel_trans = Transition()
                            wheel_trans.save()
                            wheel_trans.source.connect(source_comp)
                            wheel_trans.target.connect(target_comp)
                            wheel_trans.cycle.connect(w)

                    cycle.wheels.connect(w)
                    new_wheels.append(w)

                    # Score the wheel
                    self.scorer.calculate_score(w)
            else:
                # No changes - preserve original wheel
                new_wheels.append(wheel)

        self.__wheels = new_wheels
        return self.__wheels
