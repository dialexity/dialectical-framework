"""
Repository for Cycle node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class CycleRepository:
    """
    Repository for Cycle node queries.

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
    def find_by_wisdom_units(
        self,
        wisdom_units: list[WisdomUnit],
        exact_order: bool = True,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Cycle]:
        """
        Find Cycles containing the given WisdomUnits.

        Args:
            wisdom_units: List of WisdomUnits to search for
            exact_order: If True, only return cycles with exactly these WUs
                        in the same order (rotation-invariant).
                        If False, return cycles containing any of these WUs.
            sid: Scope ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of matching Cycle nodes
        """
        from dialectical_framework.graph.nodes.cycle import Cycle

        if not wisdom_units:
            return []

        wu_hashes = [wu.hash for wu in wisdom_units]

        if exact_order:
            # Query cycles with exactly the same number of WUs
            # Then filter by signature match in Python
            query = """
                MATCH (c:Cycle)
                WHERE c.sid = $sid
                AND size(c.wisdom_unit_hashes) = $hash_count
                AND ALL(h IN $wu_hashes WHERE h IN c.wisdom_unit_hashes)
                RETURN c
            """
            results = list(graph_db.execute_and_fetch(query, {
                "sid": sid,
                "wu_hashes": wu_hashes,
                "hash_count": len(wu_hashes),
            }))

            # Filter by canonical signature (rotation-invariant)
            target_signature = self._get_canonical_signature(wu_hashes)
            matching_cycles = []
            for row in results:
                cycle: Cycle = row["c"]
                cycle_signature = self._get_canonical_signature(cycle.wisdom_unit_hashes)
                if cycle_signature == target_signature:
                    matching_cycles.append(cycle)

            return matching_cycles
        else:
            # Return cycles containing ANY of these WUs
            query = """
                MATCH (c:Cycle)
                WHERE c.sid = $sid
                AND ANY(h IN $wu_hashes WHERE h IN c.wisdom_unit_hashes)
                RETURN c
            """
            results = list(graph_db.execute_and_fetch(query, {
                "sid": sid,
                "wu_hashes": wu_hashes,
            }))

            return [row["c"] for row in results]

    @inject
    def find_by_layer(
        self,
        wisdom_units: list[WisdomUnit],
        nexus: Optional[Nexus] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Cycle]:
        """
        Find all Cycles in the same layer (same WU set, any ordering).

        A "layer" consists of all Cycles with exactly the same set of
        WisdomUnits (regardless of order).

        When nexus is provided, scopes to Cycles whose WU hashes are all
        within the Nexus's WU set (excludes Cycles from other Nexuses
        that share some WUs).

        Args:
            wisdom_units: List of WisdomUnits defining the layer
            nexus: Optional Nexus to scope results to
            sid: Scope ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of Cycle nodes in this layer
        """
        from dialectical_framework.graph.nodes.cycle import Cycle

        if not wisdom_units:
            return []

        wu_hashes = sorted([wu.hash for wu in wisdom_units])  # Sort for set comparison

        query = """
            MATCH (c:Cycle)
            WHERE c.sid = $sid
            AND size(c.wisdom_unit_hashes) = $hash_count
            AND ALL(h IN $wu_hashes WHERE h IN c.wisdom_unit_hashes)
        """
        params: dict = {
            "sid": sid,
            "wu_hashes": wu_hashes,
            "hash_count": len(wu_hashes),
        }

        if nexus is not None:
            nexus_wu_hashes = [wu.hash for wu, _ in nexus.wisdom_units.all()]
            query += "    AND ALL(h IN c.wisdom_unit_hashes WHERE h IN $nexus_wu_hashes)\n"
            params["nexus_wu_hashes"] = nexus_wu_hashes

        query += "    RETURN c"

        results = list(graph_db.execute_and_fetch(query, params))

        return [row["c"] for row in results]
