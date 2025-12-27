"""
Wheel node for the dialectical framework.

This module provides the Wheel class which represents the top-level container
for a complete dialectical system.
"""

from __future__ import annotations

from typing import ClassVar, Union, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.spiral import Spiral


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

    Properties:
    - order: Number of wisdom units (computed from relationships)
    - degree: Total segments = order × 2 (computed)
    """

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
        Get wisdom unit by alias, UID, component, or segment.

        Note: No integer indexing - use cycles to determine ordering.

        Args:
            key: Can be:
               - str: component alias (searches all WU relationships)
               - WisdomUnit: match by uid
               - DialecticalComponent: find WU containing this component
               - WheelSegment: find WU containing this segment

        Returns:
            The matching WisdomUnit

        Raises:
            ValueError: If no matching wisdom unit is found

        Examples:
            wu = wheel.wisdom_unit_at("T1")  # By alias
            wu = wheel.wisdom_unit_at(component)  # By component
            wu = wheel.wisdom_unit_at(segment)  # By segment
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
                t_seg = wu.segment_t()
                if t_seg.is_same(key):
                    return wu

                a_seg = wu.segment_a()
                if a_seg.is_same(key):
                    return wu

            raise ValueError(f"Cannot find wisdom unit containing segment")

        elif isinstance(key, str):
            # Search by alias in all wisdom units using repository
            from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository
            repo = DialecticalComponentRepository()

            for wu in wus:
                components_with_aliases = repo.find_by_wisdom_unit(wu)
                for comp, alias in components_with_aliases:
                    if alias == key:
                        return wu
            raise ValueError(f"Cannot find wisdom unit with alias: {key}")

        elif isinstance(key, DCClass):
            # Search by component
            for wu in wus:
                alias = key.get_alias(wu)
                if alias is not None:
                    return wu
            raise ValueError(f"Cannot find wisdom unit containing component: {key.uid}")

        raise ValueError(f"Cannot find wisdom unit with key: {key}")

    def wheel_segment_at(
        self,
        key: Union[str, DialecticalComponent]
    ) -> WheelSegment:
        """
        Get wheel segment (T-side or A-side) by alias or component.

        Note: No integer indexing - use cycles to determine ordering.

        Args:
            key: Can be:
               - str: component alias (e.g., "T", "T+", "A1", "A2-")
               - DialecticalComponent: find segment containing this component

        Returns:
            WheelSegment instance representing the T-side or A-side

        Raises:
            ValueError: If no matching segment is found

        Examples:
            seg = wheel.wheel_segment_at("T1")  # By alias
            seg = wheel.wheel_segment_at(component)  # By component
        """

        # Search through wisdom units
        wus = [wu for wu, _ in self.wisdom_units.all()]
        for wu in wus:
            # Check T-side segment
            t_seg = wu.segment_t()
            if t_seg.is_set(key):
                return t_seg

            # Check A-side segment
            a_seg = wu.segment_a()
            if a_seg.is_set(key):
                return a_seg

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

    def __repr__(self) -> str:
        """String representation of the wheel."""
        return f"Wheel(uid={self.uid}, polarity_count={self.polarity_count if self.wisdom_units.count() > 0 else 0})"
