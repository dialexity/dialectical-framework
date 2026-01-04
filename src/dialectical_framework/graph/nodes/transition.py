"""
Transition node for the dialectical framework.

This module provides the Transition class which represents relationships
between dialectical components (causal, convergence, transformation).
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING, Literal

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.spiral import Spiral
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment


class Transition(AssessableEntity):
    """
    Represents a transition (relationship) between dialectical components.

    Transitions capture different types of relationships between components:
    - CAUSES: Causal transitions organized in Cycles
    - CONSTRUCTIVELY_CONVERGES_TO: Synthesis convergence organized in Spirals
    - TRANSFORMS_TO: Dialectical transformations organized in Transformations

    The semantic type of transition is implicit from its container:
    - Transitions in Cycle → CAUSES
    - Transitions in Spiral → CONSTRUCTIVELY_CONVERGES_TO
    - Transitions in Transformation → TRANSFORMS_TO

    Transitions are nodes (not edges) in the graph because they:
    1. Can be assessed/scored
    2. Have their own rationales
    3. Can have estimations (probability of transition)
    4. Are organized into Cycles, Spirals, and Transformations

    Relationships:
    - source: The representative component from the source wheel segment (1:1)
    - target: The representative component from the target wheel segment (1:1)
    - cycle: The container (Cycle, Spiral, or Transformation) this transition belongs to (0:1)

    Note: Default probability fallback is handled by the scorer (TaroRank.default_transition_probability)
    from settings, not stored on individual transition nodes.
    """

    source: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        "IS_SOURCE_OF",
        cardinality=(1, 1)
    )

    target: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "IS_TARGET_OF",
        cardinality=(1, 1)
    )

    cycle: ClassVar[RelationshipManager[Cycle | Spiral | Transformation]] = RelationshipTo(
        ("Cycle", "Spiral", "Transformation"),
        "BELONGS_TO_CYCLE",
        cardinality=(0, 1)
    )

    derived_statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "HAS_STATEMENT",
        cardinality=(0, None)
    )

    def get_wheel(self) -> Wheel | None:
        """
        Get the wheel this transition belongs to via its cycle/spiral.

        Returns:
            The wheel containing this transition's cycle, or None if not found
        """
        cycle_result = self.cycle.get()
        if not cycle_result:
            return None

        container, _ = cycle_result
        return container.get_wheel()

    def get_source_wheel_segment(self, wheel: Wheel = None) -> WheelSegment | None:
        """
        Get the wheel segment containing the source component.

        Args:
            wheel: Optional wheel to use. If not provided, gets wheel from transition's cycle.

        Returns:
            WheelSegment containing the source component, or None if not found
        """
        if wheel is None:
            wheel = self.get_wheel()
        if not wheel:
            return None

        source_result = self.source.get()
        if not source_result:
            return None

        source_comp, _ = source_result
        wu = wheel.wisdom_unit_at(source_comp)
        if not wu:
            return None

        # Determine which side (T or A) based on component's position
        position = source_comp.get_position(wu)
        if not position:
            return None

        # Positions starting with 'T' are T-side, starting with 'A' are A-side
        side: Literal["T", "A"] = "T" if position.startswith("T") else "A"

        # Import here to avoid circular dependency at module level
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(wu, side)

    def get_target_wheel_segment(self, wheel: Wheel = None) -> WheelSegment | None:
        """
        Get the wheel segment containing the target component.

        Args:
            wheel: Optional wheel to use. If not provided, gets wheel from transition's cycle.

        Returns:
            WheelSegment containing the target component, or None if not found
        """
        if wheel is None:
            wheel = self.get_wheel()
        if not wheel:
            return None

        target_result = self.target.get()
        if not target_result:
            return None

        target_comp, _ = target_result
        wu = wheel.wisdom_unit_at(target_comp)
        if not wu:
            return None

        # Determine which side (T or A) based on component's position
        position = target_comp.get_position(wu)
        if not position:
            return None

        # Positions starting with 'T' are T-side, starting with 'A' are A-side
        side: Literal["T", "A"] = "T" if position.startswith("T") else "A"

        # Import here to avoid circular dependency at module level
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(wu, side)

    def __repr__(self) -> str:
        """String representation of the transition."""
        return f"Transition(uid={self.uid})"
