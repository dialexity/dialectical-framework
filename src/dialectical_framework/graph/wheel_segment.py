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

    @property
    def wisdom_unit(self) -> WisdomUnit:
        """Get the WisdomUnit containing this segment."""
        return self._wisdom_unit

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

    def get_component_by_alias(self, alias: str) -> Optional[DialecticalComponent]:
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
            t_seg.get_component_by_alias("T1")   # Returns T component if found
            t_seg.get_component_by_alias("A1")   # Returns None (not in this segment)
        """
        # Collect all components in this segment using relationship managers
        segment_components = []

        # Add t component
        t_result = self.t.get()
        if t_result:
            segment_components.append(t_result[0])

        # Add t_plus and t_minus components
        segment_components.extend([comp for comp, _ in self.t_plus.all()])
        segment_components.extend([comp for comp, _ in self.t_minus.all()])

        # Search for matching alias
        for comp in segment_components:
            if comp.get_alias(self._wisdom_unit) == alias:
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
            return self.get_component_by_alias(key) is not None
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

    def __repr__(self) -> str:
        """String representation of the segment."""
        t_result = self.t.get()
        t_uid = t_result[0].uid if t_result else "None"
        return f"WheelSegment(side={self._side}, wisdom_unit={self._wisdom_unit.uid}, t={t_uid})"
