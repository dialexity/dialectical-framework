"""
Repository for Wheel node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transformation import Transformation


class WheelRepository:
    """
    Repository for Wheel node queries.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @staticmethod
    def _get_canonical_signature(hashes: list[str]) -> str:
        """
        Get canonical signature for hash ordering (rotation-invariant).

        Args:
            hashes: List of hashes in order

        Returns:
            Canonical string signature (colon-joined, lex-smallest rotation)
        """
        if not hashes:
            return ""

        # Find canonical rotation (lexicographically smallest)
        rotations = [hashes[i:] + hashes[:i] for i in range(len(hashes))]
        canonical = min(rotations)
        return ":".join(canonical)

    @inject
    def find_by_component_sequence(
        self,
        components: list[DialecticalComponent],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> Optional[Wheel]:
        """
        Find a Wheel with exactly the given component sequence (rotation-invariant).

        Args:
            components: List of DialecticalComponents in order
            sid: Scope ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            Existing Wheel if found, None otherwise
        """
        from dialectical_framework.graph.nodes.wheel import Wheel

        if not components:
            return None

        comp_hashes = [c.hash for c in components]
        target_signature = self._get_canonical_signature(comp_hashes)

        # Query wheels that have the right number of transitions
        # A wheel with N components has N transitions (circular)
        query = """
            MATCH (w:Wheel)<-[:BELONGS_TO_CYCLE]-(t:Transition)
            WHERE w.sid = $sid
            WITH w, count(t) as trans_count
            WHERE trans_count = $expected_count
            RETURN w
        """
        results = list(graph_db.execute_and_fetch(query, {
            "sid": sid,
            "expected_count": len(comp_hashes),
        }))

        # Filter by canonical signature match
        for row in results:
            wheel: Wheel = row["w"]
            wheel_components = wheel.dialectical_components
            if wheel_components:
                wheel_hashes = [c.hash for c in wheel_components]
                wheel_signature = self._get_canonical_signature(wheel_hashes)
                if wheel_signature == target_signature:
                    return wheel

        return None

    @inject
    def get_transformations(
        self,
        wheel: Wheel,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Transformation]:
        """
        Get all Transformations belonging to a wheel's edges.

        Queries transformations that point to any of the wheel's edges
        via ACTION_REFLECTION relationship, scoped by sid.

        Args:
            wheel: The Wheel to get transformations for
            graph_db: Graph database (injected)
            sid: Scope ID (injected from DI context)

        Returns:
            List of Transformation nodes from all edges
        """
        from dialectical_framework.graph.nodes.transformation import Transformation as TransformationNode

        # Get edge IDs for this wheel
        edge_ids = [edge._id for edge in wheel.edges if edge._id is not None]
        if not edge_ids:
            return []

        # Query transformations pointing to these edges, scoped by sid
        query = """
        MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(t:Transition)
        WHERE id(t) IN $edge_ids AND tr.sid = $sid
        RETURN tr
        ORDER BY id(tr)
        """
        results = list(graph_db.execute_and_fetch(query, {
            "edge_ids": edge_ids,
            "sid": sid,
        }))

        all_transformations: list[TransformationNode] = []
        for row in results:
            tr = row.get("tr")
            if tr and isinstance(tr, TransformationNode):
                all_transformations.append(tr)
        return all_transformations
