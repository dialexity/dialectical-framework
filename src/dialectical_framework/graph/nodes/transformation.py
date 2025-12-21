"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents transformational
patterns within a WisdomUnit with action-reflection components.
"""

from __future__ import annotations

from typing import ClassVar

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager


class Transformation(AssessableEntity):
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

    # Exactly two transitions for internal transformation
    transitions: ClassVar[RelationshipManager] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, 2)  # Exactly two transitions: T- → A+, A- → T+
    )

    # The containing WisdomUnit (this transformation is internal to it)
    wisdom_unit: ClassVar[RelationshipManager] = RelationshipTo(
        "WisdomUnit",
        "IS_SPIRAL_OF",
        cardinality=(1, 1)  # Required - transformation (spiral) belongs to one wisdom unit
    )

    # The action-reflection context WisdomUnit (what this transformation is about)
    ac_re: ClassVar[RelationshipManager] = RelationshipTo(
        "WisdomUnit",
        "ACTION_REFLECTION",
        cardinality=(1, 1)  # Required action-reflection wisdom unit
    )

    # Note: Transformation does not directly connect to Wheel
    # It's accessed via its containing WisdomUnit (wisdom_unit field)

    def __repr__(self) -> str:
        """String representation of the transformation."""
        return f"Transformation(uid={self.uid})"
