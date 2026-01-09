"""
Invalidation utilities for graph-native assessable entities.

Provides functions to invalidate scores when structural changes occur
(e.g., new rationale connections) that aren't captured by EstimationManager.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Union, Optional

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity


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
        invalidate_node_and_parents(rationale)  # Uses DI for graph_db

        # Or with explicit graph_db (e.g., from EstimationManager)
        invalidate_node_and_parents(node, graph_db=db)
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

    now = datetime.now()

    # Invalidate this node
    node.score_invalidated_at = now
    node.save()

    # Find immediate parents using directed relationship pattern
    # All parent relationships use RelationshipTo() which creates outgoing edges (child→parent):
    # - WisdomUnit.wheel → WU→Wheel
    # - Transformation.wisdom_unit → Transformation→WU
    # - Transformation.ac_re → Transformation→WU(ac_re)
    # - Cycle/Spiral._wheel_as_* → Cycle/Spiral→Wheel
    # - Rationale.explanation → Rationale→Entity
    # - Rationale.critiques → RationaleA→RationaleB (critique→critiqued)
    #
    # IMPORTANT: Exclude HAS_STATEMENT to prevent crossing wheel boundaries
    query = """
        MATCH (child)-[rel]->(parent:AssessableEntity)
        WHERE id(child) = $child_id
        AND type(rel) <> 'HAS_STATEMENT'
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
                    invalidate_node_and_parents(parent, graph_db=graph_db, visited=visited)
    except Exception:
        # Silent failure to avoid breaking the flow
        pass
