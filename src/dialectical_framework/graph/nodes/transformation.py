"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents transformational
patterns within a WisdomUnit with action-reflection components.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.mixins.sequence_topology_mixin import SequenceTopologyMixin
from dialectical_framework.graph.utils.order_transitions import order_transitions

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.wheel import Wheel


class Transformation(SequenceTopologyMixin, AssessableEntity):
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
    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, 2)  # Exactly two transitions: T- → A+, A- → T+
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

    @property
    def transitions_ordered(self) -> list[Transition]:
        """
        Get transitions in transformation order by following source->target chain.

        Returns:
            List of Transition nodes in transformation order (should always be 2)
        """
        all_transitions = [trans for trans, _ in self.transitions.all()]
        return order_transitions(all_transitions)

    def get_wheel(self) -> Wheel | None:
        """
        Get the wheel this transformation belongs to via its WisdomUnit.

        Transformation is internal to a WisdomUnit, so this method:
        1. Gets the containing WisdomUnit
        2. Gets the Wheel from that WisdomUnit

        Returns:
            Wheel instance or None if not assigned to a wheel

        Example:
            wheel = transformation.get_wheel()
            if wheel:
                print(f"Transformation belongs to wheel {wheel.uid}")
        """
        # Get the containing WisdomUnit
        wu_result = self.wisdom_unit.get()
        if not wu_result:
            return None

        wisdom_unit = wu_result[0]

        # Get the Wheel from the WisdomUnit
        wheel_result = wisdom_unit.wheel.get()
        if wheel_result:
            return wheel_result[0]

        return None

    def __repr__(self) -> str:
        """String representation of the transformation."""
        return f"Transformation(uid={self.uid})"
