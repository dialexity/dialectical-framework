"""
WisdomUnit with declarative relationships and cardinality constraints.

This version uses the enhanced RelationshipManager with cardinality support
for automatic validation and enforcement.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager, BoundRelationshipManager
from dialectical_framework.graph.relationships.polarity_relationship import (
    TRelationship,
    TPlusRelationship,
    TMinusRelationship,
    ARelationship,
    APlusRelationship,
    AMinusRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.synthesis import Synthesis
    from dialectical_framework.graph.wheel_segment import WheelSegment


class WisdomUnit(AssessableEntity):
    """
    Represents ONE coherent dialectical analysis with enforced cardinality.

    A WisdomUnit contains exactly ONE component per polarity position:
    - Thesis side (T-side): 1 T, 1 T+, 1 T-
    - Antithesis side (A-side): 1 A, 1 A+, 1 A-

    Total: 6 core positions forming a complete dialectical analysis.

    Each WisdomUnit represents ONE dialectical exploration. To explore multiple
    consequences or alternative perspectives on the same thesis, create multiple
    WisdomUnits that share the same T component node (component reuse pattern).

    Synthesis (S+, S-) is a separate optional entity that represents emergent
    properties derived from the dialectic. It is connected via the synthesis
    relationship, not stored as core positions.

    The cardinality constraints are enforced at the RelationshipManager level,
    providing automatic validation and runtime checks.
    """

    # Position constants - use these instead of string literals
    POSITION_T = "T"
    POSITION_T_PLUS = "T+"
    POSITION_T_MINUS = "T-"
    POSITION_A = "A"
    POSITION_A_PLUS = "A+"
    POSITION_A_MINUS = "A-"

    reasoning_mode: Optional[str] = None

    # Declarative relationships with specific polarity relationship types
    # The alias is stored on the relationship edge, making component positions contextual
    # Each polarity has its own relationship type for fine-grained querying

    # T-side (exactly one neutral thesis)
    t: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # T+ side (exactly one positive thesis)
    t_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TPlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # T- side (exactly one negative thesis)
    t_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A-side (exactly one neutral antithesis)
    a: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=ARelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A+ side (exactly one positive antithesis)
    a_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=APlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A- side (exactly one negative antithesis)
    a_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=AMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # Optional synthesis (emergent properties derived from dialectic)
    # Multiple synthesis alternatives can exist for the same WU
    synthesis: ClassVar[RelationshipManager[Synthesis]] = RelationshipFrom(
        "Synthesis",
        "SYNTHESIS_OF",
        cardinality=(0, None)  # Zero or more synthesis alternatives
    )

    # Relationship to Wheel
    wheel: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        "BELONGS_TO_WHEEL",
        cardinality=(0, 1)  # Zero or one wheel
    )

    # Internal transformation spiral (T- → A+, A- → T+)
    transformation: ClassVar[RelationshipManager[Transformation]] = RelationshipFrom(
        "Transformation",
        "IS_SPIRAL_OF",
        cardinality=(0, 1)  # Zero or one internal transformation spiral
    )

    # Note: Transformation.ac_re points to action-reflection WisdomUnit
    # To find transformations referencing this WU, query via Transformation.ac_re

    def __repr__(self) -> str:
        """String representation of the wisdom unit."""
        return f"WisdomUnit(uid={self.uid}, reasoning_mode={self.reasoning_mode})"

    def is_complete(self) -> bool:
        """
        Check if this wisdom unit has all required components.

        A WisdomUnit is complete when it has:
        - Required: t, a, t_plus, t_minus, a_plus, a_minus (at least one each)
        - Optional: s_plus, s_minus (don't affect completeness)

        Returns:
            True if all required components are present
        """
        return (
            self.t.count() >= 1
            and self.t_plus.count() >= 1
            and self.t_minus.count() >= 1
            and self.a.count() >= 1
            and self.a_plus.count() >= 1
            and self.a_minus.count() >= 1
        )

    def segment_t(self) -> WheelSegment:
        """
        Get the T-side segment as a WheelSegment window.

        Returns:
            WheelSegment providing access to T, T+, T- relationships

        Example:
            wu = WisdomUnit(...)
            t_seg = wu.segment_t()
            t_comp = t_seg.t.get()  # Get T component
            t_plus_comps = [c for c, _ in t_seg.t_plus.all()]  # Get T+ components
            t_minus_comps = [c for c, _ in t_seg.t_minus.all()]  # Get T- components
        """
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(self, 'T')

    def segment_a(self) -> WheelSegment:
        """
        Get the A-side segment as a WheelSegment window.

        Returns:
            WheelSegment providing access to A, A+, A- relationships

        Example:
            wu = WisdomUnit(...)
            a_seg = wu.segment_a()
            a_comp = a_seg.t.get()  # Get A component (using 't' property)
            a_plus_comps = [c for c, _ in a_seg.t_plus.all()]  # Get A+ components
            a_minus_comps = [c for c, _ in a_seg.t_minus.all()]  # Get A- components
        """
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(self, 'A')

    def get_relationship_manager_by_position(self, position: str) -> BoundRelationshipManager[DialecticalComponent]:
        """
        Get the bound relationship manager for a given position name.

        Args:
            position: Position name (e.g., 'T', 'A', 'T+', 'T-', 'A+', 'A-')

        Returns:
            The corresponding BoundRelationshipManager (bound to this WU instance)

        Raises:
            ValueError: If position is not recognized (including S+/S- which are on Synthesis node)

        Note:
            Position is NOT the same as alias!
            - Position: Structural role ('T', 'A+') - which relationship manager
            - Alias: Display label stored on edge ('T1', 'Democracy', 'A3+') - can be anything
        """
        position_map = {
            # Position constants
            self.POSITION_T: self.t,
            self.POSITION_A: self.a,
            self.POSITION_T_PLUS: self.t_plus,
            self.POSITION_T_MINUS: self.t_minus,
            self.POSITION_A_PLUS: self.a_plus,
            self.POSITION_A_MINUS: self.a_minus,
            # Attribute format (lowercase, underscore) for backward compatibility
            't': self.t,
            'a': self.a,
            't_plus': self.t_plus,
            't_minus': self.t_minus,
            'a_plus': self.a_plus,
            'a_minus': self.a_minus,
        }
        if position not in position_map:
            raise ValueError(f"Unknown position: {position}. Note: S+/S- are on the Synthesis node, not WisdomUnit.")
        return position_map[position]

    def is_set(self, position: str) -> bool:
        """
        Check if a component is connected at the given position.

        Args:
            position: Position name (e.g., 'T', 'A', 'T+')

        Returns:
            True if at least one component is connected at this position
        """
        try:
            manager = self.get_relationship_manager_by_position(position)
            return manager.count() > 0
        except ValueError:
            return False

    def get_component(self, alias: str) -> Optional[DialecticalComponent]:
        """
        Get the component with a given alias by searching all positions.

        Alias can be anything: 'T', 'T1', 'A3+', 'Democracy', etc.
        This method searches all relationship managers to find which component
        has this alias stored on its edge.

        Args:
            alias: Component alias to search for (any string)

        Returns:
            The component if found, None otherwise

        Example:
            wu.get_component('T1')  # Finds component with alias='T1'
            wu.get_component('Democracy')  # Finds component with alias='Democracy'
        """
        # Search all 6 core positions
        for manager in [self.t, self.t_plus, self.t_minus, self.a, self.a_plus, self.a_minus]:
            for component, props in manager.all():
                if props.get('alias') == alias:
                    return component
        return None

    @property
    def core_positions(self) -> list[str]:
        """
        Get list of all 6 core position names.

        Returns:
            List of position names that can be used with get_relationship_manager_by_position()

        Note: S+/S- are NOT included - they are on the Synthesis node
        """
        return [
            self.POSITION_T,
            self.POSITION_A,
            self.POSITION_T_PLUS,
            self.POSITION_T_MINUS,
            self.POSITION_A_PLUS,
            self.POSITION_A_MINUS,
        ]

    def get_human_friendly_index(self) -> int:
        """
        Extract the human-friendly index from component aliases in this WU.

        Looks at the T component's alias and extracts the numeric index.
        If no index exists, returns 0.

        Returns:
            The numeric index (e.g., T3 → 3, T → 0)

        Example:
            wu.set_human_friendly_index(3)  # T → T3
            wu.get_human_friendly_index()   # Returns 3
        """
        import re

        # Get T component alias as representative
        t_result = self.t.get()
        if not t_result:
            return 0

        _, props = t_result
        alias = props.get('alias', '')

        # Find the last sequence of digits in the alias
        match = re.search(r"(\d+)(?!.*\d)", alias)
        return int(match.group(1)) if match else 0

    def set_human_friendly_index(self, human_friendly_index: int) -> None:
        """
        Updates the alias of all components in this WU by setting the numeric index.

        If the index is 0, removes any existing digits entirely.
        If no digits exist and index > 0, inserts the index before any trailing signs.

        Format: T3+, A1-, T2 (NOT T+3, A-1)

        Args:
            human_friendly_index: The integer index (0 = strip numbers, >0 = add/replace)

        Example:
            wu.set_human_friendly_index(3)
            # T → T3, A+ → A3+, T- → T3-, etc.
        """
        import re

        for manager in [self.t, self.t_plus, self.t_minus, self.a, self.a_plus, self.a_minus]:
            for component, props in manager.all():
                old_alias = props.get('alias', '')
                if not old_alias:
                    continue

                # Apply same logic as legacy DialecticalComponent.set_human_friendly_index
                if human_friendly_index == 0:
                    # Remove the last sequence of digits entirely
                    new_alias = re.sub(r"(\d+)(?!.*\d)", "", old_alias)
                else:
                    # Try to replace existing digits first
                    if re.search(r"\d", old_alias):
                        # Replace the last sequence of digits with the new index
                        new_alias = re.sub(r"(\d+)(?!.*\d)", str(human_friendly_index), old_alias)
                    else:
                        # No digits exist, insert before any trailing signs
                        match = re.search(r"([+-]+)$", old_alias)
                        if match:
                            # Has trailing signs (+ or -), insert index before them
                            # Example: T+ → T3+, A- → A3-
                            base = old_alias[: match.start()]
                            signs = match.group(1)
                            new_alias = f"{base}{human_friendly_index}{signs}"
                        else:
                            # No trailing signs, just append the index
                            # Example: T → T3, A → A3
                            new_alias = f"{old_alias}{human_friendly_index}"

                # Update the edge property if changed
                if new_alias != old_alias:
                    manager.disconnect(component)
                    manager.connect(component, properties={'alias': new_alias})
