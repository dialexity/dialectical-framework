"""
DialecticalComponent node with declarative relationships.

This version uses the RelationshipManager layer for clean, neomodel-like syntax.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.opposition_relationship import (
    OppositionRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.transition import Transition


class DialecticalComponent(AssessableEntity):
    """
    Represents an atomic dialectical statement or concept.

    Components are the building blocks of the dialectical framework.
    They can play different roles in different WisdomUnits:
    - T (neutral thesis), T+ (positive thesis), T- (negative thesis)
    - A (neutral antithesis), A+ (positive antithesis), A- (negative antithesis)
    - S+ (positive synthesis), S- (negative synthesis)

    Components are connected TO WisdomUnits via PolarityRelationship, which stores
    the contextual alias (e.g., "T1+", "A2-") on the relationship edge.
    This allows the same component to have different positions in different wheels.
    """

    statement: str

    oppositions: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        model=OppositionRelationship,
        cardinality=(1, None)
    )

    source_of: ClassVar[RelationshipManager[Transition]] = RelationshipTo("Transition", "IS_SOURCE_OF")
    target_of: ClassVar[RelationshipManager[Transition]] = RelationshipFrom("Transition", "IS_TARGET_OF")

    def __repr__(self) -> str:
        """String representation of the component."""
        statement_preview = (
            self.statement[:47] + "..." if len(self.statement) > 50 else self.statement
        )
        return f"DialecticalComponent(uid={self.uid}, statement='{statement_preview}')"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.statement

    def get_alias(self, wisdom_unit: WisdomUnit) -> Optional[str]:
        """
        Get the alias of this component within a specific WisdomUnit's context.

        This method searches all relationship managers on the WisdomUnit to find
        where this component is connected and returns the alias from the edge properties.

        Args:
            wisdom_unit: The WisdomUnit to look up the alias in

        Returns:
            The alias string (e.g., "T", "T+", "A-") or None if not connected

        Example:
            comp = DialecticalComponent(statement="Democracy")
            wu = WisdomUnit(...)
            wu.t.connect(comp, properties={'alias': 'T1'})

            alias = comp.get_alias(wu)  # Returns "T1"
        """
        # Search through all relationship managers on the wisdom unit
        rel_managers = [
            wisdom_unit.t,
            wisdom_unit.t_plus,
            wisdom_unit.t_minus,
            wisdom_unit.a,
            wisdom_unit.a_plus,
            wisdom_unit.a_minus,
            wisdom_unit.s_plus,
            wisdom_unit.s_minus,
        ]

        for manager in rel_managers:
            components = manager.all()  # Returns [(node, props)]

            for comp, props in components:
                # Check if this is the component we're looking for
                if comp.uid == self.uid:
                    return props.get('alias')

        return None
