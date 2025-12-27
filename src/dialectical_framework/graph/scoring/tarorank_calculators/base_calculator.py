"""
Abstract base class for node-specific scoring calculators.

Each calculator implements the TaroRank scoring logic for one node type.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar, TYPE_CHECKING

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
    from dialectical_framework.graph.nodes.estimation import Estimation
    from dialectical_framework.graph.scoring.tarorank import TaroRank

T = TypeVar('T', bound='Estimation')


class BaseCalculator(ABC):
    """
    Abstract base class for node-specific scoring calculators.

    Each calculator implements the logic for one node type,
    following the TaroRank scoring algorithm.

    Responsibilities:
    - Calculate probability (P) for this node type
    - Calculate relevance (R) for this node type
    - Score children nodes (if composite)
    - Clear children scores (for re-scoring)
    """

    def __init__(self, scorer: TaroRank):
        """
        Initialize calculator with reference to main scorer.

        Args:
            scorer: TaroRank instance (provides access to alpha,
                   default_transition_probability, other calculators)
        """
        self.scorer = scorer

    @abstractmethod
    def calculate_probability(self, node: AssessableEntity) -> Optional[float]:
        """
        Calculate probability (P) for this node.

        Args:
            node: AssessableEntity to calculate P for

        Returns:
            P value (0.0-1.0) or None if insufficient data
        """
        ...

    @abstractmethod
    def calculate_relevance(self, node: AssessableEntity) -> Optional[float]:
        """
        Calculate relevance (R) for this node.

        Args:
            node: AssessableEntity to calculate R for

        Returns:
            R value (0.0-1.0) or None if insufficient data
        """
        ...

    def score_children(self, node: AssessableEntity, skip_valid: bool = True) -> None:
        """
        Recursively score all children nodes.

        Override in composite calculators (WisdomUnit, Cycle, Wheel).
        Leaf calculators (Component, Transition) do nothing here.

        Args:
            node: Parent node whose children should be scored
            skip_valid: If True, skip scoring children with valid scores (default)
        """
        pass

    def clear_children(self, node: AssessableEntity) -> None:
        """
        Recursively clear scores from children nodes.

        Override in composite calculators.

        Args:
            node: Parent node whose children should be cleared
        """
        pass

    def _get_manual_estimations(self, node: AssessableEntity, estimation_type: Type[T]) -> list[T]:
        """
        Get only MANUAL estimations (ProbabilityEstimation or RelevanceEstimation).

        Does NOT include calculated estimations (CalculatedProbabilityEstimation, etc.)
        to avoid circular dependencies during scoring.

        This ensures calculators read ONLY manual values as input, matching legacy behavior where
        calculate_probability() reads manual_probability (not self.probability which includes calculated).

        Args:
            node: AssessableEntity to get estimations from
            estimation_type: Type of estimation (ProbabilityEstimation or RelevanceEstimation)

        Returns:
            List of manual estimation nodes of the specified type

        Example:
            from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation

            manual_probs = self._get_manual_estimations(component, ProbabilityEstimation)
            values = [est.value for est in manual_probs]
        """
        estimations = node.estimations.all()
        return [
            est for est, _ in estimations
            if isinstance(est, estimation_type)
        ]
