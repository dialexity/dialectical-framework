"""
Spiral node for the dialectical framework.

This module provides the Spiral class which represents transformational
spirals composed of transformation transitions.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.mixins.sequence_topology_mixin import SequenceTopologyMixin
from dialectical_framework.graph.utils.order_transitions import order_transitions

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel


class Spiral(SequenceTopologyMixin, AssessableEntity):
    """
    Represents a transformational spiral in the dialectical framework.

    A Spiral is an analytical interpretation - a directed graph of transitions
    that captures dialectical evolution and synthesis pathways. Spirals are
    "drawn on" a wheel to show transformational relationships that lead to synthesis.

    Unlike Cycles which track causal relationships between components, Spirals
    track transformational relationships that represent upward movement in
    dialectical reasoning, where thesis and antithesis are transformed through
    synthesis into higher-order understanding.

    Relationship to Wheel:
    - A wheel can have one primary/canonical spiral (wheel.spiral)
    - Alternative spiral interpretations can also reference the same wheel
    - Spirals can exist independently or be created after the wheel
    """

    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, None)  # At least two transitions to form a spiral
    )

    wheel: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        "IS_SPIRAL_OF",
        cardinality=(0, 1)  # Optional - spiral may analyze a wheel
    )

    @property
    def transitions_ordered(self) -> list[Transition]:
        """
        Get transitions in spiral order by following source->target chain.

        Returns:
            List of Transition nodes in spiral order, or empty list if no transitions
        """
        all_transitions = [trans for trans, _ in self.transitions.all()]
        return order_transitions(all_transitions)

    def get_wheel(self) -> Wheel | None:
        """
        Get the wheel this spiral belongs to.

        Returns:
            Wheel instance or None if not assigned to a wheel

        Example:
            wheel = spiral.get_wheel()
            if wheel:
                print(f"Spiral belongs to wheel {wheel.uid}")
        """
        wheel_result = self.wheel.get()
        if wheel_result:
            return wheel_result[0]
        return None

    def __repr__(self) -> str:
        """String representation of the spiral."""
        return f"Spiral(uid={self.uid})"
