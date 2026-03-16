from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Union

from dependency_injector.wiring import Provide, inject

logger = logging.getLogger(__name__)

from dialectical_framework.ai_dto.dialectical_component_dto import DialecticalComponentDto
from dialectical_framework.ai_dto.graph_mapper import component_from_dto
from dialectical_framework.enums.di import DI
from dialectical_framework.protocols.causality_sequencer import CausalitySequencer
from dialectical_framework.protocols.has_config import SettingsAware
from dialectical_framework.protocols.input_resolver import InputResolver
from dialectical_framework.agents.brainstorming.capabilities.thesis_extraction import ThesisExtraction
from dialectical_framework.graph.repositories.node_repository import NodeRepository

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

    @inject
    def __init__(
        self,
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
                input_node.commit()
                self.__source.inputs.connect(input_node)
                self.__input_source = input_node
        elif self.__text is not None:
            # Create Input from text
            input_node = Input(content=self.__text)
            input_node.commit()
            self.__input_source = input_node
        else:
            # No source and no text - create empty Input
            input_node = Input(content="")
            input_node.commit()
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

    async def _extract_theses(
        self,
        *,
        count: int = 1,
        not_like_these: list[str] = None,
    ) -> list[DialecticalComponent]:
        """
        Extract theses using extraction capability and query back components.

        Args:
            count: Number of theses to extract
            not_like_these: Statements to avoid duplicating

        Returns:
            List of DialecticalComponent graph nodes (committed)
        """
        text = await self._get_text()
        source = await self._get_input_source()

        service = ThesisExtraction()
        components = await service.execute(
            text=text,
            count=count,
            not_like_these=not_like_these or [],
        )

        # Connect extracted theses to source
        for comp in components:
            source.statements.connect(comp)

        return components

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
            generated = await self._extract_theses(count=1)
            theses = generated
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
                        provided_thesis.commit()
                        source.statements.connect(provided_thesis)
                    else:  # thesis is already DialecticalComponent (graph node)
                        provided_thesis = thesis
                    final_theses.append(provided_thesis)

            known_theses = [t.statement for t in final_theses if t is not None]

            # Generate all missing theses at once if needed
            if none_positions:
                generated_theses = await self._extract_theses(
                    count=len(none_positions),
                    not_like_these=known_theses,
                )

                # Place generated theses in their correct positions
                for i, pos in enumerate(none_positions):
                    if i < len(generated_theses):
                        final_theses[pos] = generated_theses[i]

                # Backfill any remaining None (precaution)
                for pos in none_positions:
                    if final_theses[pos] is None:
                        backfill = await self._extract_theses(
                            count=1,
                            not_like_these=known_theses,
                        )
                        if backfill:
                            final_theses[pos] = backfill[0]

            theses = final_theses

        # Create Nexus for the cycles
        nexus = Nexus()
        nexus.save()

        # Create temporary WisdomUnits from theses (just T components)
        # This is needed because arrange() works from WisdomUnits
        source = await self._get_input_source()
        text = await self._get_text()
        for thesis in theses:
            await self.reasoner.think(source=source, text=text, thesis=thesis, nexus=nexus)
        nexus.commit()

        # Arrange creates cycles and wheels from the Nexus (uncommitted since Nexus is uncommitted)
        cycles: list[Cycle] = self.__sequencer.arrange(nexus, self.settings.cycle_intent)

        return cycles

    async def build_wheel_structures_only(
        self,
        *,
        theses: Union[list[str | DialecticalComponent | None], list[tuple[str | DialecticalComponent | None, str | DialecticalComponent | None]]] = None,
        t_cycle: Cycle = None,
    ) -> tuple[Nexus, list[Wheel]]:
        """
        Build Wheel structures without AI estimation (Phase 1).

        Creates Nexus, WisdomUnits, Cycles, and Wheel structures. All structures
        are committed and ready for estimation.

        This is Phase 1 of the two-phase workflow. Use `estimate_wheel_structures()`
        to attach AI-generated estimations in Phase 2.

        Args:
            theses: List of thesis inputs (strings, graph components, or None for auto-generation).
                   Can also be list of (thesis, antithesis) tuples.
            t_cycle: Optional pre-computed thesis Cycle. If None, will be generated.

        Returns:
            Tuple of (Nexus, list[Wheel]) - committed structures

        Example:
            # Phase 1: Build and commit structures
            nexus, wheels = await builder.build_wheel_structures_only(theses=["thesis1", "thesis2"])

            # Phase 2: Attach AI estimations (can be retried)
            await builder.estimate_wheel_structures(nexus, wheels)
        """
        source = await self._get_input_source()
        text = await self._get_text()

        # Create Nexus first (save, not commit - we need to add WUs first)
        nexus = Nexus()
        nexus.save()

        # Determine thesis components (either from provided t_cycle or generated)
        thesis_components: list[DialecticalComponent] = []
        if t_cycle is not None:
            # Use components from provided cycle
            thesis_components = t_cycle.dialectical_components
        else:
            # Extract thesis components from theses parameter
            thesis_inputs = [t[0] if isinstance(t, tuple) else t for t in theses]

            # First pass: collect provided theses and identify positions needing generation
            none_positions = []
            for i, thesis_input in enumerate(thesis_inputs):
                if thesis_input is None or (isinstance(thesis_input, str) and not thesis_input.strip()):
                    none_positions.append(i)
                    thesis_components.append(None)  # Placeholder
                elif isinstance(thesis_input, str):
                    comp = DialecticalComponent(statement=thesis_input)
                    comp.commit()
                    source.statements.connect(comp)
                    thesis_components.append(comp)
                else:
                    thesis_components.append(thesis_input)

            # Batch generate missing theses (more efficient + ensures distinctness)
            if none_positions:
                known = [c.statement for c in thesis_components if c is not None]
                generated_list = await self._extract_theses(
                    count=len(none_positions),
                    not_like_these=known,
                )
                for i, pos in enumerate(none_positions):
                    if i < len(generated_list):
                        thesis_components[pos] = generated_list[i]

        # Build WisdomUnits from thesis components (connects them to Nexus)
        # This MUST happen before connecting Cycles to Nexus (Nexus freezes after Cycle connection)
        wheel_wisdom_units = []
        for dc in thesis_components:
            antithesis = None
            if isinstance(theses, list):
                if len(theses) == 1 and isinstance(theses[0], tuple) and theses[0][0] is None:
                    antithesis = theses[0][1]
                else:
                    for t in theses:
                        if isinstance(t, tuple):
                            if isinstance(t[0], DialecticalComponent):
                                if dc.hash == t[0].hash:
                                    antithesis = t[1]
                                    break
                            elif isinstance(t[0], str) and dc.statement == t[0]:
                                antithesis = t[1]
                                break

            wu = await self.reasoner.think(source=source, text=text, thesis=dc, antithesis=antithesis, nexus=nexus)
            wheel_wisdom_units.append(wu)

        if len(wheel_wisdom_units) > 1:
            for idx, wu in enumerate(wheel_wisdom_units, start=1):
                wu.set_human_friendly_index(idx)

        # Arrange creates cycles and wheels from the Nexus (uncommitted since Nexus is uncommitted)
        if t_cycle is None:
            cycles: list[Cycle] = self.__sequencer.arrange(nexus, self.settings.cycle_intent)
            # Commit: Nexus first, then Cycles, then Wheels
            nexus.commit()
            for cycle in cycles:
                cycle.commit()
                for wheel, _ in cycle.wheels.all():
                    wheel.commit()
            t_cycle = cycles[0]
        else:
            # If t_cycle is provided, connect and commit Nexus, then add wheels
            nexus.cycles.connect(t_cycle)
            nexus.commit()
            # Build wheels for the provided cycle
            wu_sequences = self.__sequencer._get_sequences(wheel_wisdom_units)
            wheels_list = self.__sequencer._build_structures(wu_sequences, node_type=Wheel)
            for wheel in wheels_list:
                t_cycle.wheels.connect(wheel)
                wheel.commit()

        # Get wheels from the first cycle
        wheels = [w for w, _ in t_cycle.wheels.all()]

        # Store t_cycle reference for later
        for wheel in wheels:
            wheel._t_cycle = t_cycle

        return nexus, wheels

    async def estimate_wheel_structures(
        self,
        nexus: Nexus,
        wheels: list[Wheel],
        *,
        t_cycle: Cycle = None,
    ) -> list[Wheel]:
        """
        Attach AI estimations to existing skeleton wheel structures (Phase 2).

        This is Phase 2 of the two-phase workflow. Wheels must have been created
        via `build_wheel_structures_only()` first.

        Estimates both cycles and wheels (idempotent - skips if already estimated).

        Args:
            nexus: Nexus containing the WisdomUnits
            wheels: List of skeleton Wheel nodes created via build_wheel_structures_only()
            t_cycle: Optional thesis Cycle (retrieved from wheels if not provided)

        Returns:
            The same wheels list, now with AI estimations attached

        Note:
            - Modifies wheels in-place (updates _pending_rationale)
            - Does NOT commit wheels - caller must commit after estimation
            - Can be called multiple times to retry estimation
        """
        if not wheels:
            return wheels

        # Get all cycles from nexus and estimate them (idempotent)
        all_cycles = [c for c, _ in nexus.cycles.all()]
        if all_cycles:
            await self.__sequencer.estimate(all_cycles)

        # Attach AI estimations to wheels (idempotent)
        await self.__sequencer.estimate(wheels)

        return wheels

    async def build_wheel_permutations(
        self,
        *,
        theses: Union[list[str | DialecticalComponent | None], list[tuple[str | DialecticalComponent | None, str | DialecticalComponent | None]]] = None,
        t_cycle: Cycle = None,
    ) -> list[Wheel]:
        """
        Build wheel permutations with AI estimation (backwards-compatible convenience method).

        This method combines the two-phase workflow into a single call:
        1. Builds and commits structures via build_wheel_structures_only()
        2. Attaches AI estimations via estimate_wheel_structures()
        3. Scores the wheels

        IMPORTANT: t_cycle is the "path" we take for permutations. If not provided,
        we'll take the most likely path. Do not confuse it with building all wheels
        for all "paths".

        For more control, use the two-phase methods directly:
        - build_wheel_structures_only() for Phase 1 (structure creation + commit)
        - estimate_wheel_structures() for Phase 2 (AI estimation)

        Args:
            theses: List of thesis inputs (strings, graph components, or None for auto-generation).
                   Can also be list of (thesis, antithesis) tuples.
            t_cycle: Optional pre-computed thesis Cycle. If None, will be generated.

        Returns:
            List of Wheel objects with AI-estimated probabilities, committed and scored.
        """
        # Phase 1: Build and commit structures
        nexus, wheels = await self.build_wheel_structures_only(theses=theses, t_cycle=t_cycle)

        # Get t_cycle reference
        if t_cycle is None and wheels:
            t_cycle = getattr(wheels[0], '_t_cycle', None)
            if t_cycle is None:
                cycle_result = wheels[0].cycle.get() if wheels else None
                t_cycle = cycle_result[0] if cycle_result else None

        # Phase 2: Attach AI estimations (only if multiple wheels need comparison)
        if len(wheels) > 1 or (wheels and len(wheels[0].transitions) > 2):
            await self.estimate_wheel_structures(nexus, wheels)
        else:
            # For trivial cases (1 wheel, ≤2 transitions), set default P=1.0, R=1.0
            # This is the only possible arrangement, so probability is 1.0
            from dialectical_framework.graph.estimation_manager import EstimationManager
            from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
            estimation_manager = EstimationManager()
            for wheel in wheels:
                # Set wheel-level estimations
                estimation_manager.upsert_estimation(wheel, ProbabilityEstimation, 1.0)
                estimation_manager.upsert_estimation(wheel, RelevanceEstimation, 1.0)
                # Set transition-level estimations (TaroRank calculates from children)
                for trans in wheel.transitions:
                    estimation_manager.upsert_estimation(trans, ProbabilityEstimation, 1.0)
                    estimation_manager.upsert_estimation(trans, RelevanceEstimation, 1.0)
            # Also set Cycle estimations
            if t_cycle:
                estimation_manager.upsert_estimation(t_cycle, ProbabilityEstimation, 1.0)
                estimation_manager.upsert_estimation(t_cycle, RelevanceEstimation, 1.0)
                for trans in t_cycle.transitions:
                    estimation_manager.upsert_estimation(trans, ProbabilityEstimation, 1.0)
                    estimation_manager.upsert_estimation(trans, RelevanceEstimation, 1.0)

        # Score all wheels
        for wheel in wheels:
            self.scorer.calculate_score(wheel)

        # Clean up temporary attributes
        for wheel in wheels:
            if hasattr(wheel, '_t_cycle'):
                delattr(wheel, '_t_cycle')

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
                    logger.warning(f"Skipping synthesis for WU {wu.hash}: {e}")
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
                # Commit the synthesis now that all children are connected
                synthesis.commit()
            else:
                # Cannot commit Synthesis without a target - skip this WU
                logger.warning(f"WU {wu.hash} has no transformation - cannot create Synthesis")
                continue

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
                # Get the original t_cycle from the wheel (thesis-level arrangement)
                cycle_result = wheel.cycle.get()
                if not cycle_result:
                    raise ValueError(f"Wheel {wheel.hash} has no parent cycle")
                original_t_cycle, _ = cycle_result

                # Build new wheels from modified WUs
                wu_sequences = self.__sequencer._get_sequences(new_wus)
                redefined_wheels: list[Wheel] = self.__sequencer._build_structures(wu_sequences, node_type=Wheel)

                # Connect and commit wheels
                for w in redefined_wheels:
                    original_t_cycle.wheels.connect(w)
                    w.commit()

                # Estimate if multiple wheels
                if len(new_wus) > 1:
                    await self.__sequencer.estimate(redefined_wheels)

                for w in redefined_wheels:
                    new_wheels.append(w)
                    # Score the wheel
                    self.scorer.calculate_score(w)
            else:
                # No changes - preserve original wheel
                new_wheels.append(wheel)

        self.__wheels = new_wheels
        return self.__wheels
