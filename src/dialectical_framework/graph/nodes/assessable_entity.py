"""
Assessable entity class for scored entities in the dialectical framework.

This module provides the AssessableEntity class which serves as the base for all
nodes that can be assessed/scored (Components, WisdomUnits, Wheels, Cycles, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Optional, TYPE_CHECKING, Union

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j, Node

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.explains_relationship import (
    ExplainsRelationship,
)
from dialectical_framework.graph.relationships.has_estimation_relationship import (
    HasEstimationRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.estimation import (
        Estimation,
        ProbabilityEstimation,
        RelevanceEstimation,
        CalculatedProbabilityEstimation,
        CalculatedRelevanceEstimation
    )
    from dialectical_framework.graph.nodes.rationale import Rationale


class AssessableEntity(BaseNode, Node, label="Assessable"):
    """
    Base class for all assessable (scoreable) entities in the dialectical graph.

    Assessable nodes can have:
    - A score (computed by external TaroRank algorithm)
    - Rationales (explanations for assessments)
    - Estimations (probability, relevance, feasibility, cost)

    The scoring architecture follows the formula: Score = P × R^α
    where P is probability and R is relevance.

    Score Provenance:
    Scores are analytical artifacts (like BI dashboard metrics or materialized views)
    computed at a point in time. They don't auto-update when knowledge graph changes.
    Users explicitly refresh scores when needed (snapshot model, not reactive cache).
    """

    score: Optional[float] = None
    score_computed_at: Optional[datetime] = None
    score_invalidated_at: Optional[datetime] = None

    # Declarative relationships
    # Rationales explain this assessable entity
    rationales: ClassVar[RelationshipManager[Rationale]] = RelationshipFrom(
        "Rationale",
        model=ExplainsRelationship,
        cardinality=(0, None)  # Zero or more rationales
    )

    # Estimations for this assessable entity
    estimations: ClassVar[RelationshipManager[Estimation]] = RelationshipTo(
        "Estimation",
        model=HasEstimationRelationship,
        cardinality=(0, None)  # Zero or more estimations
    )

    @property
    def probability(self) -> Optional[float]:
        """
        Get probability following legacy semantics.

        Returns:
        - CalculatedProbabilityEstimation value if exists
        - OTHERWISE: GM of all ProbabilityEstimation nodes (manual)
        - NOT mixed together!

        This matches legacy behavior:
            return calculated_probability if calculated_probability is not None else manual_probability

        If any manual estimation is 0, returns 0 (veto semantics).

        Returns:
            Probability value (0.0-1.0) or None if no estimations exist

        Example:
            # Manual only
            component.estimations.connect(ProbabilityEstimation(value=0.8))
            prob = component.probability  # Returns 0.8

            # Multiple manual: returns geometric mean
            component.estimations.connect(ProbabilityEstimation(value=0.6))
            prob = component.probability  # Returns ~0.693 (GM of 0.8 and 0.6)

            # Calculated exists: returns calculated (ignores manual)
            component.estimations.connect(CalculatedProbabilityEstimation(value=0.75))
            prob = component.probability  # Returns 0.75 (calculated takes precedence)
        """
        from dialectical_framework.graph.nodes.estimation import (
            ProbabilityEstimation,
            CalculatedProbabilityEstimation
        )
        from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

        estimations = self.estimations.all()

        # 1. Check for calculated (TaroRank output) first
        calculated = [
            est for est, _ in estimations
            if isinstance(est, CalculatedProbabilityEstimation)
        ]
        if calculated:
            # Should be at most one calculated estimation per node
            return calculated[0].value

        # 2. Otherwise, aggregate manual estimations
        manual = [
            est for est, _ in estimations
            if isinstance(est, ProbabilityEstimation)
        ]
        if not manual:
            return None

        values = [est.value for est in manual]
        return gm_with_zeros_and_nones_handled(values)

    @property
    def relevance(self) -> Optional[float]:
        """
        Get relevance following legacy semantics with FeasibilityEstimation fallback.

        Returns:
        - CalculatedRelevanceEstimation value if exists (highest priority)
        - OTHERWISE: GM of all RelevanceEstimation nodes (manual, second priority)
        - OTHERWISE: GM of all FeasibilityEstimation nodes (manual, fallback priority)
        - NOT mixed together!

        Priority order:
        1. CalculatedRelevanceEstimation (TaroRank output)
        2. RelevanceEstimation (manual)
        3. FeasibilityEstimation (manual fallback - semantically same as relevance)

        If any manual estimation is 0, returns 0 (veto semantics).

        Returns:
            Relevance value (0.0-1.0) or None if no estimations exist

        Example:
            # RelevanceEstimation takes priority
            component.estimations.connect(RelevanceEstimation(value=0.9))
            component.estimations.connect(FeasibilityEstimation(value=0.7))
            rel = component.relevance  # Returns 0.9 (RelevanceEstimation takes priority)

            # FeasibilityEstimation as fallback
            component.estimations.connect(FeasibilityEstimation(value=0.8))
            rel = component.relevance  # Returns 0.8 (FeasibilityEstimation used as fallback)

            # Calculated takes precedence over both
            component.estimations.connect(RelevanceEstimation(value=0.9))
            component.estimations.connect(CalculatedRelevanceEstimation(value=0.85))
            rel = component.relevance  # Returns 0.85 (calculated takes precedence)
        """
        from dialectical_framework.graph.nodes.estimation import (
            RelevanceEstimation,
            FeasibilityEstimation,
            CalculatedRelevanceEstimation
        )
        from dialectical_framework.graph.scoring.gm import gm_with_zeros_and_nones_handled

        estimations = self.estimations.all()

        # 1. Check for calculated (TaroRank output) first - highest priority
        calculated = [
            est for est, _ in estimations
            if isinstance(est, CalculatedRelevanceEstimation)
        ]
        if calculated:
            # Should be at most one calculated estimation per node
            return calculated[0].value

        # 2. Check for manual RelevanceEstimation - second priority
        manual_relevance = [
            est for est, _ in estimations
            if isinstance(est, RelevanceEstimation)
        ]
        if manual_relevance:
            values = [est.value for est in manual_relevance]
            return gm_with_zeros_and_nones_handled(values)

        # 3. Fallback to FeasibilityEstimation - third priority
        manual_feasibility = [
            est for est, _ in estimations
            if isinstance(est, FeasibilityEstimation)
        ]
        if manual_feasibility:
            values = [est.value for est in manual_feasibility]
            return gm_with_zeros_and_nones_handled(values)

        # 4. No estimations found
        return None

    @property
    def is_probability_calculated(self) -> bool:
        """
        Check if probability comes from calculated (TaroRank) estimation.

        Returns:
            True if CalculatedProbabilityEstimation exists, False otherwise

        Example:
            if entity.is_probability_calculated:
                print(f"[{entity.probability}]")  # Show in brackets
            else:
                print(f"{entity.probability}")    # Show without brackets
        """
        from dialectical_framework.graph.nodes.estimation import CalculatedProbabilityEstimation

        for est, _ in self.estimations.all():
            if isinstance(est, CalculatedProbabilityEstimation):
                return True
        return False

    @property
    def is_relevance_calculated(self) -> bool:
        """
        Check if relevance comes from calculated (TaroRank) estimation.

        Returns:
            True if CalculatedRelevanceEstimation exists, False otherwise

        Example:
            if entity.is_relevance_calculated:
                print(f"[{entity.relevance}]")  # Show in brackets
            else:
                print(f"{entity.relevance}")    # Show without brackets
        """
        from dialectical_framework.graph.nodes.estimation import CalculatedRelevanceEstimation

        for est, _ in self.estimations.all():
            if isinstance(est, CalculatedRelevanceEstimation):
                return True
        return False

    @property
    def best_rationale(self) -> Optional[Rationale]:
        """
        Get the highest-scoring rationale explaining this entity.

        Rationales are ranked by their score field. If no rationales have
        scores, returns the first rationale. If no rationales exist, returns None.

        Returns:
            Rationale with highest score, or first rationale, or None

        Example:
            r1 = Rationale(text="Good reason", score=0.8)
            r2 = Rationale(text="Better reason", score=0.9)
            component.rationales.connect(r1)
            component.rationales.connect(r2)

            best = component.best_rationale  # Returns r2 (higher score)
        """
        from dialectical_framework.graph.nodes.rationale import Rationale

        rationales_with_props = self.rationales.all()
        if not rationales_with_props:
            return None

        rationales = [rat for rat, _ in rationales_with_props]

        # Get rationales with scores
        scored_rationales = [r for r in rationales if r.score is not None]

        if scored_rationales:
            # Return rationale with highest score
            return max(scored_rationales, key=lambda r: r.score)

        # Fallback: return first rationale if none have scores
        return rationales[0] if rationales else None

    @inject
    def is_score_valid(
        self,
        graph_db: Optional[Union[Memgraph, Neo4j]] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if the score is still valid (data hasn't changed since computation).

        A score is valid if:
        - Score exists
        - Score was computed (has timestamp)
        - Either never invalidated OR computed after last invalidation

        This method queries the DB for the current invalidation timestamp to handle
        cases where in-memory objects are stale after DB modifications.

        Returns:
            True if score is valid and doesn't need recalculation

        Example:
            # Only recalculate if data changed
            if not wheel.is_score_valid():
                scorer.score_node(wheel)
        """
        if self.score is None:
            return False

        if self.score_computed_at is None:
            return False

        # Query DB for current invalidation timestamp (in-memory may be stale)
        db_invalidated_at = self._get_db_invalidated_at(graph_db)

        if db_invalidated_at is None:
            return True  # Never invalidated

        # Valid if computed AFTER invalidation
        return self.score_computed_at > db_invalidated_at

    def _get_db_invalidated_at(
        self,
        graph_db: Union[Memgraph, Neo4j]
    ) -> Optional[datetime]:
        """
        Query DB for current score_invalidated_at value.

        This ensures we check against the actual DB state, not stale in-memory state.
        """
        if self._id is None:
            return self.score_invalidated_at  # Not persisted, use in-memory

        try:
            query = """
                MATCH (n)
                WHERE id(n) = $node_id
                RETURN n.score_invalidated_at as invalidated_at
            """
            results = list(graph_db.execute_and_fetch(query, {"node_id": self._id}))
            if results:
                return results[0]["invalidated_at"]
        except Exception:
            pass  # Fall back to in-memory value

        return self.score_invalidated_at

    def __repr__(self) -> str:
        """String representation of the assessable entity."""
        score_str = f"{self.score:.3f}" if self.score is not None else "None"
        return f"{self.__class__.__name__}(uid={self.uid}, score={score_str})"
