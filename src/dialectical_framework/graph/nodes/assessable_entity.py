"""
Assessable entity class for scored entities in the dialectical framework.

This module provides the AssessableEntity class which serves as the base for all
nodes that can be assessed/scored (Components, WisdomUnits, Wheels, Cycles, etc.).
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.explains_relationship import (
    ExplainsRelationship,
)
from dialectical_framework.graph.relationships.estimates_relationship import (
    EstimatesRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.estimation import (
        Estimation,
        CalculatedEstimation,
        CalculatedScoreEstimation,
        ProbabilityEstimation,
        RelevanceEstimation,
        CalculatedProbabilityEstimation,
        CalculatedRelevanceEstimation
    )
    from dialectical_framework.graph.nodes.rationale import Rationale


class AssessableEntity(BaseNode, label="Assessable"):
    """
    Base class for all assessable (scoreable) entities in the dialectical graph.

    Assessable nodes can have:
    - A score (computed by external TaroRank algorithm, stored as CalculatedScoreEstimation)
    - Rationales (explanations for assessments)
    - Estimations (probability, relevance, feasibility, cost)

    The scoring architecture follows the formula: Score = P × R^α
    where P is probability and R is relevance.

    Score Provenance:
    Scores are analytical artifacts stored as CalculatedScoreEstimation nodes.
    Computed at a point in time, they don't auto-update when knowledge graph changes.
    Users explicitly refresh scores when needed (snapshot model, not reactive cache).
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

        # Separate direct (non-sourced) vs rationale-provided (sourced) estimations
        # Hard veto: if any direct estimation has P=0, return 0
        # Soft exclusion: filter out sourced estimations with P=0
        values = []
        for est in manual:
            has_source = est.provider.count() > 0  # Check PROVIDES relationship
            if est.value == 0:
                if not has_source:
                    # Direct P=0 → hard veto
                    return 0.0
                # else: sourced P=0 → soft exclusion (skip)
            else:
                values.append(est.value)

        if not values:
            return None
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

        Veto semantics:
        - Direct (non-sourced) estimation with R=0: hard veto (returns 0)
        - Sourced (rationale-provided) estimation with R=0: soft exclusion (filtered out)

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
            # Separate direct (non-sourced) vs rationale-provided (sourced) estimations
            # Hard veto: if any direct estimation has R=0, return 0
            # Soft exclusion: filter out sourced estimations with R=0
            direct_zeros = []
            values = []
            for est in manual_relevance:
                has_source = est.provider.count() > 0  # Check PROVIDES relationship
                if est.value == 0:
                    if not has_source:
                        # Direct R=0 → hard veto
                        return 0.0
                    # else: sourced R=0 → soft exclusion (skip)
                else:
                    values.append(est.value)

            if not values:
                return None
            return gm_with_zeros_and_nones_handled(values)

        # 3. Fallback to FeasibilityEstimation - third priority
        manual_feasibility = [
            est for est, _ in estimations
            if isinstance(est, FeasibilityEstimation)
        ]
        if manual_feasibility:
            # Same logic: hard veto on direct R=0, soft exclusion on sourced R=0
            values = []
            for est in manual_feasibility:
                has_source = est.provider.count() > 0
                if est.value == 0:
                    if not has_source:
                        return 0.0
                else:
                    values.append(est.value)

            if not values:
                return None
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
    def score(self) -> Optional[float]:
        """
        Get score from CalculatedScoreEstimation.

        Returns:
            Score value (0.0-1.0) or None if not computed

        Example:
            scorer = TaroRank()
            scorer.score_node(wheel)
            print(wheel.score)  # Returns computed score
        """
        estimation = self._get_calculated_score_estimation()
        return estimation.value if estimation else None

    @property
    def is_score_calculated(self) -> bool:
        """
        Check if score has been calculated (CalculatedScoreEstimation exists).

        Returns:
            True if CalculatedScoreEstimation exists, False otherwise
        """
        return self.score is not None

    def _get_calculated_score_estimation(self) -> Optional[CalculatedScoreEstimation]:
        """
        Get the CalculatedScoreEstimation for this entity.

        Returns:
            CalculatedScoreEstimation or None if not computed
        """
        from dialectical_framework.graph.nodes.estimation import CalculatedScoreEstimation

        for est, _ in self.estimations.all():
            if isinstance(est, CalculatedScoreEstimation):
                return est
        return None

    @property
    def best_rationale(self) -> Optional[Rationale]:
        """
        Get the highest-rated rationale explaining this entity.

        Rationales are ranked by their rating field (0.0-1.0). If no rationales have
        ratings, returns the first rationale. If no rationales exist, returns None.

        Note: Rationale no longer extends AssessableEntity and doesn't have a score.
        The rating field is used for ranking instead.

        Returns:
            Rationale with highest rating, or first rationale, or None

        Example:
            r1 = Rationale(text="Good reason", rating=0.8)
            r2 = Rationale(text="Better reason", rating=0.9)
            component.rationales.connect(r1)
            component.rationales.connect(r2)

            best = component.best_rationale  # Returns r2 (higher rating)
        """
        from dialectical_framework.graph.nodes.rationale import Rationale

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

    def is_score_valid(self) -> bool:
        """
        Check if the score is still valid (data hasn't changed since computation).

        A score is valid if CalculatedScoreEstimation exists and:
        - Either never invalidated (invalidated_at is None)
        - OR computed after last invalidation (committed_at > invalidated_at)

        Returns:
            True if score is valid and doesn't need recalculation

        Example:
            # Only recalculate if data changed
            if not wheel.is_score_valid():
                scorer.score_node(wheel)
        """
        estimation = self._get_calculated_score_estimation()
        if estimation is None:
            return False
        return estimation.is_valid()

    def __repr__(self) -> str:
        """String representation of the assessable entity."""
        score_str = f"{self.score:.3f}" if self.score is not None else "None"
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"{self.__class__.__name__}({hash_str}, score={score_str})"
