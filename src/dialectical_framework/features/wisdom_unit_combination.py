"""
WisdomUnitCombination: Feature for combining WisdomUnits into Cycles and Wheels.

Purely structural — creates the graph topology, no estimation.

Takes a Nexus and WisdomUnits, adds WUs to the Nexus (idempotent),
then creates all layer-by-layer combinations:
- Layer 1: Single WU Cycles/Wheels
- Layer 2: Pairs of WUs → multiple T-cycle orderings → multiple TA-wheel arrangements
- Layer 3: Triplets → more orderings → more wheel arrangements
- etc.

Existing Cycles and Wheels are reused (no duplicates).

Usage:
    from dialectical_framework.features.wisdom_unit_combination import WisdomUnitCombination

    feature = WisdomUnitCombination()
    result = feature.execute(
        nexus=nexus,
        wisdom_units=[wu1, wu2, wu3],
    )

    for cycle in result.cycles:
        print(f"Cycle: {cycle.short_hash}")
    for wheel in result.wheels:
        print(f"Wheel: {wheel.short_hash}")
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Optional, TYPE_CHECKING

from dialectical_framework.agents.executable_capability import ExecutableCapability
from dialectical_framework.agents.execution_report import ExecutionReport
from dialectical_framework.graph.nodes.cycle import Cycle
from dialectical_framework.graph.nodes.nexus import Nexus
from dialectical_framework.graph.nodes.transition import Transition
from dialectical_framework.graph.nodes.wheel import Wheel
from dialectical_framework.graph.repositories.wheel_repository import WheelRepository
from dialectical_framework.utils.sequence_generation import (
    generate_compatible_sequences,
    generate_permutation_sequences,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


@dataclass
class LayerResult:
    """Result for a single layer of combination."""

    layer: int
    cycles: list[Cycle]
    wheels: list[Wheel]
    new_cycles: list[Cycle]
    new_wheels: list[Wheel]


@dataclass
class CombinationResult:
    """Result from WisdomUnitCombination. Contains only newly created structures."""

    nexus: Nexus
    cycles: list[Cycle]
    wheels: list[Wheel]
    cycles_by_layer: dict[int, list[Cycle]]
    wheels_by_layer: dict[int, list[Wheel]]


class WisdomUnitCombination(ExecutableCapability[CombinationResult]):
    """
    Feature for combining WisdomUnits into Cycles and Wheels.

    Purely structural — creates graph topology, no estimation.

    - Adds WisdomUnits to Nexus (idempotent, no duplicates)
    - Generates T-cycle permutations for each WU combination
    - Creates Cycle nodes (connected to Nexus)
    - Generates Wheel arrangements for each Cycle
    - Reuses existing Cycles and Wheels where possible

    Idempotent: calling multiple times with same inputs produces no duplicates.
    """

    def __init__(self) -> None:
        self._report: ExecutionReport

    @property
    def report(self) -> ExecutionReport:
        """Access the execution report."""
        return self._report

    def execute(
        self,
        nexus: Nexus,
        wisdom_units: list[WisdomUnit],
        preset: Optional[str] = None,
    ) -> CombinationResult:
        """
        Combine WisdomUnits into Cycles and Wheels.

        Adds WUs to the Nexus (skipping duplicates), then builds all
        layer-by-layer structural combinations.

        Args:
            nexus: Required exploration context (must be committed)
            wisdom_units: WUs to combine (must be committed)
            preset: Concrete preset for Cycle intent. If None, reads from nexus.preset.
                Must not be "preset:auto" — caller resolves that first.

        Returns:
            CombinationResult with newly created Cycles and Wheels
        """
        self._preset = preset or nexus.preset
        self._report = ExecutionReport(tool=self.__class__.__name__)

        if not nexus.is_committed:
            self._report.ok = False
            self._report.summary = "Nexus must be committed before combination"
            return CombinationResult(
                nexus=nexus, cycles=[], wheels=[],
                cycles_by_layer={}, wheels_by_layer={},
            )

        if not wisdom_units:
            self._report.ok = False
            self._report.summary = "No WisdomUnits provided"
            return CombinationResult(
                nexus=nexus, cycles=[], wheels=[],
                cycles_by_layer={}, wheels_by_layer={},
            )

        # Validate all WUs are committed
        for wu in wisdom_units:
            if not wu.is_committed:
                self._report.ok = False
                self._report.summary = "WisdomUnit must be committed before combination"
                return CombinationResult(
                    nexus=nexus, cycles=[], wheels=[],
                    cycles_by_layer={}, wheels_by_layer={},
                )

        # Add WUs to Nexus (idempotent — skip already connected)
        self._add_wisdom_units_to_nexus(nexus, wisdom_units)

        self._report.artifacts["nexus_hash"] = nexus.short_hash
        self._report.artifacts["wu_count"] = len(wisdom_units)

        # Build from all WUs in Nexus (not just the ones passed in)
        all_nexus_wus = [wu for wu, _ in nexus.wisdom_units.all()]
        total_wus = len(all_nexus_wus)

        # Build combinations layer by layer, collect only new structures
        new_cycles: list[Cycle] = []
        new_wheels: list[Wheel] = []
        cycles_by_layer: dict[int, list[Cycle]] = {}
        wheels_by_layer: dict[int, list[Wheel]] = {}

        for layer in range(1, total_wus + 1):
            layer_result = self._build_layer(nexus, all_nexus_wus, layer)

            if layer_result.new_cycles:
                cycles_by_layer[layer] = layer_result.new_cycles
            if layer_result.new_wheels:
                wheels_by_layer[layer] = layer_result.new_wheels
            new_cycles.extend(layer_result.new_cycles)
            new_wheels.extend(layer_result.new_wheels)

        self._report.artifacts["new_cycles"] = len(new_cycles)
        self._report.artifacts["new_wheels"] = len(new_wheels)
        self._report.artifacts["layers_built"] = total_wus

        self._report.summary = (
            f"Combined {total_wus} WUs: created {len(new_cycles)} new cycles "
            f"and {len(new_wheels)} new wheels"
        )

        return CombinationResult(
            nexus=nexus,
            cycles=new_cycles,
            wheels=new_wheels,
            cycles_by_layer=cycles_by_layer,
            wheels_by_layer=wheels_by_layer,
        )

    def _add_wisdom_units_to_nexus(
        self,
        nexus: Nexus,
        wisdom_units: list[WisdomUnit],
    ) -> None:
        """
        Add WisdomUnits to Nexus, skipping any already connected.
        """
        existing_hashes = {wu.hash for wu, _ in nexus.wisdom_units.all()}

        for wu in wisdom_units:
            if wu.hash not in existing_hashes:
                wu.nexus.connect(nexus)
                existing_hashes.add(wu.hash)

    def _build_layer(
        self,
        nexus: Nexus,
        wisdom_units: list[WisdomUnit],
        layer: int,
    ) -> LayerResult:
        """
        Build all Cycles and Wheels for a specific layer.

        For each WU combination of size `layer`:
        1. Generate T-cycle permutations
        2. Create missing Cycle nodes (connected to Nexus)
        3. For each Cycle, generate Wheel arrangements
        4. Create missing Wheel nodes
        """
        all_cycles: list[Cycle] = []
        all_wheels: list[Wheel] = []
        new_cycles: list[Cycle] = []
        new_wheels: list[Wheel] = []

        # Generate all combinations of WUs for this layer size
        wu_combinations = list(combinations(wisdom_units, layer))

        for wu_combo in wu_combinations:
            # Generate T-cycle permutations for this combination
            cycles_for_combo, new_for_combo = self._build_cycles_for_wus(
                nexus, list(wu_combo)
            )
            all_cycles.extend(cycles_for_combo)
            new_cycles.extend(new_for_combo)

            # For each Cycle, generate Wheels
            for cycle in cycles_for_combo:
                wheels_for_cycle, new_wheels_for_cycle = self._build_wheels_for_cycle(
                    cycle
                )
                all_wheels.extend(wheels_for_cycle)
                new_wheels.extend(new_wheels_for_cycle)

        # Connect opposite-direction pairs (queries DB for full layer scope)
        self._connect_opposite_direction_pairs(
            nexus, [list(combo) for combo in wu_combinations]
        )

        return LayerResult(
            layer=layer,
            cycles=all_cycles,
            wheels=all_wheels,
            new_cycles=new_cycles,
            new_wheels=new_wheels,
        )

    def _build_cycles_for_wus(
        self,
        nexus: Nexus,
        wisdom_units: list[WisdomUnit],
    ) -> tuple[list[Cycle], list[Cycle]]:
        """
        Generate T-cycle permutations for a WU combination.

        Uses generate_permutation_sequences to produce all (N-1)! unique
        T-cycle orderings (first element fixed to eliminate rotational duplicates).

        Returns:
            Tuple of (all_cycles, new_cycles)
        """
        all_cycles: list[Cycle] = []
        new_cycles: list[Cycle] = []

        # For single WU, only one trivial T-cycle
        if len(wisdom_units) == 1:
            cycle, is_new = self._find_or_create_cycle(wisdom_units)
            all_cycles.append(cycle)
            if is_new:
                new_cycles.append(cycle)
            return all_cycles, new_cycles

        # Extract T components and build component→WU lookup
        t_components: list[DialecticalComponent] = []
        comp_hash_to_wu: dict[str, WisdomUnit] = {}
        for wu in wisdom_units:
            t_result = wu.t.get()
            if not t_result:
                continue
            t_comp = t_result[0]
            t_components.append(t_comp)
            comp_hash_to_wu[t_comp.hash] = wu

        if not t_components:
            return all_cycles, new_cycles

        # Generate all (N-1)! permutation sequences
        sequences = generate_permutation_sequences(t_components)

        for sequence in sequences:
            # Map component sequence back to WU ordering
            ordered_wus = [comp_hash_to_wu[comp.hash] for comp in sequence]

            cycle, is_new = self._find_or_create_cycle(ordered_wus)
            all_cycles.append(cycle)
            if is_new:
                new_cycles.append(cycle)

        return all_cycles, new_cycles

    def _find_or_create_cycle(
        self,
        wisdom_units: list[WisdomUnit],
    ) -> tuple[Cycle, bool]:
        """
        Find existing Cycle or create new one.

        Checks if a Cycle with the same WU ordering and intent already exists.
        Layer-1 Cycles (single WU) have no intent — causality requires 2+ WUs.

        Returns:
            Tuple of (Cycle, is_new)
        """
        from dialectical_framework.graph.repositories.cycle_repository import CycleRepository

        # Layer-1 (single WU) Cycles have no intent
        intent = self._preset if len(wisdom_units) >= 2 else None

        cycle_repo = CycleRepository()
        existing_cycles = cycle_repo.find_by_wisdom_units(wisdom_units, exact_order=True)

        for cycle in existing_cycles:
            if cycle.intent == intent:
                return cycle, False

        # Create new Cycle
        cycle = Cycle(intent=intent)
        cycle.set_wisdom_units(wisdom_units)
        cycle.commit()

        return cycle, True

    def _build_wheels_for_cycle(
        self,
        cycle: Cycle,
    ) -> tuple[list[Wheel], list[Wheel]]:
        """
        Generate Wheel arrangements for a Cycle.

        Uses generate_compatible_sequences to produce all valid TA-wheel
        arrangements with diagonal symmetry (T and A neutral components).

        Returns:
            Tuple of (all_wheels, new_wheels)
        """
        all_wheels: list[Wheel] = []
        new_wheels: list[Wheel] = []

        wisdom_units = cycle.wisdom_units
        if not wisdom_units:
            return all_wheels, new_wheels

        # Generate all compatible TA arrangements
        arrangements = generate_compatible_sequences(wisdom_units)

        if not arrangements:
            return all_wheels, new_wheels

        wheel_repo = WheelRepository()

        for components in arrangements:
            # Check for existing wheel with same component sequence
            existing_wheel = wheel_repo.find_by_component_sequence(components)
            if existing_wheel:
                # Reuse existing wheel — connect to this cycle if not already
                cycle_result = existing_wheel.cycle.get()
                if not cycle_result or cycle_result[0].hash != cycle.hash:
                    cycle.wheels.connect(existing_wheel)
                all_wheels.append(existing_wheel)
                continue

            # Create new wheel
            wheel = Wheel(intent=cycle.intent)
            wheel.save()

            # Create transitions forming the circular causality sequence
            for i in range(len(components)):
                source_comp = components[i]
                target_comp = components[(i + 1) % len(components)]

                transition = Transition()
                transition.set_source(source_comp)
                transition.set_target(target_comp)
                transition.commit()
                transition.cycle.connect(wheel)

            # Connect to cycle
            cycle.wheels.connect(wheel)

            wheel.commit()

            all_wheels.append(wheel)
            new_wheels.append(wheel)

        return all_wheels, new_wheels

    def _connect_opposite_direction_pairs(
        self,
        nexus: Nexus,
        wu_combo_list: list[list[WisdomUnit]],
    ) -> None:
        """
        Detect and connect opposite-direction pairs among cycles and wheels.

        Queries the DB for ALL cycles/wheels in each WU combo's layer scope,
        so pairs are connected even if one side was created in a previous run.

        Two sequences are opposite-direction if one is a circular reverse of the other.
        Connects pairs via the OPPOSITE_DIRECTION symmetric relationship.
        """
        from dialectical_framework.graph.repositories.cycle_repository import CycleRepository

        cycle_repo = CycleRepository()
        wheel_repo = WheelRepository()

        for wu_combo in wu_combo_list:
            if len(wu_combo) <= 1:
                continue  # Single WU has no opposite direction

            # Get ALL cycles and wheels for this WU set from DB
            all_layer_cycles = cycle_repo.find_by_layer(wu_combo, nexus=nexus)
            all_layer_wheels = wheel_repo.find_by_layer(wu_combo, nexus=nexus)

            # Cycles: reversal needs 3+ WUs (2-element circular sequences
            # have no distinct reverse). Wheels always have 2n components,
            # so 2 WUs → 4-component sequences which can have reversals.
            if len(wu_combo) >= 3:
                _connect_opposite_direction_cycles(all_layer_cycles)
            _connect_opposite_direction_wheels(all_layer_wheels)


def _connect_opposite_direction_cycles(cycles: list[Cycle]) -> None:
    """Connect cycles that are circular reverses of each other."""
    connected: set[tuple[str, str]] = set()

    for i, cycle_a in enumerate(cycles):
        seq_a = cycle_a.wisdom_unit_hashes
        for cycle_b in cycles[i + 1:]:
            seq_b = cycle_b.wisdom_unit_hashes
            if _is_circular_reverse(seq_a, seq_b):
                pair_id = tuple(sorted([cycle_a.hash, cycle_b.hash]))
                if pair_id not in connected:
                    cycle_a.opposite_direction.connect(cycle_b)
                    connected.add(pair_id)


def _connect_opposite_direction_wheels(wheels: list[Wheel]) -> None:
    """Connect wheels that are circular reverses of each other."""
    connected: set[tuple[str, str]] = set()

    # Pre-compute component hash sequences
    wheel_sequences: list[tuple[Wheel, list[str]]] = []
    for wheel in wheels:
        comp_hashes = [c.hash for c in wheel.dialectical_components]
        wheel_sequences.append((wheel, comp_hashes))

    for i, (wheel_a, seq_a) in enumerate(wheel_sequences):
        for wheel_b, seq_b in wheel_sequences[i + 1:]:
            if _is_circular_reverse(seq_a, seq_b):
                pair_id = tuple(sorted([wheel_a.hash, wheel_b.hash]))
                if pair_id not in connected:
                    wheel_a.opposite_direction.connect(wheel_b)
                    connected.add(pair_id)


def _is_circular_reverse(seq_a: list[str], seq_b: list[str]) -> bool:
    """
    Check if seq_b is any rotation of the reverse of seq_a.

    Returns False for sequences of length <= 2 (no distinct reversal).
    """
    if len(seq_a) != len(seq_b) or set(seq_a) != set(seq_b):
        return False
    if len(seq_a) <= 2:
        return False
    reversed_a = list(reversed(seq_a))
    return any(
        reversed_a[i:] + reversed_a[:i] == seq_b
        for i in range(len(reversed_a))
    )
