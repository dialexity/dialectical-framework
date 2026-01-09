"""
Manages creation and updates of Estimation nodes.

This module handles graph operations for storing P and R values
as separate Estimation nodes connected to AssessableEntity nodes.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING, TypeVar, Type, Sequence

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.graph.nodes.estimation import (
    Estimation,
    ProbabilityEstimation,
    RelevanceEstimation
)
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.invalidation import invalidate_node_and_parents

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity

T = TypeVar('T', bound=Estimation)


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
    def upsert_estimation(
        self,
        node: AssessableEntity,
        estimation_type: Type[T],
        value: Optional[float],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> None:
        """
        Create or update (upsert) an Estimation of specified type for a node.

        Automatically determines whether to invalidate based on estimation type:
        - Manual estimations (ProbabilityEstimation, RelevanceEstimation) → invalidate parents
        - Calculated estimations (Calculated*) → don't invalidate (these are TaroRank outputs)

        Args:
            node: AssessableEntity to upsert estimation for
            estimation_type: Type of estimation (any Estimation subclass)
            value: Estimation value (0.0-1.0) or None (None deletes the estimation)
            graph_db: Database connection (injected)

        Example:
            manager.upsert_estimation(node, ProbabilityEstimation, 0.8)  # Invalidates
            manager.upsert_estimation(node, CalculatedProbabilityEstimation, 0.75)  # No invalidation
            manager.upsert_estimation(node, ProbabilityEstimation, None)  # Deletes and invalidates
        """
        # Determine if we should invalidate based on estimation type
        # Calculated estimations are TaroRank outputs, not inputs, so don't invalidate
        should_invalidate = not estimation_type.__name__.startswith('Calculated')

        if value is None:
            # Delete existing estimations of this type
            self._delete_estimations(node, estimation_type, graph_db)
            if should_invalidate:
                invalidate_node_and_parents(node, graph_db=graph_db)
            return

        # Check for existing estimation of this type
        existing = self._get_scoring_estimation(node, estimation_type, graph_db)

        if existing:
            # Update existing
            old_value = existing.value
            existing.value = value
            existing.save()
            # Only invalidate if value actually changed AND it's a manual estimation
            if should_invalidate and old_value != value:
                invalidate_node_and_parents(node, graph_db=graph_db)
        else:
            # Create new
            estimation = estimation_type(value=value)
            estimation.save()
            node.estimations.connect(estimation)
            if should_invalidate:
                invalidate_node_and_parents(node, graph_db=graph_db)

    @inject
    def clear_estimations(
        self,
        node: AssessableEntity,
        estimation_types: Optional[Sequence[Type[Estimation]]] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> None:
        """
        Delete Estimation nodes for this AssessableEntity.

        Automatically determines whether to invalidate based on estimation types:
        - If clearing manual estimations (ProbabilityEstimation, RelevanceEstimation) → invalidate parents
        - If clearing calculated estimations (Calculated*) → don't invalidate

        Args:
            node: AssessableEntity to clear
            estimation_types: Types of estimations to clear. If None or empty, clears ALL estimations.
            graph_db: Database connection (injected)

        Example:
            # Clear all estimations (any type)
            manager.clear_estimations(node)
            manager.clear_estimations(node, None)
            manager.clear_estimations(node, [])

            # Clear only probability estimations
            manager.clear_estimations(node, [ProbabilityEstimation])

            # Clear only relevance estimations
            manager.clear_estimations(node, [RelevanceEstimation])

            # Clear both probability and relevance (explicit)
            manager.clear_estimations(node, [ProbabilityEstimation, RelevanceEstimation])
        """
        should_invalidate = False

        if not estimation_types:
            # Clearing ALL estimations - check if any manual ones exist
            all_estimations = node.estimations.all()
            for est, _ in all_estimations:
                if not est.__class__.__name__.startswith('Calculated'):
                    should_invalidate = True
                    break
            # Delete ALL estimations
            self._delete_all_estimations(node, graph_db)
        else:
            # Clearing specific types - check if any are manual
            for estimation_type in estimation_types:
                if not estimation_type.__name__.startswith('Calculated'):
                    should_invalidate = True
                self._delete_estimations(node, estimation_type, graph_db)

        # Invalidate if we cleared any manual estimations
        if should_invalidate:
            invalidate_node_and_parents(node, graph_db=graph_db)

    def _delete_all_estimations(
        self,
        node: AssessableEntity,
        graph_db: Union[Memgraph, Neo4j]
    ) -> None:
        """
        Delete ALL Estimation nodes connected to this AssessableEntity.

        Args:
            node: AssessableEntity to clear
            graph_db: Database connection
        """
        if node._id is None:
            return

        # Delete all estimations in a single query
        query = """
            MATCH (n)-[:HAS_ESTIMATION]->(e:Estimation)
            WHERE id(n) = $node_id
            DETACH DELETE e
        """
        graph_db.execute(query, {"node_id": node._id})

    def _get_scoring_estimation(
        self,
        node: AssessableEntity,
        estimation_class: Type[T],
        graph_db: Union[Memgraph, Neo4j]
    ) -> Optional[T]:
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
        estimation_class: Type[T],
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

        # Delete estimations of specific type in a single query
        label = estimation_class.__name__
        query = f"""
            MATCH (n)-[:HAS_ESTIMATION]->(e:{label})
            WHERE id(n) = $node_id
            DETACH DELETE e
        """
        graph_db.execute(query, {"node_id": node._id})
