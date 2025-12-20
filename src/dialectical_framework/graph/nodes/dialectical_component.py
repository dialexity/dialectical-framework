"""
DialecticalComponent node with declarative relationships.

This version uses the RelationshipManager layer for clean, neomodel-like syntax.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.opposition_relationship import (
    OppositionRelationship,
)


class DialecticalComponent(AssessableEntity):
    """
    Represents an atomic dialectical statement or concept.

    Components are the building blocks of the dialectical framework.
    They can play different roles in different WisdomUnits:
    - T (neutral thesis), T+ (positive thesis), T- (negative thesis)
    - A (neutral antithesis), A+ (positive antithesis), A- (negative antithesis)
    - S+ (positive synthesis), S- (negative synthesis)

    Components are connected TO WisdomUnits from the WisdomUnit side using
    typed relationships (T, T_PLUS, T_MINUS, A, A_PLUS, A_MINUS, S_PLUS, S_MINUS).

    The full alias (e.g., "T1+", "A2-") is computed from:
    - Relationship type (T_PLUS, A_MINUS, etc.)
    - WisdomUnit.index property
    """

    statement: str

    oppositions: ClassVar[RelationshipManager] = RelationshipTo(
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

    def get_wisdom_units(self, db=None) -> list[tuple[Any, str]]:
        """
        Get all WisdomUnits this component belongs to with their relationship types.

        Args:
            db: Database connection (uses get_db() if not provided)

        Returns:
            List of tuples: (WisdomUnit, relationship_type)
            Example: [(wu1, "T"), (wu2, "T_PLUS")]
        """
        if self._id is None:
            return []

        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

        # Query all typed relationships to WisdomUnits
        query = """
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS', 'S_PLUS', 'S_MINUS']
        RETURN wu, type(r) as rel_type
        """

        results = db.execute_and_fetch(query, {"component_id": self._id})
        return [(result["wu"], result["rel_type"]) for result in results]

    def get_wisdom_units_with_aliases(self, db=None) -> list[tuple[Any, str]]:
        """
        Get all WisdomUnits with computed full aliases.

        Args:
            db: Database connection (uses get_db() if not provided)

        Returns:
            List of tuples: (WisdomUnit, full_alias)
            Example: [(wu1, "T1"), (wu2, "T2+")]
        """
        result = []
        wisdom_units = self.get_wisdom_units(db)

        for wu, rel_type in wisdom_units:
            alias = wu.get_component_alias(rel_type)
            result.append((wu, alias))

        return result
