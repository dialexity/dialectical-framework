"""
Assessable entity class for scored entities in the dialectical framework.

This module provides the AssessableEntity class which serves as the base for all
nodes that can be assessed/scored (Components, WisdomUnits, Wheels, Cycles, etc.).
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation, RelevanceEstimation
    from dialectical_framework.graph.nodes.rationale import Rationale


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

    @property
    def probability(self) -> Optional[float]:
        """
        Get probability from connected ProbabilityEstimation nodes.

        If multiple probability estimations exist, returns the geometric mean.
        This reflects the multiplicative nature of independent probabilities.
        If any estimation is 0, returns 0 (veto semantics).

        Returns:
            Geometric mean of probability values (0.0-1.0) or None if no estimations exist

        Example:
            component.estimations.connect(ProbabilityEstimation(value=0.8))
            prob = component.probability  # Returns 0.8

            # Multiple estimations: returns geometric mean
            component.estimations.connect(ProbabilityEstimation(value=0.6))
            prob = component.probability  # Returns ~0.693 (GM of 0.8 and 0.6)
        """
        from dialectical_framework.graph.nodes.estimation import ProbabilityEstimation
        from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

        estimations = self.estimations.all()
        prob_estimations = [
            est for est, _ in estimations
            if isinstance(est, ProbabilityEstimation)
        ]

        if not prob_estimations:
            return None

        values = [est.value for est in prob_estimations]
        return gm_with_zeros_and_nones_handled(values)

    @property
    def relevance(self) -> Optional[float]:
        """
        Get relevance from connected RelevanceEstimation nodes.

        If multiple relevance estimations exist, returns the geometric mean.
        This reflects the multiplicative nature of relevance factors.
        If any estimation is 0, returns 0 (veto semantics).

        Returns:
            Geometric mean of relevance values (0.0-1.0) or None if no estimations exist

        Example:
            component.estimations.connect(RelevanceEstimation(value=0.9))
            rel = component.relevance  # Returns 0.9

            # Multiple estimations: returns geometric mean
            component.estimations.connect(RelevanceEstimation(value=0.7))
            rel = component.relevance  # Returns ~0.789 (GM of 0.9 and 0.7)
        """
        from dialectical_framework.graph.nodes.estimation import RelevanceEstimation
        from dialectical_framework.utils.gm import gm_with_zeros_and_nones_handled

        estimations = self.estimations.all()
        rel_estimations = [
            est for est, _ in estimations
            if isinstance(est, RelevanceEstimation)
        ]

        if not rel_estimations:
            return None

        values = [est.value for est in rel_estimations]
        return gm_with_zeros_and_nones_handled(values)

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

    def __repr__(self) -> str:
        """String representation of the assessable entity."""
        score_str = f"{self.score:.3f}" if self.score is not None else "None"
        return f"{self.__class__.__name__}(uid={self.uid}, score={score_str})"
