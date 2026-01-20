"""
Rationale node for the dialectical framework.

This module provides the Rationale class which represents explanations
and evidence for assessments in the dialectical system.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


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
    rating: Optional[float] = None  # Importance/quality rating (0.0-1.0), used for weighting critiques

    # Declarative relationships
    # What this rationale explains
    explanation: ClassVar[RelationshipManager[AssessableEntity]] = RelationshipTo(
        "AssessableEntity",
        "EXPLAINS",
        cardinality=(0, 1)  # Zero or one (rationale explains one entity)
    )

    # Incoming: rationales that critique this one (audit-wins semantics)
    # Usage: parent_rationale.critiques.connect(audit_rationale) creates audit_rationale -[CRITIQUES]-> parent_rationale
    critiques: ClassVar[RelationshipManager[Rationale]] = RelationshipFrom(
        "Rationale",
        "CRITIQUES",
        cardinality=(0, None)  # Zero or more critiques can target this rationale
    )

    # Inverse: the rationale this one critiques (outgoing edge)
    # A rationale can critique at most one other rationale
    _critiques_target: ClassVar[RelationshipManager[Rationale]] = RelationshipTo(
        "Rationale",
        "CRITIQUES",
        cardinality=(0, 1)  # Zero or one target (can critique at most one rationale)
    )

    derived_statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
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