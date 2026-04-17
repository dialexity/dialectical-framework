"""
TaroRank scoring algorithm for graph-native dialectical structures.

This module implements the dual-dimension scoring formula: Score = P × R^α
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.estimation import (
    CalculatedProbabilityEstimation,
    CalculatedRelevanceEstimation,
    CalculatedScoreEstimation
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

        # Track nodes currently being scored to detect cycles
        self._scoring_stack: set[str] = set()

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
            from dialectical_framework.graph.scoring.tarorank_calculators.dialectical_component_calculator import ComponentCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.transition_calculator import TransitionCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.perspective_calculator import PerspectiveCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.synthesis_calculator import SynthesisCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.cycle_calculator import CycleCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.transformation_calculator import TransformationCalculator
            from dialectical_framework.graph.scoring.tarorank_calculators.wheel_calculator import WheelCalculator

            # Note: Rationale is NOT in this map because it extends BaseNode, not AssessableEntity.
            # Rationales are sources of evidence (they PROVIDE estimations), not targets of scoring.
            # The RationaleAuditor reads estimations from rationales but doesn't score them.
            calculator_map = {
                'DialecticalComponent': ComponentCalculator,
                'Transition': TransitionCalculator,
                'Perspective': PerspectiveCalculator,
                'Synthesis': SynthesisCalculator,
                'Cycle': CycleCalculator,
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
        node: AssessableEntity,
        force: bool = False
    ) -> Optional[float]:
        """
        Calculate and store score for a node.

        This method:
        1. Validates node is committed (raises ValueError if not)
        2. Checks if score is valid (skips if valid, unless force=True)
        3. Detects circular dependencies (returns None if cycle found)
        4. Clears old calculated estimations (so properties return manual/child values)
        5. Recursively scores children
        6. Calculates node's P and R (using properties, which now reflect current state)
        7. Stores new calculated P and R
        8. Computes final Score = P × R^α
        9. Stores score in node.score field
        10. Returns the score

        Committed Node Requirement:
        Nodes must be committed before scoring. Uncommitted nodes have no stable
        identity (hash) and cannot be reliably tracked for cycle detection or
        invalidation. Call node.commit() before scoring.

        Cycle Detection:
        If a circular dependency is detected (e.g., WU_A → Trans_A → ac_re: WU_B →
        Trans_B → ac_re: WU_A), the method returns None to break the cycle gracefully.
        This prevents infinite recursion in large databases where cycles may exist.

        With hierarchical invalidation propagation, we always skip valid nodes.
        If something needs rescoring, it will be marked invalid automatically.

        Args:
            node: AssessableEntity to score (must be committed)
            force: If True, recalculate even if score appears valid. Use this when
                   you know DB was modified but in-memory object may be stale.
                   This only affects the top-level node - children still use
                   validity checks (their DB state should be accurate).

        Returns:
            Computed score or None if insufficient data or cycle detected

        Raises:
            ValueError: If node is not committed

        Example:
            scorer = TaroRank(alpha=1.0)
            score = scorer.calculate_score(wheel)

            # After calculate_transitions/calculate_syntheses, force rescore:
            score = scorer.calculate_score(wheel, force=True)
        """
        # Require committed node - scoring uncommitted nodes doesn't make sense
        # (they have no stable identity and can't be reliably tracked)
        if not node.is_committed:
            raise ValueError(
                f"Cannot score uncommitted {node.__class__.__name__}. "
                f"Call commit() first to finalize the node before scoring."
            )

        # Skip valid nodes unless force=True
        # force is useful when caller knows DB was modified but in-memory object is stale
        if not force and node.is_score_valid():
            return node.score

        # Detect cycles: if this node is already being scored up the call stack,
        # we've found a circular dependency (e.g., WU_A → Trans_A → ac_re: WU_B → Trans_B → ac_re: WU_A)
        if node.hash in self._scoring_stack:
            # Circular dependency detected - cannot compute score
            # Return None to break the cycle gracefully
            return None

        # Add to scoring stack to track that we're currently scoring this node
        self._scoring_stack.add(node.hash)

        try:
            # Clear old calculated estimations BEFORE calculating
            # This ensures properties return manual values (or None) for this node
            # After scoring children, their properties will return fresh calculated values
            self.estimation_manager.clear_estimations(
                node,
                estimation_types=[
                    CalculatedProbabilityEstimation,
                    CalculatedRelevanceEstimation,
                    CalculatedScoreEstimation
                ]
            )

            calculator = self._get_calculator(node.__class__.__name__)

            # Always score children recursively (they get fresh calculated values)
            # Propagate force flag so children also rescore if parent is forced
            calculator.score_children(node, force=force)

            # Calculate P and R (properties now return correct values)
            p = calculator.calculate_probability(node)
            r = calculator.calculate_relevance(node)

            # Store new calculated P and R (won't invalidate)
            self.estimation_manager.upsert_estimation(node, CalculatedProbabilityEstimation, p)
            self.estimation_manager.upsert_estimation(node, CalculatedRelevanceEstimation, r)

            # Calculate final score
            if p is None or r is None:
                # Store None score (clears any existing)
                self.estimation_manager.upsert_estimation(node, CalculatedScoreEstimation, None)
                return None

            score = p * (r ** self.alpha)

            # Store score as CalculatedScoreEstimation (won't invalidate)
            self.estimation_manager.upsert_estimation(node, CalculatedScoreEstimation, score)

            return score
        finally:
            # Always remove from scoring stack when done (even if exception occurs)
            self._scoring_stack.discard(node.hash)

    def clear_scores(self, node: AssessableEntity) -> None:
        """
        Clear computed scores for a node and all its children.

        This clears calculated estimation nodes:
        - CalculatedProbabilityEstimation
        - CalculatedRelevanceEstimation
        - CalculatedScoreEstimation

        Manual estimations are PRESERVED (they're user/agent input, not algorithm output).

        Args:
            node: Node to clear scores for

        Example:
            scorer = TaroRank()
            scorer.clear_scores(wheel)
            scorer.score_node(wheel)  # Re-score using existing manual estimations
        """
        # Clear CALCULATED estimations (algorithm output), preserve manual estimations
        self.estimation_manager.clear_estimations(
            node,
            estimation_types=[
                CalculatedProbabilityEstimation,
                CalculatedRelevanceEstimation,
                CalculatedScoreEstimation
            ]
        )

        # Always clear children recursively
        calculator = self._get_calculator(node.__class__.__name__)
        calculator.clear_children(node)
