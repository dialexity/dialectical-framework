"""
Wheel node for the dialectical framework.

This module provides the Wheel class which represents the top-level container
for a complete dialectical system. A Wheel is a concrete T-A arrangement
implementing a Cycle's abstract T-cycle via causality edges.
"""

from __future__ import annotations

from typing import ClassVar, Literal, Optional, Union, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipBoth, RelationshipManager
from dialectical_framework.graph.relationships.has_wheel_relationship import (
    HasWheelRelationship,
)
from dialectical_framework.graph.relationships.belongs_to_cycle_relationship import (
    BelongsToCycleRelationship,
)
from dialectical_framework.graph.relationships.opposite_direction_relationship import (
    OppositeDirectionRelationship,
)
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_T,
    POSITION_T_PLUS,
    POSITION_T_MINUS,
    POSITION_A,
    POSITION_A_PLUS,
    POSITION_A_MINUS,
)
from dialectical_framework.utils.order_transitions import order_transitions

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.transformation import Transformation

    # Type alias for flexible wheel segment references (no integer indexing in graph-native)
    WheelSegmentReference = Union[str, WheelSegment, DialecticalComponent]


class Wheel(IncrementalBuildMixin, IntentMixin, AssessableEntity, label="Wheel"):
    """
    Represents a concrete T-A arrangement implementing a Cycle's T-cycle.

    A Wheel = Cycle + Edges. The Cycle defines which WisdomUnits are
    included and their T-cycle order. The Edges define the concrete
    component-to-component causality flow (T1- → A2+ → A1- → T2+ → ...).

    The polarity (which side appears first - T or A) for each WU is derived
    from the edges, not stored separately.

    Hierarchy:
        WisdomUnit → Cycle (T-cycle + intent) → Wheel (edges)

    The wheel metaphor represents the circular, iterative nature of
    dialectical reasoning where thesis and antithesis are arranged in segments.

    Relationships:
    - Wheel belongs to exactly one Cycle
    - Wheel has edges (causality sequence / ta_cycle level)
    - Each edge can have Transformations (via ACTION_REFLECTION)

    Properties:
        polarity_count: Number of wisdom units (computed via cycle)
        segment_count: Total segments = polarity_count × 2 (computed)
        polar_segments: WUs with L/R orientation derived from edges (use this!)

    Example:
        cycle = Cycle(intent="preset:balanced")
        cycle.set_wisdom_units([wu1, wu2, wu3])
        cycle.commit()

        wheel = Wheel()
        wheel.save()
        cycle.wheels.connect(wheel)

        # Add edges that define the T-A arrangement
        edge1 = Transition()
        edge1.set_source(t1_minus)
        edge1.set_target(a2_plus)
        edge1.commit()
        edge1.cycle.connect(wheel)
        # ... more edges ...

        wheel.commit()
    """

    def __init__(self, **data):
        """Initialize wheel with polar pair cache."""
        super().__init__(**data)
        # Cache for polar pairs: wu_key:polarity -> WheelSegmentPolarPair
        self._polar_pair_cache: dict[str, WheelSegmentPolarPair] = {}

    # Parent Cycle (required)
    # Parent→child: Cycle has this Wheel
    cycle: ClassVar[RelationshipManager[Cycle]] = RelationshipFrom(
        "Cycle",
        model=HasWheelRelationship,
        cardinality=(1, 1)  # Exactly one parent cycle
    )

    # Edges that form this wheel's causality sequence (ta_cycle)
    _edges: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=BelongsToCycleRelationship,
        cardinality=(2, None)  # At least two edges to form a cycle
    )

    # Opposite-direction counterpart (symmetric)
    # Links wheels that are circular reverses of each other
    opposite_direction: ClassVar[RelationshipManager[Wheel]] = RelationshipBoth(
        "Wheel",
        model=OppositeDirectionRelationship,
    )

    @property
    def edges(self) -> list[Transition]:
        """
        Get causality edges in order by following source->target chain.

        Each edge is a Transition representing one step in the wheel's causality sequence.
        Transformations belong to individual edges.

        Returns:
            List of Transition nodes in order, or empty list if no edges
        """
        all_edges = [edge for edge, _ in self._edges.all()]
        return order_transitions(all_edges)

    @property
    def transformations(self) -> list[Transformation]:
        """
        Get all Transformations belonging to this wheel's edges.

        Queries transformations that point to any of this wheel's edges
        via ACTION_REFLECTION relationship, scoped by case_id.

        Returns:
            List of Transformation nodes from all edges
        """
        from dialectical_framework.graph.repositories.wheel_repository import WheelRepository
        repo = WheelRepository()
        return repo.get_transformations(self)

    @property
    def _wisdom_units(self) -> list[WisdomUnit]:
        """
        Get WisdomUnits derived from edges (unique WUs used in this wheel).

        For public API, use polar_segments which includes orientation.

        Returns:
            List of unique WisdomUnit nodes used in this wheel's edges
        """
        from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository

        seen_hashes: set[str] = set()
        result: list[WisdomUnit] = []
        wu_repo = WisdomUnitRepository()

        for edge in self.edges:
            source_result = edge.source.get()
            target_result = edge.target.get()

            components = []
            if source_result:
                components.append(source_result[0])
            if target_result:
                components.append(target_result[0])

            for component in components:
                # Find the WU this component belongs to
                wu_tuples = wu_repo.find_by_dialectical_component(component)
                for wu, _ in wu_tuples:
                    if wu.hash not in seen_hashes:
                        seen_hashes.add(wu.hash)
                        result.append(wu)

        return result

    def _get_commit_dependents(self):
        """
        Get edges for hash computation.

        Yields:
            Transition nodes (edges)
        """
        for edge in self.edges:
            yield edge

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Wheel.

        Parts: cycle hash, sorted edge hashes.
        The intent is added separately by BaseNode.compute_hash().

        Returns:
            List of strings: [cycle_hash, edge_hash1, edge_hash2, ...]

        Raises:
            ValueError: If Cycle is not connected/committed or edges not committed
        """
        parts = []

        # Get and verify parent Cycle
        cycle_result = self.cycle.get()
        if cycle_result:
            cycle_obj, _ = cycle_result
            if not cycle_obj.is_committed:
                raise ValueError(
                    "Cycle must be committed before computing Wheel structure hash. "
                    "Commit the parent Cycle first."
                )
            parts.append(cycle_obj.hash)
        else:
            raise ValueError(
                "Wheel must be connected to a Cycle before computing structure hash."
            )

        # Get edge hashes and sort for deterministic ordering
        # Edges encode the T-A arrangement (polarity is derived from them)
        edge_hashes = []
        for edge in self.edges:
            if not edge.is_committed:
                raise ValueError(
                    "Edge (Transition) must be committed before computing "
                    "Wheel structure hash"
                )
            edge_hashes.append(edge.hash)

        edge_hashes.sort()
        parts.extend(edge_hashes)

        return parts

    @property
    def polarity_count(self) -> int:
        """
        The number of polarities (wisdom units) in the wheel.

        Each wisdom unit represents one polarity - a thesis/antithesis pair.
        Computed via Wheel → Cycle → wisdom_units.

        Returns:
            Number of wisdom units in the wheel

        Raises:
            ValueError: If the wheel has no WisdomUnits
        """
        wus = self._wisdom_units
        if not wus:
            raise ValueError("The wheel has no WisdomUnits, therefore polarity_count is undefined.")
        return len(wus)

    @property
    def segment_count(self) -> int:
        """
        The total number of segments in the wheel.

        Each wisdom unit contains 2 segments (T-side and A-side), so
        segment_count = polarity_count × 2.

        Returns:
            Total number of segments (T and A sides)
        """
        return self.polarity_count * 2

    def polar_segment_at(
        self,
        key: Union[str, WisdomUnit, DialecticalComponent, WheelSegment]
    ) -> WheelSegmentPolarPair:
        """
        Get polar pair (WU with orientation) by various identifiers.

        Note: No integer indexing - use cycles to determine ordering.

        Args:
            key: Can be:
               - str: Tries in order:
                 1. WisdomUnit UID (e.g., "wu_12345")
                 2. Component UID (e.g., "comp_67890")
                 3. Component alias (e.g., "T1", "A2+")
               - WisdomUnit: match by uid
               - DialecticalComponent: find polar pair containing this component
               - WheelSegment: find polar pair containing this segment

        Returns:
            The matching WheelSegmentPolarPair (WU with orientation derived from transitions)

        Raises:
            ValueError: If no matching polar pair is found

        Examples:
            pair = wheel.polar_segment_at("wu_123")  # By WU UID
            pair = wheel.polar_segment_at("comp_456")  # By component UID
            pair = wheel.polar_segment_at("T1")  # By component alias
            pair = wheel.polar_segment_at(component)  # By component instance
            pair = wheel.polar_segment_at(segment)  # By segment instance
            pair = wheel.polar_segment_at(wisdom_unit)  # By WU instance
        """
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit as WUClass
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as DCClass
        from dialectical_framework.graph.wheel_segment import WheelSegment

        # Get polar pairs (WUs with orientation)
        pairs = self.polar_segments

        def find_pair_for_wu(target_wu: WisdomUnit) -> WheelSegmentPolarPair:
            """Find the polar pair containing the target WU."""
            target_key = target_wu._id if target_wu._id is not None else id(target_wu)
            for pair in pairs:
                pair_key = pair.wisdom_unit._id if pair.wisdom_unit._id is not None else id(pair.wisdom_unit)
                if pair_key == target_key:
                    return pair
                # Also check by hash
                if target_wu.hash and pair.wisdom_unit.hash == target_wu.hash:
                    return pair
            raise ValueError(f"WisdomUnit not found in polar pairs")

        if isinstance(key, WUClass):
            return find_pair_for_wu(key)

        elif isinstance(key, WheelSegment):
            # Match by segment
            for pair in pairs:
                wu = pair.wisdom_unit
                t_seg = wu.segment_t
                if t_seg.is_same(key):
                    return pair

                a_seg = wu.segment_a
                if a_seg.is_same(key):
                    return pair

            raise ValueError(f"Cannot find polar pair containing segment")

        elif isinstance(key, str):
            # Try string as three possibilities: WU identity, component identity, or component alias
            from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
            repo = DialecticalComponentRepository()

            # 1. Try as WisdomUnit identity (fast, direct lookup by hash or _id)
            for pair in pairs:
                wu = pair.wisdom_unit
                if wu.hash == key or str(wu._id) == key:
                    return pair

            # 2. Try as component identity
            for pair in pairs:
                wu = pair.wisdom_unit
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if comp.hash == key:
                        return pair

            # 3. Finally try as component alias
            for pair in pairs:
                wu = pair.wisdom_unit
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if alias == key:
                        return pair

            raise ValueError(f"Cannot find polar pair with key: {key} (tried as WU identity, component identity, and component alias)")

        elif isinstance(key, DCClass):
            # Search by component
            for pair in pairs:
                wu = pair.wisdom_unit
                try:
                    key.get_alias(wu)
                    return pair  # Found it
                except ValueError:
                    continue  # Not in this WU
            raise ValueError(f"Cannot find polar pair containing component: {key.hash}")

        raise ValueError(f"Cannot find polar pair with key: {key}")

    def segment_at(
        self,
        key: WheelSegmentReference
    ) -> WheelSegment:
        """
        Get wheel segment (T-side or A-side) by various identifiers.

        Note: No integer indexing - use cycles to determine ordering.

        Args:
            key: Can be:
               - str: Tries in order:
                 1. Component UID (e.g., "comp_12345")
                 2. Component alias (e.g., "T", "T+", "A1", "A2-")
               - DialecticalComponent: find segment containing this component
               - WheelSegment: validates it exists in wheel and returns it

        Returns:
            WheelSegment instance representing the T-side or A-side

        Raises:
            ValueError: If no matching segment is found

        Examples:
            seg = wheel.segment_at("comp_123")  # By component UID
            seg = wheel.segment_at("T1")  # By component alias
            seg = wheel.segment_at(component)  # By component instance
            seg = wheel.segment_at(existing_seg)  # Validates and returns
        """
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as DCClass
        from dialectical_framework.graph.wheel_segment import WheelSegment as WSClass

        # If key is a WheelSegment, validate it exists in this wheel and return it
        if isinstance(key, WSClass):
            wus = self._wisdom_units
            for wu in wus:
                if wu.segment_t.is_same(key) or wu.segment_a.is_same(key):
                    return key
            raise ValueError(f"WheelSegment not found in this wheel")

        # If key is a DialecticalComponent instance, use it directly
        elif isinstance(key, DCClass):
            wus = self._wisdom_units
            for wu in wus:
                # Check T-side segment
                t_seg = wu.segment_t
                if t_seg.is_set(key):
                    return t_seg

                # Check A-side segment
                a_seg = wu.segment_a
                if a_seg.is_set(key):
                    return a_seg

            raise ValueError(f"Cannot find wheel segment containing component: {key.hash}")

        # If key is a string, try as component identity first, then alias
        elif isinstance(key, str):
            from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
            repo = DialecticalComponentRepository()

            wus = self._wisdom_units

            # 1. Try as component identity
            for wu in wus:
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if comp.hash == key:
                        # Found component by identity, now find which segment it's in
                        t_seg = wu.segment_t
                        if t_seg.is_set(comp):
                            return t_seg
                        a_seg = wu.segment_a
                        if a_seg.is_set(comp):
                            return a_seg

            # 2. Try as component alias
            for wu in wus:
                # Check T-side segment
                t_seg = wu.segment_t
                if t_seg.is_set(key):
                    return t_seg

                # Check A-side segment
                a_seg = wu.segment_a
                if a_seg.is_set(key):
                    return a_seg

            raise ValueError(f"Cannot find wheel segment with key: {key} (tried as component UID and alias)")

        raise ValueError(f"Cannot find wheel segment with key: {key}")

    def is_set(self, key: Union[str, DialecticalComponent, WheelSegment]) -> bool:
        """
        Check if a component, alias, or segment exists in the wheel.

        Args:
            key: Can be:
               - str: component alias (e.g., "T", "T+", "A1")
               - DialecticalComponent: check if component exists in any WU
               - WheelSegment: check if segment exists in the wheel

        Returns:
            True if the key exists in the wheel, False otherwise

        Examples:
            if wheel.is_set("T1"):
                print("T1 exists")
            if wheel.is_set(component):
                print("Component exists")
            if wheel.is_set(segment):
                print("Segment exists")
        """
        try:
            self.polar_segment_at(key)
            return True
        except ValueError:
            return False

    @property
    def polar_segments(self) -> list[WheelSegmentPolarPair]:
        """
        Get all wisdom units as WheelSegmentPolarPair objects in edge order.

        Orientation (which side appears first - T or A) is derived from edges.
        The first component of each WU seen in the edge chain determines
        whether it's "normal" (T-side first) or "swapped" (A-side first).

        Polar pairs are cached per wisdom unit to ensure the same instances are reused.

        Returns:
            List of WheelSegmentPolarPair objects in edge order with derived orientation

        Raises:
            ValueError: If wheel has no WisdomUnits

        Example:
            pairs = wheel.polar_segments
            for pair in pairs:
                print(f"Left: {pair.segment_left.t.get()[0].statement}")
                print(f"Right: {pair.segment_right.t.get()[0].statement}")
        """
        wus = self._wisdom_units
        if not wus:
            raise ValueError("Wheel has no WisdomUnits")

        return self._derive_polar_segments_from_edges()

    def _derive_polar_segments_from_edges(self) -> list[WheelSegmentPolarPair]:
        """
        Derive polar pair orientations from edges.

        Traverses edges to determine which side of each WU appears first.
        The first component from each WU seen in the edge chain determines
        the polarity: T-side components → "normal", A-side components → "swapped".

        Returns:
            List of WheelSegmentPolarPair objects with derived orientation
        """
        from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair

        ordered_edges = self.edges
        if not ordered_edges:
            # Fall back to default "normal" orientation
            return [
                WheelSegmentPolarPair(wu, "normal")
                for wu in self._wisdom_units
            ]

        # Build a lookup map: component_hash -> (wisdom_unit, position)
        component_to_wu_map = {}
        for wu in self._wisdom_units:
            positions = [
                (POSITION_T, wu.t),
                (POSITION_T_PLUS, wu.t_plus),
                (POSITION_T_MINUS, wu.t_minus),
                (POSITION_A, wu.a),
                (POSITION_A_PLUS, wu.a_plus),
                (POSITION_A_MINUS, wu.a_minus),
            ]
            for position, manager in positions:
                for comp, _ in manager.all():
                    component_to_wu_map[comp.hash] = (wu, position)

        seen_wisdom_units = set()
        pairs = []

        for edge in ordered_edges:
            source_result = edge.source.get()
            if not source_result:
                continue

            source_component, _ = source_result
            wu_info = component_to_wu_map.get(source_component.hash)
            if wu_info is None:
                continue

            wu, position = wu_info
            wu_key = wu._id if wu._id is not None else id(wu)
            if wu_key in seen_wisdom_units:
                continue

            # Determine polarity based on which side appears first
            polarity: Literal["normal", "swapped"]
            if position in [POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS]:
                polarity = "normal"
            elif position in [POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS]:
                polarity = "swapped"
            else:
                continue

            cache_key = f"{wu_key}:{polarity}"
            if cache_key not in self._polar_pair_cache:
                self._polar_pair_cache[cache_key] = WheelSegmentPolarPair(wu, polarity)

            pairs.append(self._polar_pair_cache[cache_key])
            seen_wisdom_units.add(wu_key)

        return pairs

    @property
    def segments(self) -> list[WheelSegment]:
        """
        Get all wheel segments (T and A sides) in edge order.

        Returns segments in the exact order they appear in the wheel's edges,
        which is the correct order for creating edges (each segment's
        minus connects to the next segment's plus).

        Returns:
            List of WheelSegment objects in edge order

        Raises:
            ValueError: If wheel has no edges

        Example:
            # If edges follow T1 → A2 → A1 → T2:
            # Returns: [T1, A2, A1, T2] (exact edge order)

            for seg in wheel.segments:
                comp = seg.t.get()
                if comp:
                    print(f"{seg.side}: {comp[0].statement}")
        """
        ordered_edges = self.edges

        if not ordered_edges:
            raise ValueError("Wheel has no edges")

        # Extract segments by following the edges
        segments = []
        seen_segments = set()

        for edge in ordered_edges:
            # Get source component
            source_result = edge.source.get()
            if not source_result:
                continue

            source_component, _ = source_result

            # Find which segment this component belongs to
            for wu in self._wisdom_units:
                # Use _id for tracking since uncommitted nodes have hash=None
                wu_key = wu._id if wu._id is not None else id(wu)

                # Try to get segment containing this component
                t_seg = wu.segment_t
                if t_seg.is_set(source_component):
                    seg_key = (wu_key, t_seg.side)
                    if seg_key not in seen_segments:
                        segments.append(t_seg)
                        seen_segments.add(seg_key)
                    break

                a_seg = wu.segment_a
                if a_seg.is_set(source_component):
                    seg_key = (wu_key, a_seg.side)
                    if seg_key not in seen_segments:
                        segments.append(a_seg)
                        seen_segments.add(seg_key)
                    break

        return segments

    def get_next_segment(self, current: WheelSegment) -> WheelSegment:
        """
        Get the next segment in edge order.

        Args:
            current: The current segment

        Returns:
            The next segment in circular order

        Raises:
            ValueError: If current segment is not found in this wheel
        """
        segments = self.segments

        # Find current segment
        for i, seg in enumerate(segments):
            if seg.is_same(current):
                # Return next segment (wrap around if at end)
                next_index = (i + 1) % len(segments)
                return segments[next_index]

        raise ValueError(f"Segment not found in wheel's edge order")

    def is_same_structure(self, other: Wheel, compare: Literal['alias', 'statement'] = 'alias') -> bool:
        """
        Check if wheels represent the same structure regardless of starting point.

        Args:
            other: Another Wheel to compare with
            compare: What to compare - 'alias' (default) or 'statement'
                    - 'alias': Compare by component aliases
                    - 'statement': Compare by component statement text

        Returns:
            True if both have same components in same order (allowing rotation)

        Raises:
            ValueError: If compare='alias' but wisdom units not available
        """
        if not isinstance(other, Wheel):
            return False

        self_components = self.dialectical_components
        other_components = other.dialectical_components

        if len(self_components) != len(other_components):
            return False

        if compare == 'alias':
            self_wus = self._wisdom_units
            other_wus = other._wisdom_units

            if not self_wus or not other_wus:
                raise ValueError(
                    "Cannot compare by alias: wisdom units not available. "
                    "Use compare='statement' or ensure wheels have wisdom units."
                )

            self_aliases = []
            for comp in self_components:
                alias = None
                for wu in self_wus:
                    try:
                        alias = comp.get_alias(wu)
                        break
                    except ValueError:
                        continue
                if not alias:
                    raise ValueError(f"Component {comp.hash} has no alias in wheel")
                self_aliases.append(alias)

            other_aliases = []
            for comp in other_components:
                alias = None
                for wu in other_wus:
                    try:
                        alias = comp.get_alias(wu)
                        break
                    except ValueError:
                        continue
                if not alias:
                    raise ValueError(f"Component {comp.hash} has no alias in wheel")
                other_aliases.append(alias)

            if set(self_aliases) != set(other_aliases):
                return False

            if len(self_aliases) <= 1:
                return True

            return any(
                self_aliases == other_aliases[i:] + other_aliases[:i]
                for i in range(len(other_aliases))
            )

        elif compare == 'statement':
            self_statements = [comp.statement for comp in self_components]
            other_statements = [comp.statement for comp in other_components]

            if set(self_statements) != set(other_statements):
                return False

            if len(self_statements) <= 1:
                return True

            return any(
                self_statements == other_statements[i:] + other_statements[:i]
                for i in range(len(other_statements))
            )

        else:
            raise ValueError(f"Invalid compare parameter: {compare}. Must be 'alias' or 'statement'")

    def _format_edges(self, mode: str = "aliases") -> str:
        """
        Format edges as a chain string.

        Args:
            mode: "aliases" (default), "statements", or "explicit"

        Returns:
            Formatted string like "T1- → A2+ → A1- → T2+ → T1-..."
        """
        components = self.dialectical_components
        if not components:
            return ""

        wus = self._wisdom_units

        # Get aliases if needed
        aliases = []
        if mode in ("", "aliases", "explicit"):
            for i, comp in enumerate(components):
                alias = None
                for wu in wus:
                    try:
                        alias = comp.get_alias(wu)
                        break
                    except ValueError:
                        continue
                aliases.append(alias if alias else f"C{i+1}")
        else:
            aliases = [comp.statement for comp in components]

        # Build labels based on mode
        if mode in ("", "aliases"):
            labels = aliases
        elif mode == "statements":
            labels = [comp.statement for comp in components]
        elif mode == "explicit":
            labels = [
                f"{alias} ({comp.statement})"
                for alias, comp in zip(aliases, components)
            ]
        else:
            labels = aliases

        if len(labels) == 1:
            return f"{labels[0]} → {labels[0]}..."

        return " → ".join(labels) + f" → {labels[0]}..."

    @property
    def dialectical_components(self) -> list[DialecticalComponent]:
        """
        Get dialectical components from transitions in order.

        Returns:
            List of DialecticalComponent nodes from transitions
        """
        components = []
        transitions = self.edges

        if not transitions:
            return []

        for i, trans in enumerate(transitions):
            source_result = trans.source.get()
            target_result = trans.target.get()

            if not source_result or not target_result:
                continue

            source_comp, _ = source_result
            target_comp, _ = target_result

            components.append(source_comp)

            is_last = i == len(transitions) - 1
            if is_last:
                existing_ids = {comp._id for comp in components}
                if target_comp._id not in existing_ids:
                    components.append(target_comp)
            else:
                next_trans = transitions[i + 1]
                next_source_result = next_trans.source.get()

                if next_source_result:
                    next_source_comp, _ = next_source_result
                    if target_comp._id != next_source_comp._id:
                        components.append(target_comp)
                else:
                    components.append(target_comp)

        return components

    def __repr__(self) -> str:
        """String representation of the wheel."""
        try:
            wus = self._wisdom_units
            polarity_count = len(wus) if wus else 0
        except (ValueError, AttributeError):
            polarity_count = 0
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Wheel({hash_str}, polarity_count={polarity_count})"

    def __format__(self, format_spec: str) -> str:
        """
        Format this Wheel using Python's format string protocol.

        Format Specifications:
        ----------------------
        Modifiers can be combined with `:` separator.

        Modes:
        - (empty) - Default format showing cycles, wisdom units, and transformations
        - "compact" - Compact format with abbreviated components

        Modifiers:
        - "scores" - Shows S/R/P values for wheel, cycles, transformations
                     Calculated values shown in [brackets], manual without

        Shows:
        - Parent Cycle (t_cycle) with rationale
        - Wheel transitions (ta_cycle level)
        - Tabular view of all wisdom units using WheelSegmentPolarPair

        Examples:
        ---------
        f"{wheel}"              - Default format
        f"{wheel:compact}"      - Compact format
        f"{wheel:scores}"       - Default with S/R/P scores
        f"{wheel:compact:scores}" - Compact with S/R/P scores

        Returns:
            Multi-line formatted string
        """
        # Parse format spec - split by : to get modifiers
        modifiers = set(format_spec.split(":")) if format_spec else set()
        modifiers.discard("")  # Remove empty strings

        show_scores = "scores" in modifiers
        is_compact = "compact" in modifiers
        output = []

        # Import score formatting if needed
        if show_scores:
            from dialectical_framework.utils.score_format import (
                fmt_scores, fmt_score, fmt_relevance, fmt_probability
            )

        # Helper to format cycle with rationale (and optionally scores)
        def _format_cycle(cycle_obj, cycle_name: str) -> list[str]:
            lines = []
            header = f"=== {cycle_name} ==="
            if show_scores:
                header = f"=== {cycle_name} [{fmt_scores(cycle_obj, colorize=True)}] ==="
            lines.append(header)

            from dialectical_framework.graph.nodes.cycle import Cycle
            prefix = f"{cycle_obj.intent} : " if isinstance(cycle_obj, Cycle) and cycle_obj.intent else ""
            lines.append(f"{prefix}{cycle_obj:aliases}")

            # Add the best rationale if it exists
            rationale = cycle_obj.best_rationale
            if rationale and rationale.text:
                lines.append(f"Rationale: {rationale.text}")

            return lines

        # Wheel header with scores
        if show_scores:
            output.append(f"=== Wheel [{fmt_scores(self, colorize=True)}] ===")
            output.append("")

        # Parent Cycle (t_cycle level)
        cycle_result = self.cycle.get()
        if cycle_result:
            cycle_obj, _ = cycle_result
            output.extend(_format_cycle(cycle_obj, "Cycle (t_cycle)"))
            output.append("")

        # Wheel edges (ta_cycle level causality sequence)
        if len(self.edges) > 0:
            lines = []
            header = "=== Wheel Edges (ta_cycle) ==="
            if show_scores:
                header = f"=== Wheel Edges [{fmt_scores(self, colorize=True)}] ==="
            lines.append(header)
            # Format edges as alias chain
            lines.append(self._format_edges("aliases"))

            # Add the best rationale if it exists
            rationale = self.best_rationale
            if rationale and rationale.text:
                lines.append(f"Rationale: {rationale.text}")

            output.extend(lines)
            output.append("")

        # Wisdom Units (tabular with transformations)
        # Use polar_segments to get wisdom units in transition order with correct polarity
        output.append("=== Wisdom Units / Transformations ===")

        try:
            polar_segments = self.polar_segments
        except ValueError:
            # No transitions, fall back to unordered wisdom units
            from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
            polar_segments = [WheelSegmentPolarPair(wu, "normal") for wu in self._wisdom_units]

        if polar_segments:
            from tabulate import tabulate
            from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship

            positions = [
                ("t_minus", POSITION_T_MINUS),
                ("t", POSITION_T),
                ("t_plus", POSITION_T_PLUS),
                ("a_plus", POSITION_A_PLUS),
                ("a", POSITION_A),
                ("a_minus", POSITION_A_MINUS),
            ]

            # Build table: each row is a position, columns are (alias, statement) pairs for each WU
            table = []
            for position_attr, position_label in positions:
                row = []
                for pair in polar_segments:
                    wu = pair.wisdom_unit

                    # WisdomUnit columns
                    manager = getattr(wu, position_attr)
                    result = manager.get()
                    if result:
                        component, rel = result
                        assert isinstance(rel, PolarityRelationship)
                        row.append(rel.alias)
                        row.append(component.statement)
                    else:
                        row.append("")
                        row.append("")

                table.append(row)

            output.append(tabulate(table, tablefmt="plain"))

            # Show transformation scores if in scores mode
            # Transformations now belong to Transitions (causality steps), not WUs
            if show_scores and self.transformations:
                output.append("")
                output.append("Transformation Scores:")
                for idx, transformation in enumerate(self.transformations, 1):
                    output.append(f"  Step {idx}: [{fmt_scores(transformation, colorize=True)}]")
        else:
            output.append("[No wisdom units]")
        output.append("")

        # Transitions table with scores (only in scores mode)
        if show_scores:
            output.append("=== Transitions ===")
            from tabulate import tabulate

            transitions_data = []

            # Collect transitions from all sources
            cycles_to_check = [
                ("Cycle", cycle_result[0] if cycle_result else None),
                ("Wheel", self),  # Wheel itself has transitions (ta_cycle level)
            ]

            # Note: Transformation no longer has transitions - it has 6 component positions (Ac, Re, Ac+, Ac-, Re+, Re-)

            def format_rationale_tree(rationales: list, indent: int = 0) -> list[str]:
                """Format rationale hierarchy with provided P/R values and rating."""
                from dialectical_framework.graph.nodes.estimation import (
                    ProbabilityEstimation,
                    RelevanceEstimation,
                    FeasibilityEstimation
                )
                lines = []
                prefix = "  " * indent + "- " if indent > 0 else "- "
                for rat in rationales:
                    # Format rationale line with provided P/R values and rating
                    text_preview = rat.text[:40] + "..." if rat.text and len(rat.text) > 40 else (rat.text or "Unnamed rationale")

                    # Get P/R values from provided estimations
                    provided = list(rat.provided_estimations.all())
                    p_val = None
                    r_val = None
                    for est, _ in provided:
                        if isinstance(est, ProbabilityEstimation):
                            p_val = est.value
                        elif isinstance(est, (RelevanceEstimation, FeasibilityEstimation)):
                            r_val = est.value

                    # Format the values
                    parts = []
                    if r_val is not None:
                        parts.append(f"R={r_val:.2f}")
                    if p_val is not None:
                        parts.append(f"P={p_val:.2f}")
                    if rat.rating is not None:
                        parts.append(f"rating={rat.rating:.2f}")

                    info_str = " | ".join(parts) if parts else "no values"
                    lines.append(f"{prefix}{text_preview} [{info_str}]")

                    # Get critiques (audit rationales)
                    critiques = [c for c, _ in rat.critiques.all()]
                    if critiques:
                        lines.extend(format_rationale_tree(critiques, indent + 1))
                return lines

            for cycle_name, cycle_obj in cycles_to_check:
                if cycle_obj is None:
                    continue

                for trans in cycle_obj.transitions:
                    trans_repr = f"{trans}"  # Uses Transition.__str__
                    s = fmt_score(trans.score, colorize=True)
                    r = fmt_relevance(trans, colorize=True)
                    p = fmt_probability(trans, colorize=True)

                    # Get rationale hierarchy
                    rationales = [rat for rat, _ in trans.rationales.all()]
                    if rationales:
                        rationale_lines = format_rationale_tree(rationales)
                        rationale_text = "\n".join(rationale_lines)
                    else:
                        rationale_text = "No rationales"

                    transitions_data.append([cycle_name, trans_repr, s, r, p, rationale_text])

            if transitions_data:
                headers = ["Cycle", "Transition", "S", "R", "P", "Rationales"]
                output.append(tabulate(transitions_data, headers=headers, tablefmt="grid"))
            else:
                output.append("[No transitions]")
            output.append("")

        return "\n".join(output)

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def get_effective_intent(self) -> Optional[str]:
        """
        Get the effective intent, inheriting from Cycle if not set on Wheel.

        Resolution order:
        1. This wheel's intent (if set)
        2. Parent Cycle's intent (set from Nexus preset at creation)

        Returns:
            The intent string, or None if not found in lineage
        """
        if self.intent:
            return self.intent

        cycle_result = self.cycle.get()
        if cycle_result:
            cycle_obj, _ = cycle_result
            return cycle_obj.intent

        return None
