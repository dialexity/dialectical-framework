"""
Manages creation and updates of Estimation nodes.

This module handles graph operations for storing P and R values
as separate Estimation nodes connected to AssessableEntity nodes.
It also provides score invalidation propagation utilities.
"""

from __future__ import annotations

import time
from typing import Optional, Union, TYPE_CHECKING, TypeVar, Type, Sequence

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.graph.nodes.estimation import (
    Estimation,
    CalculatedEstimation,
    ProbabilityEstimation,
    RelevanceEstimation
)
from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
    from dialectical_framework.graph.nodes.rationale import Rationale

T = TypeVar('T', bound=Estimation)


@inject
def invalidate_node_and_parents(
    node: AssessableEntity,
    graph_db: Optional[Union[Memgraph, Neo4j]] = Provide[DI.graph_db],
    visited: set[int] | None = None
) -> None:
    """
    Invalidate this node and recursively propagate to all parent nodes.

    Use this function when structural changes occur that affect scoring
    but aren't captured by EstimationManager (e.g., adding rationale
    critique relationships).

    This ensures that when a node's scoring inputs change, all ancestors
    are marked invalid so they get rescored on the next scoring pass.

    Args:
        node: AssessableEntity to invalidate
        graph_db: Database connection (injected if not provided)
        visited: Set of node IDs already visited (for cycle detection)

    Example:
        # After connecting audit rationale as critique
        rationale.critiques.connect(audit_rationale)
        invalidate_node_and_parents(rationale)  # DI injects graph_db
    """
    if node._id is None:
        return

    # Initialize visited set on first call
    if visited is None:
        visited = set()

    # Avoid cycles
    if node._id in visited:
        return
    visited.add(node._id)

    now = time.time()

    # Invalidate all calculated estimations for this node
    # (set invalidated_at on CalculatedEstimation nodes)
    for est, _ in node.estimations.all():
        if isinstance(est, CalculatedEstimation):
            est.invalidated_at = now
            est.save()

    # Find immediate scoring parents using directed relationship pattern.
    # Scoring parents are nodes whose score DEPENDS ON this node's score.
    #
    # SCORING DEPENDENCIES (edges that should propagate invalidation):
    # - Polarity (T/A/T+/T-/A+/A-): Component→WU (WU score depends on Component)
    # - Polarity (S+/S-): Component→Synthesis (Synthesis score depends on Component)
    # - BELONGS_TO_NEXUS: WU→Nexus (Nexus depends on WU)
    # - HAS_CYCLE: Nexus→Cycle (Cycle scores Nexus as child)
    # - HAS_WHEEL: Cycle→Wheel (Wheel depends on Cycle)
    # - TRANSITION_OF: Transition→Cycle/Wheel (Cycle/Wheel depends on Transition)
    # - IS_SPIRAL_OF: Transformation→WU, Spiral→Wheel (WU/Wheel depends on Transformation/Spiral)
    # - SYNTHESIS_OF: Synthesis→Transformation/Spiral (Transformation/Spiral depends on Synthesis)
    # - EXPLAINS: Rationale→Entity (Entity depends on Rationale)
    # - CRITIQUES: Critique→Rationale (Rationale depends on critique)
    #
    # NON-SCORING EDGES (should NOT propagate - these are structural, not scoring):
    # - IS_SOURCE_OF: Component→Transition (Transition doesn't use Component.R/P)
    # - IS_TARGET_OF: Transition→Component (Component doesn't use Transition.R/P)
    # - HAS_STATEMENT: Input→Component (derived output, not scoring input)
    # - ESTIMATES: Estimation→Entity (analytical artifact, not scoring dependency)
    # - PROVIDES: Rationale→Estimation (provenance, Rationale isn't scored)
    # - OPPOSITE_OF: Component↔Component (semantic opposition, not scoring)
    # - POSITIVE_SIDE_OF: Component→Component (semantic polarity, not scoring)
    # - NEGATIVE_SIDE_OF: Component→Component (semantic polarity, not scoring)
    # - SIMILAR_TO: Component→Component (semantic similarity, not scoring)
    query = """
        MATCH (child)-[rel]->(parent:Assessable)
        WHERE id(child) = $child_id
        AND NOT type(rel) IN ['HAS_STATEMENT', 'IS_SOURCE_OF', 'IS_TARGET_OF', 'ESTIMATES', 'PROVIDES', 'OPPOSITE_OF', 'POSITIVE_SIDE_OF', 'NEGATIVE_SIDE_OF', 'SIMILAR_TO']
        RETURN DISTINCT id(parent) as parent_id
    """

    try:
        results = list(graph_db.execute_and_fetch(query, {"child_id": node._id}))

        # Recursively invalidate each parent
        from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity as AE
        for record in results:
            parent_id = record["parent_id"]
            if parent_id not in visited:
                # Load parent and recursively invalidate
                parent = AE(_id=parent_id)
                parent.load(db=graph_db)
                if parent:
                    invalidate_node_and_parents(parent, visited=visited)
    except Exception:
        # Silent failure to avoid breaking the flow
        pass


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
        provider: Optional[Rationale] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> None:
        """
        Set an Estimation of specified type for a node (replacing any existing).

        This is not a true "upsert" (update-or-insert). Estimation nodes are
        content-identified by (type, value, target). If the value changes,
        the old estimation is deleted and a new one is created. If the value
        is the same, the existing estimation node is reused (deduplication).

        Automatically determines whether to invalidate parent scores:
        - Manual estimations (ProbabilityEstimation, RelevanceEstimation) → invalidate parents
        - Calculated estimations (Calculated*) → don't invalidate (these are TaroRank outputs)

        Args:
            node: AssessableEntity to set estimation for (must be committed)
            estimation_type: Type of estimation (any Estimation subclass)
            value: Estimation value (0.0-1.0) or None (None deletes the estimation)
            provider: Optional Rationale that provides this estimation (provenance)
            graph_db: Database connection (injected)

        Example:
            manager.upsert_estimation(node, ProbabilityEstimation, 0.8)  # Invalidates parents
            manager.upsert_estimation(node, CalculatedProbabilityEstimation, 0.75)  # No invalidation
            manager.upsert_estimation(node, ProbabilityEstimation, None)  # Deletes and invalidates
            manager.upsert_estimation(node, RelevanceEstimation, 0.9, provider=rationale)  # With provenance
        """
        # Determine if we should invalidate based on estimation type
        # Calculated estimations are TaroRank outputs, not inputs, so don't invalidate
        should_invalidate = not issubclass(estimation_type, CalculatedEstimation)

        if value is None:
            # Delete existing estimations of this type
            self._delete_estimations(node, estimation_type, graph_db)
            if should_invalidate:
                invalidate_node_and_parents(node)
            return

        # Check for existing estimation of this type connected to this node
        existing = self._get_scoring_estimation(node, estimation_type, graph_db)

        if existing:
            # Update existing - need to disconnect old and create new
            # (Estimations are immutable and target-specific, so we create new)
            old_value = existing.value
            if old_value != value:
                # Disconnect and delete old estimation (it's specific to this node)
                node.estimations.disconnect(existing)
                # Get or create estimation with new value (pass node as target)
                # Hash now includes target, so this creates a new estimation
                estimation = self._get_or_create_estimation(estimation_type, value, node, graph_db, provider)
                if should_invalidate:
                    invalidate_node_and_parents(node)
        else:
            # Get or create estimation (pass node as target)
            # Hash includes target, so each (type, value, target) tuple is unique
            estimation = self._get_or_create_estimation(estimation_type, value, node, graph_db, provider)
            if should_invalidate:
                invalidate_node_and_parents(node)

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
                if not isinstance(est, CalculatedEstimation):
                    should_invalidate = True
                    break
            # Delete ALL estimations
            self._delete_all_estimations(node, graph_db)
        else:
            # Clearing specific types - check if any are manual
            for estimation_type in estimation_types:
                if not issubclass(estimation_type, CalculatedEstimation):
                    should_invalidate = True
                self._delete_estimations(node, estimation_type, graph_db)

        # Invalidate if we cleared any manual estimations
        if should_invalidate:
            invalidate_node_and_parents(node)

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
        # Estimation points TO Entity via ESTIMATES
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
        This method looks up by these fields to reuse existing nodes.

        Note: We query by value and target relationship rather than hash
        because we need to find the node before computing its hash.

        Args:
            estimation_class: Type of estimation to create
            value: The estimation value
            target: The target entity this estimation is for
            graph_db: Database connection
            provider: Optional Rationale that provides this estimation (provenance)

        Returns:
            Estimation instance (either existing or newly created)
        """
        if target._id is None:
            # Target not persisted, can't lookup by relationship
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
            # Return existing node
            # Note: If provider is provided but estimation already exists,
            # we don't update the provider (estimation is identified by type+value+target)
            return result[0]["e"]

        # Create new (commit() will auto-connect target and provider)
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
        # Estimation points TO Entity via ESTIMATES
        # Use GQLAlchemy's label attribute, not Python class name
        label = estimation_class.label
        query = f"""
            MATCH (e:{label})-[:ESTIMATES]->(n)
            WHERE id(n) = $node_id
            DETACH DELETE e
        """
        graph_db.execute(query, {"node_id": node._id})
