"""
Assessable entity class for entities with estimations and rationales.

This module provides the AssessableEntity class which serves as the base for all
nodes that can have domain estimations and rationales attached.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.explains_relationship import (
    ExplainsRelationship,
)
from dialectical_framework.graph.relationships.estimates_relationship import (
    EstimatesRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.estimation import Estimation
    from dialectical_framework.graph.nodes.rationale import Rationale


class AssessableEntity(BaseNode, label="Assessable"):
    """
    Base class for entities that can have estimations and rationales attached.

    Assessable nodes can have:
    - Rationales (explanations for assessments)
    - Estimations (probability, relevance, feasibility, mode, arousal, etc.)

    Quality is measured by structural edge properties (heuristic_similarity,
    complementarity_t/a, insight, proactiveness) and computed node properties
    (diff_t, diff_a, area_normalized, rectangularity on Perspective).
    """

    # Declarative relationships
    # Rationales explain this assessable entity
    rationales: ClassVar[RelationshipManager[Rationale]] = RelationshipFrom(
        "Rationale",
        model=ExplainsRelationship,
        cardinality=(0, None)  # Zero or more rationales
    )

    # Estimations for this assessable entity (Estimation points TO this entity)
    estimations: ClassVar[RelationshipManager[Estimation]] = RelationshipFrom(
        "Estimation",
        model=EstimatesRelationship,
        cardinality=(0, None)  # Zero or more estimations
    )

    @property
    def best_rationale(self) -> Optional[Rationale]:
        """
        Get the highest-rated rationale explaining this entity.

        Rationales are ranked by their rating field (0.0-1.0). If no rationales have
        ratings, returns the first rationale. If no rationales exist, returns None.

        Returns:
            Rationale with highest rating, or first rationale, or None
        """

        rationales_with_props = self.rationales.all()
        if not rationales_with_props:
            return None

        rationales = [rat for rat, _ in rationales_with_props]

        # Get rationales with ratings
        rated_rationales = [r for r in rationales if r.rating is not None]

        if rated_rationales:
            # Return rationale with highest rating
            return max(rated_rationales, key=lambda r: r.rating)

        # Fallback: return first rationale if none have ratings
        return rationales[0] if rationales else None

    def __repr__(self) -> str:
        """String representation of the assessable entity."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"{self.__class__.__name__}({hash_str})"
