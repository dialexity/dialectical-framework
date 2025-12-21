"""
WisdomUnit with declarative relationships and cardinality constraints.

This version uses the enhanced RelationshipManager with cardinality support
for automatic validation and enforcement.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager


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
    index: Optional[int] = None  # Position in the Wheel (0 = no number in alias)

    # Declarative relationships with cardinality constraints
    # Note: Direction is "incoming" because components point TO wisdom units
    # Each position uses a distinct relationship type for proper cardinality tracking

    # T-side (exactly one neutral thesis)
    t: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "T",
        cardinality=(1, 1)  # Exactly one
    )

    # T+ side (one or more positive thesis)
    t_plus: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "T_PLUS",
        cardinality=(1, None)  # One or more
    )

    # T- side (one or more negative thesis)
    t_minus: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "T_MINUS",
        cardinality=(1, None)  # One or more
    )

    # A-side (exactly one neutral antithesis)
    a: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "A",
        cardinality=(1, 1)  # Exactly one
    )

    # A+ side (one or more positive antithesis)
    a_plus: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "A_PLUS",
        cardinality=(1, None)  # One or more
    )

    # A- side (one or more negative antithesis)
    a_minus: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "A_MINUS",
        cardinality=(1, None)  # One or more
    )

    # S+ side (zero or more positive synthesis)
    s_plus: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "S_PLUS",
        cardinality=(0, None)  # Zero or more
    )

    # S- side (zero or more negative synthesis)
    s_minus: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "S_MINUS",
        cardinality=(0, None)  # Zero or more
    )

    # Relationship to Wheel
    wheel: ClassVar[RelationshipManager] = RelationshipTo(
        "Wheel",
        "BELONGS_TO_WHEEL",
        cardinality=(0, 1)  # Zero or one wheel
    )

    # Internal transformation spiral (T- → A+, A- → T+)
    transformation: ClassVar[RelationshipManager] = RelationshipFrom(
        "Transformation",
        "IS_SPIRAL_OF",
        cardinality=(0, 1)  # Zero or one internal transformation spiral
    )

    # Note: Transformation.ac_re points to action-reflection WisdomUnit
    # To find transformations referencing this WU, query via Transformation.ac_re

    def __repr__(self) -> str:
        """String representation of the wisdom unit."""
        return f"WisdomUnit(uid={self.uid}, index={self.index}, reasoning_mode={self.reasoning_mode})"

    @staticmethod
    def _rel_type_to_alias_base(rel_type: str) -> str:
        """Convert relationship type to alias base (without index)."""
        mapping = {
            "T": "T",
            "T_PLUS": "T+",
            "T_MINUS": "T-",
            "A": "A",
            "A_PLUS": "A+",
            "A_MINUS": "A-",
            "S_PLUS": "S+",
            "S_MINUS": "S-",
        }
        return mapping.get(rel_type, rel_type)

    def get_component_alias(self, rel_type: str) -> str:
        """
        Get the full alias for a component at this position.

        Args:
            rel_type: Relationship type (T, T_PLUS, T_MINUS, A, A_PLUS, etc.)

        Returns:
            Full alias (e.g., "T1+", "A2-", or "T+" if index=0)
        """
        base = self._rel_type_to_alias_base(rel_type)

        if self.index is None or self.index == 0:
            return base
        else:
            # Insert index after first character (before +/-)
            if len(base) == 1:  # "T" or "A"
                return f"{base}{self.index}"
            else:  # "T+", "T-", etc.
                return f"{base[0]}{self.index}{base[1:]}"

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

    def get_all_components_with_aliases(self) -> list[tuple[Any, str]]:
        """
        Get all components with their computed aliases.

        Uses dependency injection to get the database connection.

        Returns:
            List of tuples: (component_node, full_alias)
            Examples: [(comp1, "T1"), (comp2, "T1+"), (comp3, "A2-")]
        """
        result = []

        # Map relationship managers to their types
        rel_managers = [
            (self.t, "T"),
            (self.t_plus, "T_PLUS"),
            (self.t_minus, "T_MINUS"),
            (self.a, "A"),
            (self.a_plus, "A_PLUS"),
            (self.a_minus, "A_MINUS"),
            (self.s_plus, "S_PLUS"),
            (self.s_minus, "S_MINUS"),
        ]

        for manager, rel_type in rel_managers:
            components = manager.all()  # No db parameter, uses DI
            alias = self.get_component_alias(rel_type)

            for component, _props in components:
                result.append((component, alias))

        return result
