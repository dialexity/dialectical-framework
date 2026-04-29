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
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.settings import Settings
    from dialectical_framework.graph.nodes.perspective import Perspective


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
        components: list[Statement],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> Optional[Wheel]:
        """
        Find a Wheel with exactly the given component sequence (rotation-invariant).

        Args:
            components: List of Statements in order
            sid: Case ID (injected from DI context)
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
            wheel_components = wheel.statements
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
            sid: Case ID (injected from DI context)

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

    @inject
    def find_by_layer(
        self,
        perspectives: list[Perspective],
        nexus: Optional[Nexus] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Wheel]:
        """
        Find all Wheels in the same layer (same Perspective set, any arrangement).

        A "layer" consists of all Wheels whose parent Cycles have exactly
        the same set of Perspectives (regardless of order).

        When nexus is provided, scopes to Wheels whose parent Cycle's
        Perspective hashes are all within the Nexus's Perspective set.

        This is used for probability normalization across competing alternatives.

        Args:
            perspectives: List of Perspectives defining the layer
            nexus: Optional Nexus to scope results to
            sid: Case ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of Wheel nodes in this layer
        """
        if not perspectives:
            return []

        pp_hashes = sorted([pp.hash for pp in perspectives])

        # Find all Wheels belonging to Cycles with exactly these Perspective hashes
        query = """
            MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel)
            WHERE w.sid = $sid
            AND size(c.perspective_hashes) = $hash_count
            AND ALL(h IN $pp_hashes WHERE h IN c.perspective_hashes)
        """
        params: dict = {
            "sid": sid,
            "pp_hashes": pp_hashes,
            "hash_count": len(pp_hashes),
        }

        if nexus is not None:
            nexus_pp_hashes = [pp.hash for pp, _ in nexus.perspectives.all()]
            query += "    AND ALL(h IN c.perspective_hashes WHERE h IN $nexus_pp_hashes)\n"
            params["nexus_pp_hashes"] = nexus_pp_hashes

        query += "    RETURN w"

        results = list(graph_db.execute_and_fetch(query, params))

        return [row["w"] for row in results]

    @inject
    def find_parent_wheels(
        self,
        wheel: Wheel,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
        settings: Settings = Provide[DI.settings],
    ) -> list[Wheel]:
        """
        Find all potential parent wheels for Transformation computation.

        Returns wheels that:
        - Have one fewer Perspective than this wheel
        - Have a Perspective set that is a subset of this wheel's Perspectives
        - Match the effective intent

        Args:
            wheel: The Wheel to find parents for
            graph_db: Graph database (injected)
            sid: Case ID (injected from DI context)

        Returns:
            List of parent Wheel nodes
        """
        from dialectical_framework.graph.nodes.wheel import Wheel as WheelNode

        wheel_pp_hashes = [pp.hash for pp in wheel._perspectives]
        if len(wheel_pp_hashes) <= 1:
            return []  # Layer 1 wheels have no parents

        effective_intent = wheel.get_effective_intent() or settings.cycle_preset
        wheel_pp_set = set(wheel_pp_hashes)
        target_layer = len(wheel_pp_hashes) - 1

        # Get the Cycle
        cycle_result = wheel.cycle.get()
        if not cycle_result:
            return []
        cycle_obj, _ = cycle_result

        # Query all wheels belonging to this Cycle, filter in Python
        query = """
        MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel)
        WHERE id(c) = $cycle_id AND w.sid = $sid
        RETURN w
        """
        results = list(graph_db.execute_and_fetch(query, {
            "cycle_id": cycle_obj._id,
            "sid": sid,
        }))

        parents: list[WheelNode] = []
        for row in results:
            candidate: WheelNode = row["w"]
            candidate_pp_hashes = [pp.hash for pp in candidate._perspectives]

            # Check layer match (one fewer Perspective)
            if len(candidate_pp_hashes) != target_layer:
                continue

            candidate_pp_set = set(candidate_pp_hashes)

            # Check if candidate's Perspectives are a subset of this wheel's Perspectives
            if candidate_pp_set.issubset(wheel_pp_set):
                # Check intent match
                candidate_intent = candidate.get_effective_intent() or settings.cycle_preset
                if candidate_intent == effective_intent:
                    parents.append(candidate)

        return parents
