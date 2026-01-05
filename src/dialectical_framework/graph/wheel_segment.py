"""
WheelSegment for graph-based dialectical framework.

This module provides a lightweight "window" into one side of a WisdomUnit,
exposing a unified interface regardless of which side (T or A) is being viewed.
"""

from __future__ import annotations

from typing import Literal, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.relationship_manager import BoundRelationshipManager
    from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair

from dialectical_framework.graph.relationships.polarity_relationship import PolarityRelationship


class WheelSegment:
    """
    A "window" into one side (T or A) of a WisdomUnit.

    Provides direct access to the underlying relationship managers with
    naming consistent with the domain model:
    - For T-side: t, t_plus, t_minus
    - For A-side: a, a_plus, a_minus

    This is a lightweight view object, not a node itself.
    """

    def __init__(self, wisdom_unit: WisdomUnit, side: Literal["T", "A"]):
        """
        Initialize a wheel segment window.

        Args:
            wisdom_unit: The WisdomUnit containing this segment
            side: Either 'T' or 'A' to specify which side
        """
        if side not in ('T', 'A'):
            raise ValueError(f"side must be 'T' or 'A', got: {side}")

        self._wisdom_unit = wisdom_unit
        self._side = side
        self._opposite: Optional[WheelSegment] = None
        self._polar_pair: Optional[WheelSegmentPolarPair] = None

    @property
    def wisdom_unit(self) -> WisdomUnit:
        """Get the WisdomUnit containing this segment."""
        return self._wisdom_unit

    @property
    def opposite(self) -> WheelSegment:
        """
        Get the opposite WheelSegment (the other side of the same wisdom_unit).

        For T-side segments, returns the A-side segment.
        For A-side segments, returns the T-side segment.

        The opposite segment is constructed lazily and cached for reuse.

        Example:
            t_seg = wu.extract_segment_t()
            a_seg = t_seg.opposite  # Get the A-side segment
            assert a_seg.opposite is t_seg  # Returns the same T-side instance
        """
        if self._opposite is None:
            opposite_side: Literal["T", "A"] = "A" if self._side == "T" else "T"
            self._opposite = WheelSegment(self._wisdom_unit, opposite_side)
            # Link back to ensure both sides share the same instances
            self._opposite._opposite = self
        return self._opposite

    @property
    def polar_pair(self) -> WheelSegmentPolarPair:
        """
        Get a WheelSegmentPolarPair view of this segment's wisdom unit.

        The pair is lazily created and cached. The same instance is shared
        between this segment and its opposite. Calling swap() on the returned
        pair will mutate it, affecting all subsequent accesses from both sides.

        The pair is always created in "normal" polarity initially and reuses
        the existing WheelSegment instances.

        Example:
            t_seg = wu.extract_segment_t()
            a_seg = wu.extract_segment_a()

            pair1 = t_seg.as_pair
            pair2 = a_seg.as_pair
            assert pair1 is pair2  # Same instance!

            pair1.swap()  # Mutates the shared instance
            assert t_seg.as_pair.polarity == "swapped"
            assert a_seg.as_pair.polarity == "swapped"
        """
        if self._polar_pair is None:
            # Check if opposite segment already has a pair
            opposite_seg = self.opposite
            if opposite_seg._polar_pair is not None:
                # Reuse the existing pair from opposite
                self._polar_pair = opposite_seg._polar_pair
            else:
                # Import here to avoid circular dependency
                from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair

                # Create pair with existing segments
                if self._side == "T":
                    self._polar_pair = WheelSegmentPolarPair(
                        self._wisdom_unit, "normal", t_segment=self, a_segment=opposite_seg
                    )
                else:
                    self._polar_pair = WheelSegmentPolarPair(
                        self._wisdom_unit, "normal", t_segment=opposite_seg, a_segment=self
                    )

                # Cache on opposite segment too
                opposite_seg._polar_pair = self._polar_pair

        return self._polar_pair

    @property
    def side(self) -> Literal["T", "A"]:
        """Get the side type ('T' or 'A')."""
        return self._side

    @property
    def t(self) -> BoundRelationshipManager[DialecticalComponent]:
        """
        Get the t or a relationship manager (depending on side).

        For T-side segments, returns wisdom_unit.t
        For A-side segments, returns wisdom_unit.a

        Example:
            t_seg = wu.extract_segment_t()
            t_comp = t_seg.t.get()  # Get T component

            a_seg = wu.extract_segment_a()
            a_comp = a_seg.t.get()  # Get A component (named 't' for consistency)
        """
        return self._wisdom_unit.t if self._side == 'T' else self._wisdom_unit.a

    @property
    def t_plus(self) -> BoundRelationshipManager[DialecticalComponent]:
        """
        Get the t_plus or a_plus relationship manager (depending on side).

        For T-side segments, returns wisdom_unit.t_plus
        For A-side segments, returns wisdom_unit.a_plus

        Example:
            t_seg = wu.extract_segment_t()
            t_plus_comps = [c for c, _ in t_seg.t_plus.all()]
        """
        return self._wisdom_unit.t_plus if self._side == 'T' else self._wisdom_unit.a_plus

    @property
    def t_minus(self) -> BoundRelationshipManager[DialecticalComponent]:
        """
        Get the t_minus or a_minus relationship manager (depending on side).

        For T-side segments, returns wisdom_unit.t_minus
        For A-side segments, returns wisdom_unit.a_minus

        Example:
            t_seg = wu.extract_segment_t()
            t_minus_comps = [c for c, _ in t_seg.t_minus.all()]
        """
        return self._wisdom_unit.t_minus if self._side == 'T' else self._wisdom_unit.a_minus

    def get_component(self, alias: str) -> Optional[DialecticalComponent]:
        """
        Find a component within this segment by its alias.

        Only searches within this segment's own components (t, t_plus, t_minus).
        Does not search components from other segments.

        Args:
            alias: The alias to search for (e.g., "T", "T+", "T-", "A", "A+", "A-")

        Returns:
            The matching component, or None if not found in this segment

        Example:
            t_seg = wu.extract_segment_t()
            t_seg.get_component("T1")   # Returns T component if found
            t_seg.get_component("A1")   # Returns None (not in this segment)
        """
        # Check t component (base position)
        t_result = self.t.get()
        if t_result:
            comp, rel = t_result
            if isinstance(rel, PolarityRelationship) and rel.alias == alias:
                return comp

        # Check t_plus component
        t_plus_result = self.t_plus.get()
        if t_plus_result:
            comp, rel = t_plus_result
            if isinstance(rel, PolarityRelationship) and rel.alias == alias:
                return comp

        # Check t_minus component
        t_minus_result = self.t_minus.get()
        if t_minus_result:
            comp, rel = t_minus_result
            if isinstance(rel, PolarityRelationship) and rel.alias == alias:
                return comp

        return None

    def is_same(self, other: WheelSegment) -> bool:
        """
        Check if this segment is the same as another segment.

        Compares by checking if all components (t, t_plus, t_minus) match by UID.

        Args:
            other: Another WheelSegment to compare with

        Returns:
            True if both segments have the same components
        """
        if self == other:
            return True
        if not isinstance(other, WheelSegment):
            return False

        # Compare core components
        self_t = self.t.get()
        other_t = other.t.get()

        if (self_t is None) != (other_t is None):
            return False
        if self_t and other_t and self_t[0].uid != other_t[0].uid:
            return False

        # Compare t_plus components
        self_t_plus = [c.uid for c, _ in self.t_plus.all()]
        other_t_plus = [c.uid for c, _ in other.t_plus.all()]
        if set(self_t_plus) != set(other_t_plus):
            return False

        # Compare t_minus components
        self_t_minus = [c.uid for c, _ in self.t_minus.all()]
        other_t_minus = [c.uid for c, _ in other.t_minus.all()]
        if set(self_t_minus) != set(other_t_minus):
            return False

        return True

    def is_set(self, key: str | DialecticalComponent) -> bool:
        """
        Check if a key (alias or component) exists in this segment.

        Args:
            key: Either a string alias or a DialecticalComponent

        Returns:
            True if the key exists in this segment

        Example:
            seg = wu.extract_segment_t()
            seg.is_set("T1")  # Check by alias
            seg.is_set(component)  # Check by component
        """
        if isinstance(key, str):
            # Check by alias
            return self.get_component(key) is not None
        else:
            # Check by component (DialecticalComponent)
            # Search all components in this segment
            t_result = self.t.get()
            if t_result and t_result[0].uid == key.uid:
                return True

            for comp, _ in self.t_plus.all():
                if comp.uid == key.uid:
                    return True

            for comp, _ in self.t_minus.all():
                if comp.uid == key.uid:
                    return True

            return False

    def is_complete(self) -> bool:
        """
        Check if all components in this segment are populated.

        Returns:
            True if t, t_plus, and t_minus relationships all have components
        """
        return (
            self.t.get() is not None
            and self.t_plus.count() > 0
            and self.t_minus.count() > 0
        )

    def __format__(self, format_spec: str) -> str:
        """
        Format this WheelSegment using Python's format string protocol.

        Formats the 3 core components (t, t_plus, t_minus) of this segment.

        Format Specifications:
        ----------------------
        [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored
            "positions" - Uses canonical positions (T, T+, T- or A, A+, A-)
            "strip_index" - Strips numeric indexes

        Newlines (optional):
            :0 - Comma separation (compact single line, NO explanations)
            :1 - Single newline between components (compact)
            :2 - Double newline between components (spacious, default)

        Examples:
        ---------
        f"{segment}"           - Default format
        f"{segment:positions}" - Canonical positions
        f"{segment::0}"        - Compact (comma separated, no explanations)
        f"{segment:positions:1}" - Canonical positions, single newline

        Returns:
            Formatted string with t, t_plus, t_minus components
        """
        import re
        from dialectical_framework.graph.nodes.wisdom_unit import (
            POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
            POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS
        )

        # Parse format spec: [mode][:newlines]
        if ":" in format_spec:
            mode, newlines_str = format_spec.split(":", 1)
            try:
                newlines = int(newlines_str)
            except ValueError:
                newlines = 2
        else:
            mode = format_spec
            newlines = 2

        if newlines < 0:
            newlines = 0

        # Determine component format: "short" for :0 (no explanations), "long" otherwise
        component_format = "short" if newlines < 1 else "long"

        # Map positions based on side
        if self._side == "T":
            positions = [
                (POSITION_T, self.t),
                (POSITION_T_PLUS, self.t_plus),
                (POSITION_T_MINUS, self.t_minus),
            ]
        else:
            positions = [
                (POSITION_A, self.t),
                (POSITION_A_PLUS, self.t_plus),
                (POSITION_A_MINUS, self.t_minus),
            ]

        formatted_components = []
        for position_name, manager in positions:
            result = manager.get()
            if result:
                component, rel = result
                assert isinstance(rel, PolarityRelationship)
                alias = rel.alias

                # Apply mode formatting
                if mode == "positions":
                    alias = position_name
                elif mode == "strip_index":
                    alias = re.sub(r"(\d+)(?!.*\d)", "", alias)

                formatted_components.append(f"{alias} = {component:{component_format}}")

        # Join with specified separator
        if newlines < 1:
            separator = ", "
        else:
            separator = "\n" * newlines
        return separator.join(formatted_components)

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def __repr__(self) -> str:
        """Debug representation of the segment."""
        t_result = self.t.get()
        t_uid = t_result[0].uid if t_result else "None"
        return f"WheelSegment(side={self._side}, wisdom_unit={self._wisdom_unit.uid}, t={t_uid})"
