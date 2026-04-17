"""
Repository for Cycle node queries.

All queries are scoped by case_id (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective


class CycleRepository:
    """
    Repository for Cycle node queries.

    All queries are automatically scoped by case_id (injected from DI context).
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
    def find_by_perspectives(
        self,
        perspectives: list[Perspective],
        exact_order: bool = True,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> list[Cycle]:
        """
        Find Cycles containing the given Perspectives.

        Args:
            perspectives: List of Perspectives to search for
            exact_order: If True, only return cycles with exactly these Perspectives
                        in the same order (rotation-invariant).
                        If False, return cycles containing any of these Perspectives.
            case_id: Case ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of matching Cycle nodes
        """
        from dialectical_framework.graph.nodes.cycle import Cycle

        if not perspectives:
            return []

        pp_hashes = [pp.hash for pp in perspectives]

        if exact_order:
            # Query cycles with exactly the same number of Perspectives
            # Then filter by signature match in Python
            query = """
                MATCH (c:Cycle)
                WHERE c.case_id = $case_id
                AND size(c.perspective_hashes) = $hash_count
                AND ALL(h IN $pp_hashes WHERE h IN c.perspective_hashes)
                RETURN c
            """
            results = list(graph_db.execute_and_fetch(query, {
                "case_id": case_id,
                "pp_hashes": pp_hashes,
                "hash_count": len(pp_hashes),
            }))

            # Filter by canonical signature (rotation-invariant)
            target_signature = self._get_canonical_signature(pp_hashes)
            matching_cycles = []
            for row in results:
                cycle: Cycle = row["c"]
                cycle_signature = self._get_canonical_signature(cycle.perspective_hashes)
                if cycle_signature == target_signature:
                    matching_cycles.append(cycle)

            return matching_cycles
        else:
            # Return cycles containing ANY of these Perspectives
            query = """
                MATCH (c:Cycle)
                WHERE c.case_id = $case_id
                AND ANY(h IN $pp_hashes WHERE h IN c.perspective_hashes)
                RETURN c
            """
            results = list(graph_db.execute_and_fetch(query, {
                "case_id": case_id,
                "pp_hashes": pp_hashes,
            }))

            return [row["c"] for row in results]

    @inject
    def find_by_layer(
        self,
        perspectives: list[Perspective],
        nexus: Optional[Nexus] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> list[Cycle]:
        """
        Find all Cycles in the same layer (same Perspective set, any ordering).

        A "layer" consists of all Cycles with exactly the same set of
        Perspectives (regardless of order).

        When nexus is provided, scopes to Cycles whose Perspective hashes are all
        within the Nexus's Perspective set (excludes Cycles from other Nexuses
        that share some Perspectives).

        Args:
            perspectives: List of Perspectives defining the layer
            nexus: Optional Nexus to scope results to
            case_id: Case ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of Cycle nodes in this layer
        """
        from dialectical_framework.graph.nodes.cycle import Cycle

        if not perspectives:
            return []

        pp_hashes = sorted([pp.hash for pp in perspectives])  # Sort for set comparison

        query = """
            MATCH (c:Cycle)
            WHERE c.case_id = $case_id
            AND size(c.perspective_hashes) = $hash_count
            AND ALL(h IN $pp_hashes WHERE h IN c.perspective_hashes)
        """
        params: dict = {
            "case_id": case_id,
            "pp_hashes": pp_hashes,
            "hash_count": len(pp_hashes),
        }

        if nexus is not None:
            nexus_pp_hashes = [pp.hash for pp, _ in nexus.perspectives.all()]
            query += "    AND ALL(h IN c.perspective_hashes WHERE h IN $nexus_pp_hashes)\n"
            params["nexus_pp_hashes"] = nexus_pp_hashes

        query += "    RETURN c"

        results = list(graph_db.execute_and_fetch(query, params))

        return [row["c"] for row in results]
