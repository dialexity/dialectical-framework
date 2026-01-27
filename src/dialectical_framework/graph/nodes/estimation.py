"""
Estimation nodes for the dialectical framework.

This module provides the Estimation class and its subclasses which represent
quantitative measurements associated with assessable entities.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.has_estimation_relationship import (
    HasEstimationRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity

class Estimation(BaseNode, label="Estimation"):
    """
    Base class for estimations associated with assessable entities.

    Estimations capture quantitative measurements like probability, relevance,
    feasibility, and cost. They are stored as separate nodes connected to
    assessable entities via HAS_ESTIMATION relationships.

    The scoring architecture uses two primary dimensions:
    - Probability (P): Likelihood of truth/occurrence
    - Relevance (R): Importance/significance

    Formula: Score = P × R^α

    Additional estimations like feasibility and cost can be used for
    specialized analysis and filtering.
    """

    value: float

    # Declarative relationships
    assessed_entity: ClassVar[RelationshipManager[AssessableEntity]] = RelationshipFrom(
        "AssessableEntity",
        model=HasEstimationRelationship,
        cardinality=(1, 1)  # Exactly one assessable entity
    )

    def __repr__(self) -> str:
        """String representation of the estimation."""
        return f"{self.__class__.__name__}(uid={self.uid}, value={self.value})"


class ProbabilityEstimation(Estimation, label="Probability"):
    """
    Probability estimation (P dimension in scoring formula).

    Represents the likelihood that a component/assessment is true or
    will occur. Values typically range from 0.0 (impossible) to 1.0 (certain).

    This is a MANUAL estimation - set by users or agents.
    """

    pass


class RelevanceEstimation(Estimation, label="Relevance"):
    """
    Relevance estimation (R dimension in scoring formula).

    Represents the importance or significance of a component/assessment.
    Values typically range from 0.0 (irrelevant) to 1.0 (highly relevant).

    This is a MANUAL estimation - set by users or agents.
    """

    pass


class CalculatedProbabilityEstimation(Estimation, label="CalculatedProbability"):
    """
    Calculated probability from TaroRank aggregation.

    This is TaroRank's output, representing the aggregated probability
    from all manual estimations and rationales.

    Typically there is at most one calculated estimation per node.
    """

    pass


class CalculatedRelevanceEstimation(Estimation, label="CalculatedRelevance"):
    """
    Calculated relevance from TaroRank aggregation.

    This is TaroRank's output, representing the aggregated relevance
    from all manual estimations and rationales.

    Typically there is at most one calculated estimation per node.
    """

    pass


class FeasibilityEstimation(Estimation, label="Feasibility"):
    """
    Feasibility estimation for practical constraints.

    Represents how achievable or practical an outcome is.
    Values typically range from 0.0 (infeasible) to 1.0 (easily achievable).

    **TaroRank Semantics**:
    FeasibilityEstimation is treated semantically the same as RelevanceEstimation.

    Priority order for relevance calculation:
    1. CalculatedRelevanceEstimation (TaroRank output)
    2. RelevanceEstimation (manual)
    3. FeasibilityEstimation (manual fallback)

    When both RelevanceEstimation and FeasibilityEstimation exist on the same node,
    RelevanceEstimation takes priority for relevance calculation, and FeasibilityEstimation
    becomes additional metadata.

    Example:
        # FeasibilityEstimation used as relevance
        rationale.estimations.connect(FeasibilityEstimation(value=0.7))
        rel = rationale.relevance  # Returns 0.7

        # RelevanceEstimation takes priority
        rationale.estimations.connect(RelevanceEstimation(value=0.9))
        rel = rationale.relevance  # Returns 0.9 (FeasibilityEstimation ignored)
    """

    pass