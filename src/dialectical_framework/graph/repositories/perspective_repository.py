"""
PerspectiveRepository for complex query operations and lifecycle management.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.polarity import Polarity


class PerspectiveRepository:
    """
    Repository for Perspective query operations and lifecycle management.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def is_in_use_by_cycle(
        self,
        perspective: Perspective,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> bool:
        """
        Check if a Perspective's hash appears in any Cycle's perspective_hashes.

        A PP "in use" means it's part of committed downstream structures
        (Cycles → Wheels → Transformations) that depend on it structurally.

        Args:
            perspective: The committed Perspective to check

        Returns:
            True if this PP is referenced by at least one Cycle
        """
        if not perspective.is_committed:
            return False
        if sid and perspective.sid != sid:
            return False

        query = """
        MATCH (c:Cycle)
        WHERE c.sid = $sid AND $pp_hash IN c.perspective_hashes
        RETURN c LIMIT 1
        """
        results = list(graph_db.execute_and_fetch(
            query, {"sid": sid, "pp_hash": perspective.hash}
        ))
        return len(results) > 0

    @inject
    def find_by_polarity(
        self,
        polarity: Polarity,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Perspective]:
        """
        Find Perspectives that reference the given Polarity.

        Args:
            polarity: The Polarity (T-A pair) to query for
            sid: Case ID (injected from DI context)

        Returns:
            List of Perspectives connected to this Polarity
        """
        if polarity._id is None:
            return []

        # Validate polarity belongs to current scope
        if sid and polarity.sid != sid:
            return []

        query = """
        MATCH (pp:Perspective)-[:HAS_POLARITY]->(p:Polarity)
        WHERE id(p) = $polarity_id
        RETURN pp
        """

        results = graph_db.execute_and_fetch(query, {"polarity_id": polarity._id})
        return [result["pp"] for result in results]

    @inject
    def find_by_statement(
        self,
        component: Statement,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[Perspective, str]]:
        """
        Find all Perspectives that contain this component.

        Args:
            component: The Statement to query for
            sid: Case ID (injected from DI context)

        Returns:
            List of tuples: (Perspective, relationship_type)
        """
        if component._id is None:
            return []

        # Validate component belongs to current scope
        if sid and component.sid != sid:
            return []

        query = """
        // Aspect positions (T+, T-, A+, A-) directly on Perspective
        MATCH (c:Statement)-[r]->(pp:Perspective)
        WHERE id(c) = $component_id
        AND type(r) IN ['T_PLUS', 'T_MINUS', 'A_PLUS', 'A_MINUS']
        RETURN pp, type(r) AS rel_type

        UNION

        // T and A positions via Polarity
        MATCH (c:Statement)-[r]->(p:Polarity)<-[:HAS_POLARITY]-(pp:Perspective)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'A']
        RETURN pp, type(r) AS rel_type

        UNION

        // Synthesis positions (S+, S-) via Synthesis node
        MATCH (c:Statement)-[r]->(synth:Synthesis)-[:SYNTHESIS_OF]->(pp:Perspective)
        WHERE id(c) = $component_id
        AND type(r) IN ['S_PLUS', 'S_MINUS']
        RETURN pp, type(r) AS rel_type
        """

        results = graph_db.execute_and_fetch(query, {"component_id": component._id})
        return [(result["pp"], result["rel_type"]) for result in results]

    @inject
    def discard_uncommitted(
        self,
        perspective: Perspective,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> bool:
        """
        Discard an uncommitted Perspective node (and its relationships) from the graph.

        Only deletes if the PP is uncommitted and belongs to the current scope.
        Does NOT delete connected Statement or Polarity nodes (they may be shared).

        Args:
            perspective: The uncommitted Perspective to discard

        Returns:
            True if deleted, False if not eligible (committed or wrong scope)
        """
        if perspective._id is None:
            return False
        if perspective.is_committed:
            return False
        if sid and perspective.sid != sid:
            return False

        graph_db.execute(
            "MATCH (n) WHERE id(n) = $node_id DETACH DELETE n",
            {"node_id": perspective._id},
        )
        return True


