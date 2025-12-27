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

    def _get_calculator(self, node_type: str):
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

    def score_node(
        self,
        node: AssessableEntity,
        recursive: bool = True,
        skip_valid: bool = True
    ) -> Optional[float]:
        """
        Calculate and store score for a node.

        This method:
        1. Checks if score is valid (if skip_valid=True)
        2. Recursively scores children (if recursive=True)
        3. Calculates node's P and R
        4. Creates/updates Estimation nodes for P and R
        5. Computes final Score = P × R^α
        6. Stores score in node.score field
        7. Returns the score

        Args:
            node: AssessableEntity to score
            recursive: If True, scores all children first (default)
            skip_valid: If True, skip scoring if node.is_score_valid() (default)
                       Set to False to force recalculation

        Returns:
            Computed score or None if insufficient data

        Example:
            scorer = TaroRank(alpha=1.0)
            score = scorer.score_node(wheel, recursive=True)  # Skips if valid
            score = scorer.score_node(wheel, skip_valid=False)  # Forces recalc
        """
        # Check validity first
        if skip_valid and node.is_score_valid():
            return node.score

        calculator = self._get_calculator(node.__class__.__name__)

        # Recursive scoring of children
        if recursive:
            calculator.score_children(node, skip_valid=skip_valid)

        # Calculate P and R
        p = calculator.calculate_probability(node)
        r = calculator.calculate_relevance(node)

        # Store P and R as CALCULATED estimation nodes (don't invalidate during scoring)
        # This preserves manual estimations - calculated types are separate from manual types
        self.estimation_manager.upsert_estimation(node, CalculatedProbabilityEstimation, p, invalidate=False)
        self.estimation_manager.upsert_estimation(node, CalculatedRelevanceEstimation, r, invalidate=False)

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

    def clear_scores(self, node: AssessableEntity, recursive: bool = True) -> None:
        """
        Clear computed scores for a node.

        This clears:
        - Score fields (score, score_computed_at, score_invalidated_at)
        - Calculated estimation nodes (CalculatedProbabilityEstimation, CalculatedRelevanceEstimation)

        Manual estimations are PRESERVED (they're user/agent input, not algorithm output).

        Args:
            node: Node to clear scores for
            recursive: If True, clears children scores too

        Example:
            scorer = TaroRank()
            scorer.clear_scores(wheel, recursive=True)
            scorer.score_node(wheel, recursive=True)  # Re-score using existing manual estimations
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

        if recursive:
            calculator = self._get_calculator(node.__class__.__name__)
            calculator.clear_children(node)

    @inject
    def score_all_wheels(
        self,
        recursive: bool = True,
        skip_valid: bool = True,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> dict[str, float | int]:
        """
        Score all Wheel nodes in the graph (batch processing).

        This is useful for scheduled/maintenance operations where you want to
        refresh scores for all wheels in the system. Follows the materialized
        view model: scores are snapshots computed at a point in time.

        Args:
            recursive: If True, scores all children first (default)
            skip_valid: If True, skip wheels with valid scores (default)
            graph_db: Graph database instance (injected)

        Returns:
            Statistics dict with keys:
            - total: Number of wheels found
            - scored: Number successfully scored (or already valid)
            - failed: Number that failed to score (None result)
            - skipped: Number skipped due to valid scores
            - avg_score: Average score of successfully scored wheels

        Example:
            scorer = TaroRank(alpha=1.0)
            # Only score invalid wheels
            stats = scorer.score_all_wheels(recursive=True, skip_valid=True)
            print(f"Scored {stats['scored']}/{stats['total']} wheels")
            print(f"Skipped {stats['skipped']} valid wheels")
            # Force recalculation of all wheels
            stats = scorer.score_all_wheels(recursive=True, skip_valid=False)
        """
        from dialectical_framework.graph.nodes.wheel import Wheel

        # Query all Wheel nodes
        query = "MATCH (w:Wheel) RETURN w"
        results = graph_db.execute_and_fetch(query)

        wheels = [Wheel(**result["w"]._properties) for result in results]

        total = len(wheels)
        scored = 0
        failed = 0
        skipped = 0
        scores = []

        for wheel in wheels:
            # Check if already valid
            if skip_valid and wheel.is_score_valid():
                skipped += 1
                if wheel.score is not None:
                    scores.append(wheel.score)
                continue

            score = self.score_node(wheel, recursive=recursive, skip_valid=skip_valid)
            if score is not None:
                scored += 1
                scores.append(score)
            else:
                failed += 1

        avg_score = sum(scores) / len(scores) if scores else 0.0

        return {
            "total": total,
            "scored": scored,
            "failed": failed,
            "skipped": skipped,
            "avg_score": avg_score
        }
