"""
DialecticalComponent node with declarative relationships.

This version uses the RelationshipManager layer for clean, neomodel-like syntax.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.opposition_relationship import (
    OppositionRelationship,
)
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


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

    source_of: ClassVar[RelationshipManager] = RelationshipTo("Transition", "IS_SOURCE_OF")
    target_of: ClassVar[RelationshipManager] = RelationshipFrom("Transition", "IS_TARGET_OF")

    def __repr__(self) -> str:
        """String representation of the component."""
        statement_preview = (
            self.statement[:47] + "..." if len(self.statement) > 50 else self.statement
        )
        return f"DialecticalComponent(uid={self.uid}, statement='{statement_preview}')"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.statement

    @inject
    def get_wisdom_units(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[Any, str]]:
        """
        Get all WisdomUnits this component belongs to with their relationship types.

        Args:
            graph_db: Database connection (injected via DI)

        Returns:
            List of tuples: (WisdomUnit, relationship_type)
            Example: [(wu1, "T"), (wu2, "T_PLUS")]
        """
        if self._id is None:
            return []

        # Query all typed relationships to WisdomUnits
        query = """
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS', 'S_PLUS', 'S_MINUS']
        RETURN wu, type(r) as rel_type
        """

        results = graph_db.execute_and_fetch(query, {"component_id": self._id})
        return [(result["wu"], result["rel_type"]) for result in results]

    def get_wisdom_units_with_aliases(self) -> list[tuple[Any, str]]:
        """
        Get all WisdomUnits with computed full aliases.

        Returns:
            List of tuples: (WisdomUnit, full_alias)
            Example: [(wu1, "T1"), (wu2, "T2+")]
        """
        result = []
        wisdom_units = self.get_wisdom_units()  # Uses injected graph_db internally

        for wu, rel_type in wisdom_units:
            alias = wu.get_component_alias(rel_type)
            result.append((wu, alias))

        return result

    def get_alias(self, wisdom_unit: WisdomUnit) -> Optional[str]:
        """
        Get the alias of this component within a specific WisdomUnit's context.

        This method finds the polarity relationship connecting this component
        to the given WisdomUnit and returns the alias stored on that edge.

        Args:
            wisdom_unit: The WisdomUnit to look up the alias in

        Returns:
            The alias string (e.g., "T", "T+", "A-") or None if not connected

        Example:
            comp = DialecticalComponent(statement="Democracy")
            wu = WisdomUnit(...)
            wu.t.connect(comp, properties={'alias': 'T1'})

            alias = comp.get_alias(wu)  # Returns "T1"

        Note:
            This delegates to WisdomUnit.get_component_alias() which searches
            all polarity relationships (t, t_plus, t_minus, a, a_plus, a_minus,
            s_plus, s_minus) for the relationship edge properties.
        """
        return wisdom_unit.get_component_alias(self)
