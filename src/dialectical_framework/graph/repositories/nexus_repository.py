"""
Repository for Nexus node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus


class NexusRepository:
    """
    Repository for Nexus node queries.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_hash_prefix(
        self,
        hash_prefix: str,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Optional[Nexus]:
        """
        Find a Nexus by hash or hash prefix within the current scope.

        Args:
            hash_prefix: The hash or hash prefix to search for

        Returns:
            The Nexus if exactly one match found, None if no matches

        Raises:
            ValueError: If multiple Nexuses match (ambiguous prefix)
        """
        if not sid:
            return None

        query = """
        MATCH (n:Nexus)
        WHERE n.hash STARTS WITH $hash AND n.sid = $sid
        RETURN n
        """
        results = list(graph_db.execute_and_fetch(query, {"hash": hash_prefix, "sid": sid}))

        if not results:
            return None

        if len(results) > 1:
            raise ValueError(
                f"Ambiguous nexus hash '{hash_prefix}': "
                f"matches {len(results)} nexuses"
            )

        return results[0]["n"]

    @inject
    def find_all(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Nexus]:
        """
        Find all Nexus nodes in the current scope.

        Returns:
            List of Nexus nodes
        """
        if not sid:
            return []

        query = """
        MATCH (n:Nexus {sid: $sid})
        RETURN n
        """
        results = list(graph_db.execute_and_fetch(query, {"sid": sid}))
        return [r["n"] for r in results]
