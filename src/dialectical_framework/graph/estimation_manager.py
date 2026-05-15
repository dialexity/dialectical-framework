"""
Manages creation and updates of Estimation nodes.

This module handles graph operations for storing domain estimation values
as separate Estimation nodes connected to AssessableEntity nodes.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING, TypeVar, Type, Sequence

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.graph.nodes.estimation import Estimation
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
    from dialectical_framework.graph.nodes.rationale import Rationale

T = TypeVar('T', bound=Estimation)


class EstimationManager:
    """
    Manages creation and updates of Estimation nodes.

    This class handles the graph operations for storing domain estimation values
    as separate Estimation nodes connected to AssessableEntity nodes.

    Design:
    - Creates new Estimation nodes when needed
    - Replaces existing Estimation nodes when value changes
    - Deletes estimations when clearing
    - Uses dependency injection for graph_db
    """

    @inject
    def upsert_estimation(
        self,
        node: AssessableEntity,
        estimation_type: Type[T],
        value: Optional[float],
        provider: Optional[Rationale] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Optional[T]:
        """
        Set an Estimation of specified type for a node (replacing any existing).

        This is not a true "upsert" (update-or-insert). Estimation nodes are
        content-identified by (type, value, target). If the value changes,
        the old estimation is deleted and a new one is created. If the value
        is the same, the existing estimation node is reused (deduplication).

        Args:
            node: AssessableEntity to set estimation for (must be committed)
            estimation_type: Type of estimation (any Estimation subclass)
            value: Estimation value (0.0-1.0) or None (None deletes the estimation)
            provider: Optional Rationale that provides this estimation (provenance)
            graph_db: Database connection (injected)

        Returns:
            The created/existing estimation node, or None if value was None (deletion)
        """
        if value is None:
            self._delete_estimations(node, estimation_type, graph_db)
            return None

        # Check for existing estimation of this type connected to this node
        existing = self._get_scoring_estimation(node, estimation_type, graph_db)

        if existing:
            old_value = existing.value
            if old_value != value:
                node.estimations.disconnect(existing)
                estimation = self._get_or_create_estimation(estimation_type, value, node, graph_db, provider)
            else:
                estimation = existing
        else:
            estimation = self._get_or_create_estimation(estimation_type, value, node, graph_db, provider)

        return estimation

    @inject
    def clear_estimations(
        self,
        node: AssessableEntity,
        estimation_types: Optional[Sequence[Type[Estimation]]] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> None:
        """
        Delete Estimation nodes for this AssessableEntity.

        Args:
            node: AssessableEntity to clear
            estimation_types: Types of estimations to clear. If None or empty, clears ALL estimations.
            graph_db: Database connection (injected)
        """
        if not estimation_types:
            self._delete_all_estimations(node, graph_db)
        else:
            for estimation_type in estimation_types:
                self._delete_estimations(node, estimation_type, graph_db)

    def _delete_all_estimations(
        self,
        node: AssessableEntity,
        graph_db: Union[Memgraph, Neo4j]
    ) -> None:
        """Delete ALL Estimation nodes connected to this AssessableEntity."""
        if node._id is None:
            return

        query = """
            MATCH (e:Estimation)-[:ESTIMATES]->(n)
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
        Get existing estimation of a given type for this node.

        Returns:
            Estimation instance or None
        """
        estimations = node.estimations.all()
        for est, _ in estimations:
            if isinstance(est, estimation_class):
                return est
        return None

    def _get_or_create_estimation(
        self,
        estimation_class: Type[T],
        value: float,
        target: AssessableEntity,
        graph_db: Union[Memgraph, Neo4j],
        provider: Optional[Rationale] = None
    ) -> T:
        """
        Get existing estimation by content, or create new one.

        Estimations are content-identified by (type, value, target) tuple.
        """
        if target._id is None:
            estimation = estimation_class(value=value)
            estimation.set_target(target)
            if provider:
                estimation.set_provider(provider)
            estimation.commit()
            return estimation

        # Look up by value and target relationship
        label = estimation_class.label
        query = f"""
            MATCH (e:{label} {{value: $value}})-[:ESTIMATES]->(n)
            WHERE id(n) = $target_id
            RETURN e
            LIMIT 1
        """
        result = list(graph_db.execute_and_fetch(query, {
            "value": value,
            "target_id": target._id
        }))

        if result:
            return result[0]["e"]

        # Create new
        estimation = estimation_class(value=value)
        estimation.set_target(target)
        if provider:
            estimation.set_provider(provider)
        estimation.commit()
        return estimation

    def _delete_estimations(
        self,
        node: AssessableEntity,
        estimation_class: Type[T],
        graph_db: Union[Memgraph, Neo4j]
    ) -> None:
        """Delete all estimations of a specific type for this node."""
        if node._id is None:
            return

        label = estimation_class.label
        query = f"""
            MATCH (e:{label})-[:ESTIMATES]->(n)
            WHERE id(n) = $node_id
            DETACH DELETE e
        """
        graph_db.execute(query, {"node_id": node._id})
