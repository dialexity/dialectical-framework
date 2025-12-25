"""
Rationale node for the dialectical framework.

This module provides the Rationale class which represents explanations
and evidence for assessments in the dialectical system.
"""

from __future__ import annotations

from typing import ClassVar, Optional

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipManager


class Rationale(AssessableEntity):
    """
    Represents an explanation or evidence for an assessment.

    Rationales provide contextual explanations for why a particular
    assessment (score, relevance, probability) was assigned to an
    assessable entity (Component, WisdomUnit, Cycle, Wheel, etc.).

    Rationales can have multiple text formats:
    - text: Full detailed explanation (required)
    - headline: Short title/summary
    - haiku: Poetic 3-line summary
    - summary: Medium-length summary

    Key points/theses are represented as separate DialecticalComponent nodes
    connected via the HAS_STATEMENT relationship (derived_statements field).

    Rationales follow "auditor-wins semantics":
    - Child rationales override parent assessments
    - Zero values don't veto parent (soft exclusion)
    - Rationales can critique other rationales (recursive)

    Example:
        Component("Democracy") -[EXPLAINS]<- Rationale("Because it empowers citizens...")
    """

    text: str
    headline: Optional[str] = None
    haiku: Optional[str] = None
    summary: Optional[str] = None

    # Declarative relationships
    # What this rationale explains
    explanation: ClassVar[RelationshipManager] = RelationshipTo(
        "AssessableEntity",
        "EXPLAINS",
        cardinality=(0, 1)  # Zero or one (rationale explains one entity)
    )

    # Rationales can critique other rationales (recursive critique)
    critiques: ClassVar[RelationshipManager] = RelationshipTo(
        "Rationale",
        "CRITIQUES",
        cardinality=(0, 1)  # Zero or one (rationale may critique another rationale)
    )

    derived_statements: ClassVar[RelationshipManager] = RelationshipTo(
        "DialecticalComponent",
        "HAS_STATEMENT",
        cardinality=(0, None)
    )

    def __repr__(self) -> str:
        """String representation of the rationale."""
        text_preview = self.text[:47] + "..." if len(self.text) > 50 else self.text
        return f"Rationale(uid={self.uid}, text='{text_preview}')"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.headline if self.headline else self.text

    def decompose_into_statements(self, statements: list):
        """
        Decompose this rationale into atomic statements for dialectical analysis.

        A single rationale often contains multiple claims that can be analyzed
        separately. This method allows extracting those atomic statements.

        Args:
            statements: List of DialecticalComponent instances representing atomic statements

        Example:
            rationale = Rationale(
                text="Democracy is important because it empowers citizens and promotes equality"
            )

            # Decompose into atomic statements
            statement1 = DialecticalComponent(statement="Democracy empowers citizens")
            statement2 = DialecticalComponent(statement="Democracy promotes equality")
            rationale.decompose_into_statements([statement1, statement2])

            # Now these can participate in dialectical analysis
            wu.t_plus_components.connect(statement1)
            wu.t_plus_components.connect(statement2)
        """
        for statement in statements:
            self.derived_statements.connect(statement)  # Uses injected graph_db internally

    def get_statements(self) -> list:
        """
        Get all statements this rationale has been decomposed into.

        Returns:
            List of DialecticalComponent nodes
        """
        return [comp for comp, _ in self.derived_statements.all()]  # Uses injected graph_db internally
