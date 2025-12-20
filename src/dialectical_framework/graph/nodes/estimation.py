"""
Estimation nodes for the dialectical framework.

This module provides the Estimation class and its subclasses which represent
quantitative measurements associated with assessable entities.
"""

from __future__ import annotations

from typing import ClassVar

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager


class Estimation(BaseNode):
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
    assessed_entity: ClassVar[RelationshipManager] = RelationshipFrom(
        "AssessableEntity",
        "HAS_ESTIMATION",
        cardinality=(1, 1)  # Exactly one assessable entity
    )

    def __repr__(self) -> str:
        """String representation of the estimation."""
        return f"{self.__class__.__name__}(uid={self.uid}, value={self.value})"


class ProbabilityEstimation(Estimation):
    """
    Probability estimation (P dimension in scoring formula).

    Represents the likelihood that a component/assessment is true or
    will occur. Values typically range from 0.0 (impossible) to 1.0 (certain).
    """

    pass


class RelevanceEstimation(Estimation):
    """
    Relevance estimation (R dimension in scoring formula).

    Represents the importance or significance of a component/assessment.
    Values typically range from 0.0 (irrelevant) to 1.0 (highly relevant).
    """

    pass


class FeasibilityEstimation(Estimation):
    """
    Feasibility estimation for practical constraints.

    Represents how achievable or practical an outcome is.
    Values typically range from 0.0 (infeasible) to 1.0 (easily achievable).
    """

    pass


class CostEstimation(Estimation):
    """
    Cost estimation for resource requirements.

    Represents the resource cost (time, money, effort) associated with
    an action or outcome. Values can be absolute costs or normalized
    from 0.0 (no cost) to 1.0 (maximum cost).
    """

    pass
