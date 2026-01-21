"""
Wheel node for the dialectical framework.

This module provides the Wheel class which represents the top-level container
for a complete dialectical system.
"""

from __future__ import annotations

from typing import ClassVar, Union, TYPE_CHECKING, Literal, Any

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager
from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin
from dialectical_framework.graph.nodes.wisdom_unit import (
    POSITION_T,
    POSITION_T_PLUS,
    POSITION_T_MINUS,
    POSITION_A,
    POSITION_A_PLUS,
    POSITION_A_MINUS,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.spiral import Spiral
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.nexus import Nexus

    # Type alias for flexible wheel segment references (no integer indexing in graph-native)
    WheelSegmentReference = Union[str, WheelSegment, DialecticalComponent]


class Wheel(CircularTopologyMixin, AssessableEntity):
    """
    Represents a detailed dialectical arrangement belonging to a Cycle.

    A Wheel is a concrete implementation of a Cycle's causal arrangement,
    containing transitions that form the detailed causal loop through
    thesis and antithesis components.

    Hierarchy:
        Nexus (pool of WUs) → Cycle (arrangement) → Wheel (detailed implementation)

    The wheel metaphor represents the circular, iterative nature of
    dialectical reasoning where thesis and antithesis are arranged in segments.

    Relationships:
    - Wheel belongs to exactly one Cycle
    - WisdomUnits are accessed via cycle.nexus (not stored directly on Wheel)
    - Wheel can have a Spiral for transformational sequences

    Properties:
        polarity_count: Number of wisdom units (computed via cycle.nexus)
        segment_count: Total segments = polarity_count × 2 (computed)
        wisdom_units: WisdomUnits accessed via cycle.nexus (property)
    """

    def __init__(self, **data):
        """Initialize wheel with polar pair cache."""
        super().__init__(**data)
        # Cache for polar pairs: wu_uid -> WheelSegmentPolarPair
        self._polar_pair_cache: dict[str, WheelSegmentPolarPair] = {}

    # Parent Cycle (required)
    # Parent→child: Cycle has this Wheel
    cycle: ClassVar[RelationshipManager[Cycle]] = RelationshipFrom(
        "Cycle",
        "HAS_WHEEL",
        cardinality=(1, 1)  # Exactly one parent cycle
    )

    # Note: transitions relationship is inherited from CircularTopologyMixin as _transitions
    # Access via .transitions property which returns ordered list

    # Optional spiral (transformational sequence)
    spiral: ClassVar[RelationshipManager[Spiral]] = RelationshipFrom(
        "Spiral",
        "IS_SPIRAL_OF",
        cardinality=(0, 1)  # Zero or one wheel-level spiral
    )

    @property
    def wisdom_units(self) -> list[WisdomUnit]:
        """
        Get WisdomUnits in transition order.

        WisdomUnits are accessed via Wheel → Cycle → Nexus, then ordered
        by following the wheel's transitions. This is the canonical ordering
        for the wheel.

        Returns:
            List of WisdomUnit nodes in transition order

        Raises:
            ValueError: If wheel has no transitions
        """
        ordered_transitions = self.transitions
        if not ordered_transitions:
            raise ValueError("Wheel has no transitions")

        # Get all WUs from Nexus
        cycle_result = self.cycle.get()
        if not cycle_result:
            return []

        cycle_obj, _ = cycle_result
        nexus_result = cycle_obj.nexus.get()
        if not nexus_result:
            return []

        nexus_obj, _ = nexus_result
        all_wus = [wu for wu, _ in nexus_obj.wisdom_units.all()]

        # Track which wisdom units we've seen to avoid duplicates
        seen_wisdom_units = set()
        wisdom_units_list = []

        # Traverse transitions and extract wisdom units in order
        for transition in ordered_transitions:
            source_result = transition.source.get()
            if not source_result:
                continue

            source_component, _ = source_result

            # Find which wisdom unit this component belongs to
            for wu in all_wus:
                try:
                    source_component.get_alias(wu)
                    # Found it - add if not already seen
                    if wu.uid not in seen_wisdom_units:
                        wisdom_units_list.append(wu)
                        seen_wisdom_units.add(wu.uid)
                    break
                except ValueError:
                    continue  # Not in this WU

        return wisdom_units_list

    def get_nexus(self) -> Nexus | None:
        """
        Get the source Nexus for this wheel via its Cycle.

        Returns:
            Nexus instance or None if not connected

        Example:
            nexus = wheel.get_nexus()
            if nexus:
                print(f"Wheel's source nexus has {nexus.wisdom_units.count()} WUs")
        """
        cycle_result = self.cycle.get()
        if not cycle_result:
            return None

        cycle_obj, _ = cycle_result
        return cycle_obj.get_nexus()

    @property
    def polarity_count(self) -> int:
        """
        The number of polarities (wisdom units) in the wheel.

        Each wisdom unit represents one polarity - a thesis/antithesis pair.
        Computed via cycle.nexus.wisdom_units.

        Returns:
            Number of wisdom units in the wheel

        Raises:
            ValueError: If the wheel has no WisdomUnits
        """
        wus = self.wisdom_units
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

    def wisdom_unit_at(
        self,
        key: Union[str, WisdomUnit, DialecticalComponent, WheelSegment]
    ) -> WisdomUnit:
        """
        Get wisdom unit by various identifiers.

        Note: No integer indexing - use cycles to determine ordering.

        Args:
            key: Can be:
               - str: Tries in order:
                 1. WisdomUnit UID (e.g., "wu_12345")
                 2. Component UID (e.g., "comp_67890")
                 3. Component alias (e.g., "T1", "A2+")
               - WisdomUnit: match by uid
               - DialecticalComponent: find WU containing this component
               - WheelSegment: find WU containing this segment

        Returns:
            The matching WisdomUnit

        Raises:
            ValueError: If no matching wisdom unit is found

        Examples:
            wu = wheel.wisdom_unit_at("wu_123")  # By WU UID
            wu = wheel.wisdom_unit_at("comp_456")  # By component UID
            wu = wheel.wisdom_unit_at("T1")  # By component alias
            wu = wheel.wisdom_unit_at(component)  # By component instance
            wu = wheel.wisdom_unit_at(segment)  # By segment instance
            wu = wheel.wisdom_unit_at(wisdom_unit)  # By WU instance
        """
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit as WUClass
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent as DCClass
        from dialectical_framework.graph.wheel_segment import WheelSegment

        wus = self.wisdom_units

        if isinstance(key, WUClass):
            # Match by UID
            for wu in wus:
                if wu.uid == key.uid:
                    return wu
            raise ValueError(f"WisdomUnit {key.uid} not found in wheel")

        elif isinstance(key, WheelSegment):
            # Match by segment
            for wu in wus:
                t_seg = wu.segment_t
                if t_seg.is_same(key):
                    return wu

                a_seg = wu.segment_a
                if a_seg.is_same(key):
                    return wu

            raise ValueError(f"Cannot find wisdom unit containing segment")

        elif isinstance(key, str):
            # Try string as three possibilities: WU UID, component UID, or component alias

            # 1. Try as WisdomUnit UID (fast, direct lookup)
            for wu in wus:
                if wu.uid == key:
                    return wu

            # 2. Try as component UID (iterate through all components in all WUs)
            from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
            repo = DialecticalComponentRepository()

            for wu in wus:
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if comp.uid == key:
                        return wu

            # 3. Finally try as component alias
            for wu in wus:
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if alias == key:
                        return wu

            raise ValueError(f"Cannot find wisdom unit with key: {key} (tried as WU UID, component UID, and component alias)")

        elif isinstance(key, DCClass):
            # Search by component
            for wu in wus:
                try:
                    key.get_alias(wu)
                    return wu  # Found it
                except ValueError:
                    continue  # Not in this WU
            raise ValueError(f"Cannot find wisdom unit containing component: {key.uid}")

        raise ValueError(f"Cannot find wisdom unit with key: {key}")

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
            wus = self.wisdom_units
            for wu in wus:
                if wu.segment_t.is_same(key) or wu.segment_a.is_same(key):
                    return key
            raise ValueError(f"WheelSegment not found in this wheel")

        # If key is a DialecticalComponent instance, use it directly
        elif isinstance(key, DCClass):
            wus = self.wisdom_units
            for wu in wus:
                # Check T-side segment
                t_seg = wu.segment_t
                if t_seg.is_set(key):
                    return t_seg

                # Check A-side segment
                a_seg = wu.segment_a
                if a_seg.is_set(key):
                    return a_seg

            raise ValueError(f"Cannot find wheel segment containing component: {key.uid}")

        # If key is a string, try as component UID first, then alias
        elif isinstance(key, str):
            from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
            repo = DialecticalComponentRepository()

            wus = self.wisdom_units

            # 1. Try as component UID
            for wu in wus:
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if comp.uid == key:
                        # Found component by UID, now find which segment it's in
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
            self.wisdom_unit_at(key)
            return True
        except ValueError:
            return False

    @property
    def polar_pairs(self) -> list[WheelSegmentPolarPair]:
        """
        Get all wisdom units as WheelSegmentPolarPair objects in transition order.

        The transitions determine which side of each WU appears on the left/west.
        For example, if transitions follow T1 → A2 → A1 → T2, the pairs are:
        - Pair 1: (T1 on left, A1 on right) - T1 appears first
        - Pair 2: (A2 on left, T2 on right) - A2 appears first

        Polar pairs are cached per wisdom unit to ensure the same instances are reused.

        Returns:
            List of WheelSegmentPolarPair objects in transition order with correct orientation

        Raises:
            ValueError: If wheel has no transitions

        Example:
            pairs = wheel.polar_pairs
            for pair in pairs:
                print(f"Left: {pair.segment_left.t.get()[0].statement}")
                print(f"Right: {pair.segment_right.t.get()[0].statement}")
        """
        from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
        from dialectical_framework.graph.nodes.wisdom_unit import (
            POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
            POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS
        )

        # Wheel is now CircularTopologyMixin, get transitions directly
        ordered_transitions = self.transitions

        if not ordered_transitions:
            raise ValueError("Wheel has no transitions")

        # Build a lookup map: component_uid -> (wisdom_unit, position)
        # This avoids repeated searches through all WUs for each transition
        component_to_wu_map = {}
        for wu in self.wisdom_units:
            # Check all positions in this WU
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
                    component_to_wu_map[comp.uid] = (wu, position)

        # Track which wisdom units we've seen
        seen_wisdom_units = set()
        pairs = []

        # Traverse transitions to determine which side appears first for each WU
        for transition in ordered_transitions:
            # Get source component from transition (cardinality 1,1)
            source_result = transition.source.get()
            if not source_result:
                continue

            source_component, _ = source_result

            # Look up wisdom unit and position from map
            wu_info = component_to_wu_map.get(source_component.uid)
            if wu_info is None:
                continue

            wu, position = wu_info

            if wu.uid in seen_wisdom_units:
                continue

            # Determine polarity based on which side appears first
            polarity: Literal["normal", "swapped"]
            if position in [POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS]:
                polarity = "normal"  # T-side appears first
            elif position in [POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS]:
                polarity = "swapped"  # A-side appears first
            else:
                # Skip synthesis positions
                continue

            # Get or create cached pair
            cache_key = f"{wu.uid}:{polarity}"
            if cache_key not in self._polar_pair_cache:
                self._polar_pair_cache[cache_key] = WheelSegmentPolarPair(wu, polarity)

            pair = self._polar_pair_cache[cache_key]
            pairs.append(pair)
            seen_wisdom_units.add(wu.uid)

        return pairs

    @property
    def segments(self) -> list[WheelSegment]:
        """
        Get all wheel segments (T and A sides) in transition order.

        Returns segments in the exact order they appear in the wheel's transitions,
        which is the correct order for creating spiral transitions (each segment's
        minus connects to the next segment's plus).

        Returns:
            List of WheelSegment objects in transition order

        Raises:
            ValueError: If wheel has no transitions

        Example:
            # If transitions follow T1 → A2 → A1 → T2:
            # Returns: [T1, A2, A1, T2] (exact transition order)

            for seg in wheel.segments:
                comp = seg.t.get()
                if comp:
                    print(f"{seg.side}: {comp[0].statement}")
        """
        # Wheel is now CircularTopologyMixin, get transitions directly
        ordered_transitions = self.transitions

        if not ordered_transitions:
            raise ValueError("Wheel has no transitions")

        # Extract segments by following the transitions
        segments = []
        seen_segments = set()

        for transition in ordered_transitions:
            # Get source component
            source_result = transition.source.get()
            if not source_result:
                continue

            source_component, _ = source_result

            # Find which segment this component belongs to
            for wu in self.wisdom_units:
                # Try to get segment containing this component
                t_seg = wu.segment_t
                if t_seg.is_set(source_component):
                    seg_key = (wu.uid, t_seg.side)
                    if seg_key not in seen_segments:
                        segments.append(t_seg)
                        seen_segments.add(seg_key)
                    break

                a_seg = wu.segment_a
                if a_seg.is_set(source_component):
                    seg_key = (wu.uid, a_seg.side)
                    if seg_key not in seen_segments:
                        segments.append(a_seg)
                        seen_segments.add(seg_key)
                    break

        return segments

    def get_next_segment(self, current: WheelSegment) -> WheelSegment:
        """
        Get the next segment in transition order.

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

        raise ValueError(f"Segment not found in wheel's transition order")

    def __repr__(self) -> str:
        """String representation of the wheel."""
        try:
            wus = self.wisdom_units
            polarity_count = len(wus) if wus else 0
        except (ValueError, AttributeError):
            polarity_count = 0
        return f"Wheel(uid={self.uid}, polarity_count={polarity_count})"

    def __format__(self, format_spec: str) -> str:
        """
        Format this Wheel using Python's format string protocol.

        Format Specifications:
        ----------------------
        Modifiers can be combined with `:` separator.

        Modes:
        - (empty) - Default format showing cycles, wisdom units, and spiral
        - "compact" - Compact format with abbreviated components

        Modifiers:
        - "scores" - Shows S/R/P values for wheel, cycles, spiral, transformations
                     Calculated values shown in [brackets], manual without

        Shows:
        - Parent Cycle (t_cycle) with rationale
        - Wheel transitions (ta_cycle level)
        - Tabular view of all wisdom units using WheelSegmentPolarPair
        - Spiral with rationale (if present)

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
            prefix = f"{cycle_obj.causality_type} : " if isinstance(cycle_obj, Cycle) else ""
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

        # Wheel transitions (ta_cycle level) - Wheel is now CircularTopologyMixin
        if len(self.transitions) > 0:
            lines = []
            header = "=== Wheel Transitions (ta_cycle) ==="
            if show_scores:
                header = f"=== Wheel Transitions [{fmt_scores(self, colorize=True)}] ==="
            lines.append(header)
            # Use CircularTopologyMixin's __format__ directly to avoid recursion
            lines.append(CircularTopologyMixin.__format__(self, "aliases"))

            # Add the best rationale if it exists
            rationale = self.best_rationale
            if rationale and rationale.text:
                lines.append(f"Rationale: {rationale.text}")

            output.extend(lines)
            output.append("")

        # Wisdom Units (tabular with transformations)
        # Use polar_pairs to get wisdom units in transition order with correct polarity
        output.append("=== Wisdom Units / Transformations ===")

        try:
            polar_pairs = self.polar_pairs
        except ValueError:
            # No transitions, fall back to unordered wisdom units
            from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
            polar_pairs = [WheelSegmentPolarPair(wu, "normal") for wu in self.wisdom_units]

        if polar_pairs:
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

            # Build table: each row is a position, columns are (alias, statement) pairs for WU and then for Transformation
            table = []
            for position_attr, position_label in positions:
                row = []
                for pair in polar_pairs:
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

                    # Transformation (AC/RE) columns
                    transformation_result = wu.transformation.get()
                    if transformation_result:
                        transformation, _ = transformation_result
                        ac_re_result = transformation.ac_re.get()
                        if ac_re_result:
                            ac_re_wu, _ = ac_re_result
                            trans_manager = ac_re_wu.get_relationship_manager_by_position(position_label)
                            trans_result = trans_manager.get()
                            if trans_result:
                                trans_comp, trans_rel = trans_result
                                assert isinstance(trans_rel, PolarityRelationship)
                                row.append(trans_rel.alias)
                                row.append(trans_comp.statement)
                            else:
                                row.append("")
                                row.append("")
                        else:
                            row.append("")
                            row.append("")
                    else:
                        row.append("")
                        row.append("")

                table.append(row)

            output.append(tabulate(table, tablefmt="plain"))

            # Show transformation scores if in scores mode
            if show_scores:
                output.append("")
                output.append("Transformation Scores:")
                for idx, pair in enumerate(polar_pairs, 1):
                    wu = pair.wisdom_unit
                    transformation_result = wu.transformation.get()
                    if transformation_result:
                        transformation, _ = transformation_result
                        output.append(f"  WU{idx}: [{fmt_scores(transformation, colorize=True)}]")
                    else:
                        output.append(f"  WU{idx}: [No transformation]")
        else:
            output.append("[No wisdom units]")
        output.append("")

        # Spiral (if present)
        spiral_result = self.spiral.get()
        if spiral_result:
            spiral_obj, _ = spiral_result
            output.extend(_format_cycle(spiral_obj, "Spiral"))
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
                ("Spiral", spiral_result[0] if spiral_result else None),
            ]

            # Add transformation transitions
            for idx, pair in enumerate(polar_pairs, 1):
                wu = pair.wisdom_unit
                transformation_result = wu.transformation.get()
                if transformation_result:
                    transformation, _ = transformation_result
                    cycles_to_check.append((f"WU{idx} Trans", transformation))

            def format_rationale_tree(rationales: list, indent: int = 0) -> list[str]:
                """Format rationale hierarchy with scores."""
                lines = []
                prefix = "  " * indent + "- " if indent > 0 else "- "
                for rat in rationales:
                    # Format rationale line with scores
                    text_preview = rat.text[:40] + "..." if rat.text and len(rat.text) > 40 else (rat.text or "Unnamed rationale")
                    s_str = f"S={fmt_score(rat.score, colorize=False)}"
                    r_str = f"R={fmt_relevance(rat, colorize=False)}"
                    p_str = f"P={fmt_probability(rat, colorize=False)}"
                    lines.append(f"{prefix}{text_preview} [{s_str} | {r_str} | {p_str}]")

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
