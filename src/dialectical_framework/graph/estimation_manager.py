"""
Manages creation and updates of Estimation nodes.

This module handles graph operations for storing P and R values
as separate Estimation nodes connected to AssessableEntity nodes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.graph.nodes.estimation import (
    ProbabilityEstimation,
    RelevanceEstimation
)
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity


class EstimationManager:
    """
    Manages creation and updates of Estimation nodes.

    This class handles the graph operations for storing P and R values
    as separate Estimation nodes connected to AssessableEntity nodes.

    Design:
    - Creates new Estimation nodes when needed
    - Updates existing Estimation nodes when re-scoring
    - Deletes estimations when clearing scores
    - Uses dependency injection for graph_db
    """

    @inject
    def update_probability(
        self,
        node: AssessableEntity,
        value: Optional[float],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        invalidate: bool = True
    ) -> None:
        """
        Create or update ProbabilityEstimation for a node.

        Args:
            node: AssessableEntity to update
            value: P value (0.0-1.0) or None
            graph_db: Database connection (injected)
            invalidate: If True, invalidate node score (default: True)
                       Set to False when called from TaroRank during scoring
        """
        if value is None:
            # Delete existing probability estimations
            self._delete_estimations(node, ProbabilityEstimation, graph_db)
            if invalidate:
                node.score_invalidated_at = datetime.now()
                node.save()
            return

        # Check for existing probability estimation
        existing = self._get_scoring_estimation(node, ProbabilityEstimation, graph_db)

        if existing:
            # Update existing
            old_value = existing.value
            existing.value = value
            existing.save()
            # Only invalidate if value actually changed
            if invalidate and old_value != value:
                node.score_invalidated_at = datetime.now()
                node.save()
        else:
            # Create new
            estimation = ProbabilityEstimation(value=value)
            estimation.save()
            node.estimations.connect(estimation)
            if invalidate:
                node.score_invalidated_at = datetime.now()
                node.save()

    @inject
    def update_relevance(
        self,
        node: AssessableEntity,
        value: Optional[float],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        invalidate: bool = True
    ) -> None:
        """
        Create or update RelevanceEstimation for a node.

        Args:
            node: AssessableEntity to update
            value: R value (0.0-1.0) or None
            graph_db: Database connection (injected)
            invalidate: If True, invalidate node score (default: True)
                       Set to False when called from TaroRank during scoring
        """
        if value is None:
            # Delete existing relevance estimations
            self._delete_estimations(node, RelevanceEstimation, graph_db)
            if invalidate:
                node.score_invalidated_at = datetime.now()
                node.save()
            return

        # Check for existing relevance estimation
        existing = self._get_scoring_estimation(node, RelevanceEstimation, graph_db)

        if existing:
            # Update existing
            old_value = existing.value
            existing.value = value
            existing.save()
            # Only invalidate if value actually changed
            if invalidate and old_value != value:
                node.score_invalidated_at = datetime.now()
                node.save()
        else:
            # Create new
            estimation = RelevanceEstimation(value=value)
            estimation.save()
            node.estimations.connect(estimation)
            if invalidate:
                node.score_invalidated_at = datetime.now()
                node.save()

    @inject
    def clear_estimations(
        self,
        node: AssessableEntity,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> None:
        """
        Delete all Estimation nodes for this AssessableEntity.

        Args:
            node: AssessableEntity to clear
            graph_db: Database connection (injected)
        """
        self._delete_estimations(node, ProbabilityEstimation, graph_db)
        self._delete_estimations(node, RelevanceEstimation, graph_db)

    def _get_scoring_estimation(
        self,
        node: AssessableEntity,
        estimation_class: type,
        graph_db: Union[Memgraph, Neo4j]
    ) -> Optional[Union[ProbabilityEstimation, RelevanceEstimation]]:
        """
        Get existing scoring-generated estimation (not manual user estimations).

        For now, we'll just update the first matching estimation.
        In the future, we could distinguish scoring-generated from manual
        estimations using a property like 'source: "scoring"'.

        Args:
            node: AssessableEntity to search
            estimation_class: Type of estimation to find
            graph_db: Database connection

        Returns:
            Estimation instance or None
        """
        estimations = node.estimations.all()
        for est, _ in estimations:
            if isinstance(est, estimation_class):
                return est
        return None

    def _delete_estimations(
        self,
        node: AssessableEntity,
        estimation_class: type,
        graph_db: Union[Memgraph, Neo4j]
    ) -> None:
        """
        Delete all estimations of a specific type.

        Args:
            node: AssessableEntity to clear
            estimation_class: Type of estimation to delete
            graph_db: Database connection
        """
        if node._id is None:
            return

        # Find and delete matching estimations
        estimations = node.estimations.all()
        for est, _ in estimations:
            if isinstance(est, estimation_class):
                # Delete the estimation node
                if est._id is not None:
                    query = "MATCH (e) WHERE id(e) = $est_id DETACH DELETE e"
                    graph_db.execute(query, {"est_id": est._id})
