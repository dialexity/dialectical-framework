"""
Repository for content-hash based node lookups.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, TypeVar, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode

T = TypeVar("T", bound="BaseNode")


class NodeRepository:
    """
    Repository for content-hash based node lookups.

    All queries are automatically scoped by sid (injected from DI context).

    Example:
        from dialectical_framework.graph.scope_context import scope

        with scope(case.sid):
            repo = NodeRepository()
            node = repo.find_by_hash("abc123...")  # Only searches within scope
            nodes = repo.find_by_hashes(["abc...", "def..."])  # Batch lookup
    """

    @inject
    def find_by_hashes(
        self,
        hashes: list[str],
        node_type: type[T] | None = None,
        sid: str | None = Provide[DI.sid],
        graph_db: Memgraph | Neo4j = Provide[DI.graph_db],
    ) -> list[T]:
        """
        Find nodes by a list of full hashes within the current scope.

        Silently skips hashes that don't match any node.

        Args:
            hashes: List of full content-addressable hashes
            node_type: If provided, filters to only nodes of this type
            sid: Case ID (injected from DI context)

        Returns:
            List of matching nodes
        """
        if not sid or not hashes:
            return []

        if node_type:
            label = node_type.__name__
            query = f"""
                MATCH (n:{label})
                WHERE n.hash IN $hashes AND n.sid = $sid
                RETURN n
            """
        else:
            query = """
                MATCH (n:Node)
                WHERE n.hash IN $hashes AND n.sid = $sid
                RETURN n
            """

        results = list(
            graph_db.execute_and_fetch(query, {"hashes": hashes, "sid": sid})
        )
        return [record["n"] for record in results if record["n"] is not None]

    @inject
    def find_by_hash(
        self,
        hash: str,
        node_type: Optional[type[T]] = None,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Optional[T]:
        """
        Find a node by hash or hash prefix within the current scope.

        Uses STARTS WITH matching, which works for both:
        - Full hash: exact match (single result)
        - Hash prefix: prefix match (may have multiple results)

        Args:
            hash: The hash or hash prefix to search for
            node_type: If provided, validates the node is of this type
            sid: Case ID (injected from DI context)

        Returns:
            The node if exactly one match found, None if no matches

        Raises:
            ValueError: If multiple nodes match (ambiguous prefix)
            TypeError: If node_type is provided and the found node is not of that type
        """
        if sid:
            query = """
                MATCH (n:Node)
                WHERE n.hash STARTS WITH $hash AND n.sid = $sid
                RETURN n
            """
            results = list(
                graph_db.execute_and_fetch(query, {"hash": hash, "sid": sid})
            )
        else:
            query = """
                MATCH (n:Node)
                WHERE n.hash STARTS WITH $hash
                RETURN n
            """
            results = list(graph_db.execute_and_fetch(query, {"hash": hash}))

        if not results:
            return None

        if len(results) > 1:
            raise ValueError(
                f"Ambiguous hash '{hash}': matches {len(results)} nodes. "
                f"Use a longer prefix."
            )

        node = results[0]["n"]
        if node_type is not None and not isinstance(node, node_type):
            raise TypeError(f"Expected {node_type.__name__}, got {type(node).__name__}")
        return node
