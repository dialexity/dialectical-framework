"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents transformational
patterns within a WisdomUnit with action-reflection components.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.nexus import Nexus


class Transformation(CircularTopologyMixin, AssessableEntity):
    """
    Internal transformation within a WisdomUnit.

    A Transformation represents the internal dialectical transformation within
    a single wisdom unit. It captures the action-reflection cycle: T- → A+, A- → T+.

    Unlike Spiral (which exists at the Wheel level), Transformation is internal
    to a WisdomUnit and does not directly relate to Wheels.

    A transformation always has exactly 2 transitions:
    - T- to A+ (thesis negative to antithesis positive)
    - A- to T+ (antithesis negative to thesis positive)

    Relationships:
    - Transformations are internal to WisdomUnit (accessed via wisdom_unit.transformation)
    - They reference an action-reflection WisdomUnit via ac_re
    - They do NOT directly connect to Wheel (accessed via their WisdomUnit)
    - The ac_re WisdomUnit may or may not be part of the wheel's wisdom_units

    Note: Transformation and Spiral are siblings (both inherit from AssessableEntity),
    not parent-child. This prevents Transformation from inheriting Spiral's
    Wheel relationship, which would be semantically incorrect.
    """

    # Override _transitions from CircularTopologyMixin with exact cardinality
    # Exactly two transitions for internal transformation: T- → A+, A- → T+
    _transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, 2)  # Exactly two transitions
    )

    # The containing WisdomUnit (this transformation is internal to it)
    wisdom_unit: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        "IS_SPIRAL_OF",
        cardinality=(1, 1)  # Required - transformation (spiral) belongs to one wisdom unit
    )

    # The action-reflection context WisdomUnit (what this transformation is about)
    ac_re: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        "ACTION_REFLECTION",
        cardinality=(1, 1)  # Required action-reflection wisdom unit
    )

    # Note: Transformation does not directly connect to Wheel
    # It's accessed via its containing WisdomUnit (wisdom_unit field)

    def get_nexus(self) -> Nexus | None:
        """
        Get the nexus this transformation belongs to via its WisdomUnit.

        Transformation is internal to a WisdomUnit, so this method:
        1. Gets the containing WisdomUnit
        2. Gets the first Nexus from that WisdomUnit

        Returns:
            Nexus instance or None if not connected

        Example:
            nexus = transformation.get_nexus()
            if nexus:
                print(f"Transformation's source nexus has {nexus.wisdom_units.count()} WUs")
        """
        # Get the containing WisdomUnit
        wu_result = self.wisdom_unit.get()
        if not wu_result:
            return None

        wisdom_unit = wu_result[0]

        # Get the first Nexus from the WisdomUnit.
        # It's fine to take any Nexus since aliases are stored on WU-Component edges,
        # not on Nexus relationships - all Nexuses containing this WU see the same aliases.
        nexus_result = wisdom_unit.nexus.get()
        if nexus_result:
            return nexus_result[0]

        return None

    def __format__(self, format_spec: str) -> str:
        """
        Format this Transformation by displaying its ac_re WisdomUnit.

        Format specifications are passed through to the ac_re WisdomUnit's __format__ method.
        See WisdomUnit.__format__ for available format specifications.

        Format Specifications:
        ----------------------
        [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored
            "positions" - Uses canonical positions (T, T+, T-, A, A+, A-)
            "strip_index" - Strips numeric indexes

        Newlines (optional):
            :0 - Comma separation (compact single line)
            :1 - Single newline between components (compact)
            :2 - Double newline between components (spacious, default)

        Examples:
        ---------
        f"{transformation}"           - Default format
        f"{transformation:positions}" - Canonical positions
        f"{transformation::1}"        - Compact (1 newline)
        f"{transformation:positions:0}" - Canonical positions, comma separated

        Returns:
            Formatted string of the ac_re WisdomUnit, or empty string if ac_re not set
        """
        ac_re_result = self.ac_re.get()
        if not ac_re_result:
            return ""

        ac_re_wu, _ = ac_re_result
        return f"{ac_re_wu:{format_spec}}"

    def __str__(self) -> str:
        """Human-readable string representation (defaults to ac_re WisdomUnit format)."""
        return self.__format__("")

    def __repr__(self) -> str:
        """String representation of the transformation."""
        return f"Transformation(uid={self.uid})"
