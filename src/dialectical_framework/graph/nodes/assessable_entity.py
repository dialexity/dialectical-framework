"""
Assessable entity class for scored entities in the dialectical framework.

This module provides the AssessableEntity class which serves as the base for all
nodes that can be assessed/scored (Components, WisdomUnits, Wheels, Cycles, etc.).
"""

from __future__ import annotations

from typing import ClassVar, Optional

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager


class AssessableEntity(BaseNode):
    """
    Base class for all assessable (scoreable) entities in the dialectical graph.

    Assessable nodes can have:
    - A score (computed by external TaroRank algorithm)
    - Rationales (explanations for assessments)
    - Estimations (probability, relevance, feasibility, cost)

    The scoring architecture follows the formula: Score = P × R^α
    where P is probability and R is relevance.
    """

    score: Optional[float] = None

    # Declarative relationships
    # Rationales explain this assessable entity
    rationales: ClassVar[RelationshipManager] = RelationshipFrom(
        "Rationale",
        "EXPLAINS",
        cardinality=(0, None)  # Zero or more rationales
    )

    # Estimations for this assessable entity
    estimations: ClassVar[RelationshipManager] = RelationshipTo(
        "Estimation",
        "HAS_ESTIMATION",
        cardinality=(0, None)  # Zero or more estimations
    )

    def __repr__(self) -> str:
        """String representation of the assessable entity."""
        score_str = f"{self.score:.3f}" if self.score is not None else "None"
        return f"{self.__class__.__name__}(uid={self.uid}, score={score_str})"
