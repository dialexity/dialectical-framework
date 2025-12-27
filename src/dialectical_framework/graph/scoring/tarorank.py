"""
TaroRank scoring algorithm for graph-native dialectical structures.

This module implements the dual-dimension scoring formula: Score = P × R^α
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, TYPE_CHECKING, Union

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.graph.nodes.estimation import (
    CalculatedProbabilityEstimation,
    CalculatedRelevanceEstimation
)
from dialectical_framework.graph.scoring.tarorank_calculators.base_calculator import BaseCalculator

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity

from dialectical_framework.enums.di import DI


class TaroRank:
    """
    TaroRank scoring algorithm for graph-native dialectical structures.

    This implementation follows the dual-dimension scoring formula:
    Score = P × R^α

    Where:
    - P (Probability): Structural feasibility
    - R (Relevance): Contextual/factual alignment
    - α (alpha): Global parameter controlling relevance influence (default: 1.0)

    Architecture:
    - Calculator pattern: Each node type has a dedicated calculator
    - Estimation nodes: All P/R values stored as Estimation nodes
    - Hierarchical aggregation: P and R flow upward through appropriate hierarchies
    - Audit-wins semantics: Rationale critiques override parent values

    Usage:
        scorer = TaroRank(alpha=1.0, default_transition_probability=None)
        scorer.score_node(wheel)  # Recursively scores entire structure

        # Access results
        wheel_score = wheel.score
        wheel_p = wheel.probability  # From Estimation nodes
        wheel_r = wheel.relevance    # From Estimation nodes
    """

    def __init__(
        self,
        alpha: float = 1.0,
        default_transition_probability: Optional[float] = None
    ):
        """
        Initialize TaroRank scorer.

        Args:
            alpha: Relevance exponent (≥0). Higher values emphasize relevance more.
                   - 0: Ignore R (Score = P only)
                   - 1: Balanced (Score = P × R, recommended)
                   - >1: Emphasize R (good R helps more, weak R hurts more)
            default_transition_probability: Default P for transitions without explicit values.
                   - None (default): No free lunch - transitions must provide P
                   - 1.0: Feasibility-only mode - Score ≈ R
        """
        if alpha < 0:
            raise ValueError(f"alpha must be ≥ 0, got {alpha}")

        self.alpha = alpha
        self.default_transition_probability = default_transition_probability

        # Import here to avoid circular imports
        from dialectical_framework.graph.estimation_manager import EstimationManager

        self.estimation_manager = EstimationManager()

        # Initialize calculators (lazy loading to avoid circular imports)
        self._calculators = {}

    def _get_calculator(self, node_type: str) -> BaseCalculator:
        """
        Get calculator for a node type (lazy loading).

        Args:
            node_type: Node class name (e.g., 'DialecticalComponent')

        Returns:
            Calculator instance for this node type

        Raises:
            ValueError: If no calculator exists for this node type
        """
        if node_type not in self._calculators:
            # Import calculators lazily to avoid circular imports
            from dialectical_framework.graph.scoring.tarorank_calculators.component_calculator import ComponentCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.transition_calculator import TransitionCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.rationale_calculator import RationaleCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.wisdom_unit_calculator import WisdomUnitCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.cycle_calculator import CycleCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.spiral_calculator import SpiralCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.transformation_calculator import TransformationCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.wheel_calculator import WheelCalculator

            calculator_map = {
                'DialecticalComponent': ComponentCalculator,
                'Transition': TransitionCalculator,
                'Rationale': RationaleCalculator,
                'WisdomUnit': WisdomUnitCalculator,
                'Cycle': CycleCalculator,
                'Spiral': SpiralCalculator,
                'Transformation': TransformationCalculator,
                'Wheel': WheelCalculator,
            }

            calculator_class = calculator_map.get(node_type)
            if not calculator_class:
                raise ValueError(f"No calculator for node type: {node_type}")

            self._calculators[node_type] = calculator_class(self)

        return self._calculators[node_type]

    def calculate_score(
        self,
        node: AssessableEntity
    ) -> Optional[float]:
        """
        Calculate and store score for a node.

        This method:
        1. Checks if score is valid (always skips if valid)
        2. Clears old calculated estimations (so properties return manual/child values)
        3. Recursively scores children
        4. Calculates node's P and R (using properties, which now reflect current state)
        5. Stores new calculated P and R
        6. Computes final Score = P × R^α
        7. Stores score in node.score field
        8. Returns the score

        With hierarchical invalidation propagation, we always skip valid nodes.
        If something needs rescoring, it will be marked invalid automatically.

        Args:
            node: AssessableEntity to score

        Returns:
            Computed score or None if insufficient data

        Example:
            scorer = TaroRank(alpha=1.0)
            score = scorer.score_node(wheel)
        """
        # Always skip valid nodes - invalidation propagation ensures correctness
        if node.is_score_valid():
            return node.score

        # Clear old calculated estimations BEFORE calculating
        # This ensures properties return manual values (or None) for this node
        # After scoring children, their properties will return fresh calculated values
        self.estimation_manager.clear_estimations(
            node,
            estimation_types=[CalculatedProbabilityEstimation, CalculatedRelevanceEstimation]
        )

        calculator = self._get_calculator(node.__class__.__name__)

        # Always score children recursively (they get fresh calculated values)
        calculator.score_children(node)

        # Calculate P and R (properties now return correct values)
        p = calculator.calculate_probability(node)
        r = calculator.calculate_relevance(node)

        # Store new calculated P and R (won't invalidate)
        self.estimation_manager.upsert_estimation(node, CalculatedProbabilityEstimation, p)
        self.estimation_manager.upsert_estimation(node, CalculatedRelevanceEstimation, r)

        # Calculate final score
        if p is None or r is None:
            node.score = None
            node.score_computed_at = None
            node.save()
            return None

        score = p * (r ** self.alpha)
        node.score = score
        node.score_computed_at = datetime.now()
        node.score_invalidated_at = None  # Clear invalidation flag
        node.save()

        return score

    def clear_scores(self, node: AssessableEntity) -> None:
        """
        Clear computed scores for a node and all its children.

        This clears:
        - Score fields (score, score_computed_at, score_invalidated_at)
        - Calculated estimation nodes (CalculatedProbabilityEstimation, CalculatedRelevanceEstimation)

        Manual estimations are PRESERVED (they're user/agent input, not algorithm output).

        Args:
            node: Node to clear scores for

        Example:
            scorer = TaroRank()
            scorer.clear_scores(wheel)
            scorer.score_node(wheel)  # Re-score using existing manual estimations
        """
        # Clear score fields
        node.score = None
        node.score_computed_at = None
        node.score_invalidated_at = None
        node.save()

        # Clear CALCULATED estimations (algorithm output), preserve manual estimations
        self.estimation_manager.clear_estimations(
            node,
            estimation_types=[CalculatedProbabilityEstimation, CalculatedRelevanceEstimation]
        )

        # Always clear children recursively
        calculator = self._get_calculator(node.__class__.__name__)
        calculator.clear_children(node)
