"""
Transition node for the dialectical framework.

This module provides the Transition class which represents relationships
between dialectical components (causal, convergence, transformation).
"""

from __future__ import annotations

from typing import ClassVar, Optional

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager


class Transition(AssessableEntity):
    """
    Represents a transition (relationship) between dialectical components.

    Transitions capture different types of relationships between components:
    - CAUSES: Causal relationship (A causes B)
    - CONSTRUCTIVELY_CONVERGES_TO: Synthesis convergence (A + B → S)
    - TRANSFORMS_TO: Dialectical transformation

    Transitions are nodes (not edges) in the graph because they:
    1. Can be assessed/scored
    2. Have their own rationales
    3. Can have estimations (probability of transition)
    4. Are organized into Cycles and Spirals
    """

    default_transition_probability: Optional[float] = None

    source: ClassVar[RelationshipManager] = RelationshipFrom(
        "DialecticalComponent",
        "IS_SOURCE_OF",
        cardinality=(1, 1)
    )

    target: ClassVar[RelationshipManager] = RelationshipTo(
        "DialecticalComponent",
        "IS_TARGET_OF",
        cardinality=(1, 1)
    )

    cycle: ClassVar[RelationshipManager] = RelationshipTo(
        ("Cycle", "Spiral"),
        "BELONGS_TO_CYCLE",
        cardinality=(0, 1)
    )

    derived_statements: ClassVar[RelationshipManager] = RelationshipTo(
        "DialecticalComponent",
        "HAS_STATEMENT",
        cardinality=(0, None)
    )

    def __repr__(self) -> str:
        """String representation of the transition."""
        prob_str = (
            f"{self.default_transition_probability:.3f}"
            if self.default_transition_probability is not None
            else "None"
        )
        return f"Transition(uid={self.uid}, probability={prob_str})"

    def decompose_into_statements(self, statements: list, db=None):
        """
        Decompose this transition into atomic statements for meta-dialectical analysis.

        This enables recursive dialectics: a transition from one wheel can become
        a statement in a meta-wheel.

        Args:
            statements: List of DialecticalComponent instances representing atomic statements
            db: Database connection (uses get_db() if not provided)

        Example:
            # Wheel 1: T1, T2, T3
            transition = Transition()  # T2- → T3+

            # Decompose into statement for Wheel 2
            statement_4 = DialecticalComponent(statement="T2- causes T3+")
            transition.decompose_into_statements([statement_4], db)

            # Wheel 2: T1, T2, T3, T4 (where T4 comes from transition)
            wu4 = WisdomUnit(index=4)
            wu4.t_components.connect(statement_4, db)
        """
        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

        for statement in statements:
            self.derived_statements.connect(statement, db=db)

    def get_statements(self, db=None) -> list:
        """
        Get all statements this transition has been decomposed into.

        Returns:
            List of DialecticalComponent nodes
        """
        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

        return [comp for comp, _ in self.derived_statements.all(db)]
