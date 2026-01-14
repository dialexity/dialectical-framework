"""
Wheel node for the dialectical framework.

This module provides the Wheel class which represents the top-level container
for a complete dialectical system.
"""

from __future__ import annotations

from typing import ClassVar, Union, Optional, TYPE_CHECKING, Literal

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager
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

    # Type alias for flexible wheel segment references (no integer indexing in graph-native)
    WheelSegmentReference = Union[str, WheelSegment, DialecticalComponent]


class Wheel(AssessableEntity):
    """
    Represents a complete dialectical system (wheel metaphor).

    A Wheel is fundamentally a structured collection of WisdomUnits arranged
    in a specific configuration. The wheel represents the "raw dialectical material."

    Cycles and spirals are analytical interpretations created on top of the wheel:
    - They can be discovered/created after the wheel exists
    - A wheel can have canonical (primary) cycles/spirals
    - Alternative analyses can also reference the same wheel

    The wheel metaphor represents the circular, iterative nature of
    dialectical reasoning where thesis and antithesis are arranged in segments.

    Attributes:
        input_uri: The content source this Wheel's analysis is based on.
            This makes the Wheel a self-contained artifact that knows its origin.
            Format: Any valid URI (http, https, ipfs, file, s3, data, etc.)
            Example: "https://example.com/article" or "ipfs://Qm..."

    Properties:
        polarity_count: Number of wisdom units (computed from relationships)
        segment_count: Total segments = polarity_count × 2 (computed)
    """

    # The content source this Wheel is based on (makes Wheel self-contained)
    input_uri: Optional[str] = None

    def __init__(self, **data):
        """Initialize wheel with polar pair cache."""
        super().__init__(**data)
        # Cache for polar pairs: wu_uid -> WheelSegmentPolarPair
        self._polar_pair_cache: dict[str, WheelSegmentPolarPair] = {}

    # Declarative relationships
    wisdom_units: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipFrom(
        "WisdomUnit",
        "BELONGS_TO_WHEEL",
        cardinality=(1, None)  # One or more wisdom units
    )

    # Canonical/primary analytical structures (optional)
    # These represent the "authoritative" interpretation when one exists
    t_cycle: ClassVar[RelationshipManager[Cycle]] = RelationshipFrom(
        "Cycle",
        "IS_T_CYCLE_OF",
        cardinality=(0, 1)  # Zero or one (can be analyzed later)
    )

    ta_cycle: ClassVar[RelationshipManager[Cycle]] = RelationshipFrom(
        "Cycle",
        "IS_TA_CYCLE_OF",
        cardinality=(0, 1)  # Zero or one (can be analyzed later)
    )

    spiral: ClassVar[RelationshipManager[Spiral]] = RelationshipFrom(
        "Spiral",
        "IS_SPIRAL_OF",
        cardinality=(0, 1)  # Zero or one wheel-level spiral (Transformations are internal to WisdomUnits)
    )

    @property
    def polarity_count(self) -> int:
        """
        The number of polarities (wisdom units) in the wheel.

        Each wisdom unit represents one polarity - a thesis/antithesis pair.

        Returns:
            Number of wisdom units in the wheel

        Raises:
            ValueError: If the wheel is empty
        """
        count = self.wisdom_units.count()
        if count == 0:
            raise ValueError("The wheel is empty, therefore polarity_count is undefined.")
        return count

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

        wus = [wu for wu, _ in self.wisdom_units.all()]

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
            wus = [wu for wu, _ in self.wisdom_units.all()]
            for wu in wus:
                if wu.segment_t.is_same(key) or wu.segment_a.is_same(key):
                    return key
            raise ValueError(f"WheelSegment not found in this wheel")

        # If key is a DialecticalComponent instance, use it directly
        elif isinstance(key, DCClass):
            wus = [wu for wu, _ in self.wisdom_units.all()]
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

            wus = [wu for wu, _ in self.wisdom_units.all()]

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

    def is_same_structure(self, other: Wheel) -> bool:
        """
        Check if two wheels have the same structure.

        Compares:
        - Number of wisdom units (polarity_count)
        - T-cycle structure (if both have one)
        - TA-cycle structure (if both have one)

        Args:
            other: Another Wheel to compare with

        Returns:
            True if wheels have same structure
        """
        # Compare polarity_count
        if self.polarity_count != other.polarity_count:
            return False

        # Compare T-cycles if both exist
        self_t_cycle = self.t_cycle.get()
        other_t_cycle = other.t_cycle.get()

        if self_t_cycle and other_t_cycle:
            if not self_t_cycle[0].is_same_structure(other_t_cycle[0]):
                return False

        # Compare TA-cycles if both exist
        self_ta_cycle = self.ta_cycle.get()
        other_ta_cycle = other.ta_cycle.get()

        if self_ta_cycle and other_ta_cycle:
            if not self_ta_cycle[0].is_same_structure(other_ta_cycle[0]):
                return False

        return True

    @property
    def _wisdom_units_ordered(self) -> list[WisdomUnit]:
        """
        Internal helper: Get all wisdom units in ta_cycle order.

        Traverses the ta_cycle to determine the canonical ordering of wisdom units.
        This is used internally by polar_pairs_ordered. External code should use
        polar_pairs_ordered instead.

        Returns:
            List of WisdomUnit nodes in ta_cycle order

        Raises:
            ValueError: If ta_cycle is not set on this wheel
        """
        # Get ta_cycle
        ta_cycle_result = self.ta_cycle.get()
        if not ta_cycle_result:
            raise ValueError("ta_cycle is not set on this wheel")

        ta_cycle_obj, _ = ta_cycle_result

        # Get ordered transitions from ta_cycle
        ordered_transitions = ta_cycle_obj.transitions_ordered

        # Track which wisdom units we've seen to avoid duplicates
        seen_wisdom_units = set()
        wisdom_units = []

        # Traverse transitions and extract wisdom units
        for transition in ordered_transitions:
            # Get source component from transition (cardinality 1,1)
            source_result = transition.source.get()
            if not source_result:
                continue

            source_component, _ = source_result

            # Find which wisdom unit this component belongs to
            for wu, _ in self.wisdom_units.all():
                # Check if this component belongs to this wisdom unit
                try:
                    source_component.get_alias(wu)
                    # Found it - add if not already seen
                    if wu.uid not in seen_wisdom_units:
                        wisdom_units.append(wu)
                        seen_wisdom_units.add(wu.uid)
                    break
                except ValueError:
                    continue  # Not in this WU

        return wisdom_units

    @property
    def polar_pairs_ordered(self) -> list[WheelSegmentPolarPair]:
        """
        Get all wisdom units as WheelSegmentPolarPair objects in ta_cycle order.

        The ta_cycle determines which side of each WU appears on the left/west.
        For example, if ta_cycle is T1 → A2 → A1 → T2, the pairs are:
        - Pair 1: (T1 on left, A1 on right) - T1 appears first
        - Pair 2: (A2 on left, T2 on right) - A2 appears first

        Polar pairs are cached per wisdom unit to ensure the same instances are reused.

        Returns:
            List of WheelSegmentPolarPair objects in ta_cycle order with correct orientation

        Raises:
            ValueError: If ta_cycle is not set on this wheel

        Example:
            pairs = wheel.polar_pairs_ordered
            for pair in pairs:
                print(f"Left: {pair.segment_left.t.get()[0].statement}")
                print(f"Right: {pair.segment_right.t.get()[0].statement}")
        """
        from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
        from dialectical_framework.graph.nodes.wisdom_unit import (
            POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
            POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS
        )

        # Get ta_cycle
        ta_cycle_result = self.ta_cycle.get()
        if not ta_cycle_result:
            raise ValueError("ta_cycle is not set on this wheel")

        ta_cycle_obj, _ = ta_cycle_result

        # Get ordered transitions from ta_cycle
        ordered_transitions = ta_cycle_obj.transitions_ordered

        # Build a lookup map: component_uid -> (wisdom_unit, position)
        # This avoids repeated searches through all WUs for each transition
        component_to_wu_map = {}
        for wu, _ in self.wisdom_units.all():
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
    def segments_ordered(self) -> list[WheelSegment]:
        """
        Get all wheel segments (T and A sides) following the actual ta_cycle traversal order.

        Returns segments in the exact order they appear in the ta_cycle, which is the
        correct order for creating spiral transitions (each segment's minus connects to
        the next segment's plus).

        Returns:
            List of WheelSegment objects in ta_cycle traversal order

        Raises:
            ValueError: If ta_cycle is not set on this wheel

        Example:
            # If ta_cycle is T1 → A2 → A1 → T2:
            # Returns: [T1, A2, A1, T2] (exact ta_cycle order)

            segments = wheel.segments_ordered
            for seg in segments:
                comp = seg.t.get()
                if comp:
                    print(f"{seg.side}: {comp[0].statement}")
        """
        # Get ta_cycle
        ta_cycle_result = self.ta_cycle.get()
        if not ta_cycle_result:
            raise ValueError("ta_cycle is not set on this wheel")

        ta_cycle_obj, _ = ta_cycle_result

        # Get ordered transitions from ta_cycle
        ordered_transitions = ta_cycle_obj.transitions_ordered

        # Extract segments by following the ta_cycle transitions
        segments = []
        seen_segments = set()

        for transition in ordered_transitions:
            # Get source component
            source_result = transition.source.get()
            if not source_result:
                continue

            source_component, _ = source_result

            # Find which segment this component belongs to
            for wu, _ in self.wisdom_units.all():
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
        Get the next segment in ta_cycle order.

        Args:
            current: The current segment

        Returns:
            The next segment in ta_cycle circular order

        Raises:
            ValueError: If current segment is not found in this wheel
        """
        segments = self.segments_ordered

        # Find current segment
        for i, seg in enumerate(segments):
            if seg.is_same(current):
                # Return next segment (wrap around if at end)
                next_index = (i + 1) % len(segments)
                return segments[next_index]

        raise ValueError(f"Segment not found in wheel's ta_cycle order")

    def __repr__(self) -> str:
        """String representation of the wheel."""
        return f"Wheel(uid={self.uid}, polarity_count={self.polarity_count if self.wisdom_units.count() > 0 else 0})"

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
        - T-cycle with rationale
        - TA-cycle with rationale
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

        # T-Cycle
        t_cycle_result = self.t_cycle.get()
        if t_cycle_result:
            t_cycle_obj, _ = t_cycle_result
            output.extend(_format_cycle(t_cycle_obj, "T-Cycle"))
            output.append("")

        # TA-Cycle
        ta_cycle_result = self.ta_cycle.get()
        if ta_cycle_result:
            ta_cycle_obj, _ = ta_cycle_result
            output.extend(_format_cycle(ta_cycle_obj, "TA-Cycle"))
            output.append("")

        # Wisdom Units (tabular with transformations)
        # Use polar_pairs_ordered to get wisdom units in ta_cycle order with correct polarity
        output.append("=== Wisdom Units / Transformations ===")

        try:
            polar_pairs = self.polar_pairs_ordered
        except ValueError:
            # ta_cycle not set, fall back to unordered wisdom units
            from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair
            polar_pairs = [WheelSegmentPolarPair(wu, "normal") for wu, _ in self.wisdom_units.all()]

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

            # Collect transitions from all cycles
            cycles_to_check = [
                ("T-Cycle", t_cycle_result[0] if t_cycle_result else None),
                ("TA-Cycle", ta_cycle_result[0] if ta_cycle_result else None),
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

                for trans, _ in cycle_obj.transitions.all():
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
