"""
WisdomUnit with declarative relationships and cardinality constraints.

This version uses the enhanced RelationshipManager with cardinality support
for automatic validation and enforcement.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.polarity_relationship import (
    TRelationship,
    TPlusRelationship,
    TMinusRelationship,
    ARelationship,
    APlusRelationship,
    AMinusRelationship,
    SPlusRelationship,
    SMinusRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment


class WisdomUnit(AssessableEntity):
    """
    Represents a complete dialectical structure with enforced cardinality.

    A WisdomUnit contains:
    - Thesis side (T-side): 1 T, 1+ T+, 1+ T-
    - Antithesis side (A-side): 1 A, 1+ A+, 1+ A-
    - Optional synthesis: 0+ S+, 0+ S-

    The cardinality constraints are now enforced at the RelationshipManager level,
    providing automatic validation and runtime checks.
    """

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

    # T+ side (one or more positive thesis)
    t_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TPlusRelationship,
        cardinality=(1, None)  # One or more
    )

    # T- side (one or more negative thesis)
    t_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TMinusRelationship,
        cardinality=(1, None)  # One or more
    )

    # A-side (exactly one neutral antithesis)
    a: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=ARelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A+ side (one or more positive antithesis)
    a_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=APlusRelationship,
        cardinality=(1, None)  # One or more
    )

    # A- side (one or more negative antithesis)
    a_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=AMinusRelationship,
        cardinality=(1, None)  # One or more
    )

    # S+ side (zero or more positive synthesis)
    s_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=SPlusRelationship,
        cardinality=(0, None)  # Zero or more
    )

    # S- side (zero or more negative synthesis)
    s_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=SMinusRelationship,
        cardinality=(0, None)  # Zero or more
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

    def validate_cardinality(self) -> tuple[bool, list[str]]:
        """
        Validate all relationship cardinality constraints.

        This method checks that all relationships satisfy their declared
        cardinality constraints using dependency injection.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # List of all relationship managers to validate
        relationships = [
            ('T components', self.t),
            ('T+ components', self.t_plus),
            ('T- components', self.t_minus),
            ('A components', self.a),
            ('A+ components', self.a_plus),
            ('A- components', self.a_minus),
            ('S+ components', self.s_plus),
            ('S- components', self.s_minus),
        ]

        for name, rel_manager in relationships:
            is_valid, error = rel_manager.validate_cardinality()  # No db parameter, uses DI
            if not is_valid:
                errors.append(f"{name}: {error}")

        return (len(errors) == 0, errors)

    def is_complete(self) -> bool:
        """
        Check if this wisdom unit has all required components.

        Uses dependency injection to get the database connection.

        Returns:
            True if all cardinality constraints are satisfied
        """
        is_valid, _ = self.validate_cardinality()  # No db parameter, uses DI
        return is_valid

    def get_component_summary(self) -> dict:
        """
        Get a summary of all component counts.

        Uses dependency injection to get the database connection.

        Returns:
            Dict with component type as key and count as value
        """
        return {
            't': self.t.count(),
            't_plus': self.t_plus.count(),
            't_minus': self.t_minus.count(),
            'a': self.a.count(),
            'a_plus': self.a_plus.count(),
            'a_minus': self.a_minus.count(),
            's_plus': self.s_plus.count(),
            's_minus': self.s_minus.count(),
        }

    def get_component_alias(self, component: DialecticalComponent) -> Optional[str]:
        """
        Get the alias of a specific component within this wisdom unit's context.

        Args:
            component: The DialecticalComponent to look up

        Returns:
            The alias string (e.g., "T", "T+", "A-") or None if component not found

        Example:
            wu = WisdomUnit(...)
            comp = DialecticalComponent(statement="Democracy")
            wu.t.connect(comp, properties={'alias': 'T1'})
            alias = wu.get_component_alias(comp)  # Returns "T1"
        """
        # Search through all relationship managers
        rel_managers = [
            self.t,
            self.t_plus,
            self.t_minus,
            self.a,
            self.a_plus,
            self.a_minus,
            self.s_plus,
            self.s_minus,
        ]

        for manager in rel_managers:
            components = manager.all()  # Returns [(node, props)]

            for comp, props in components:
                # Check if this is the component we're looking for
                if comp.uid == component.uid:
                    return props.get('alias')

        return None

    def get_all_components_with_aliases(self) -> list[tuple[Any, str]]:
        """
        Get all components with their aliases from relationship properties.

        Uses dependency injection to get the database connection.

        Returns:
            List of tuples: (component_node, alias_from_relationship)
            Examples: [(comp1, "T1"), (comp2, "T1+"), (comp3, "A2-")]
        """
        result = []

        # Map relationship managers
        rel_managers = [
            self.t,
            self.t_plus,
            self.t_minus,
            self.a,
            self.a_plus,
            self.a_minus,
            self.s_plus,
            self.s_minus,
        ]

        for manager in rel_managers:
            components = manager.all()  # Returns [(node, props)]

            for component, props in components:
                # Alias is stored in the relationship properties
                alias = props.get('alias', '?')
                result.append((component, alias))

        return result

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
