"""
Repository for content-hash based node lookups.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING, TypeVar

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.mixins.forkable_mixin import ForkableMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode

T = TypeVar("T", bound="BaseNode")


class NodeRepository:
    """
    Repository for content-hash based node lookups.

    All queries are automatically scoped by sid (injected from DI context).

    Example:
        from dialectical_framework.graph.scope_context import scope

        with scope(brainstorm.sid):
            repo = NodeRepository()
            node = repo.find_by_hash("abc123...")  # Only searches within scope
    """

    @inject
    def find_by_hash(
        self,
        hash: str,
        node_type: Optional[type[T]] = None,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Optional[T]:
        """
        Find a node by hash or hash prefix within the current scope.

        Uses STARTS WITH matching, which works for both:
        - Full hash: exact match (single result)
        - Hash prefix: prefix match (may have multiple results)

        Args:
            hash: The hash or hash prefix to search for
            node_type: If provided, validates the node is of this type
            sid: Scope ID (injected from DI context)

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
            results = list(graph_db.execute_and_fetch(query, {"hash": hash, "sid": sid}))
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
            raise TypeError(
                f"Expected {node_type.__name__}, got {type(node).__name__}"
            )
        return node

    @inject
    def find_by_origin(
        self,
        origin_hash: str,
        node_type: Optional[type[T]] = None,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[BaseNode]:
        """
        Find all nodes that were cloned from a given origin.

        Args:
            origin_hash: The hash of the original node
            node_type: If provided, validates all nodes are of this type
            sid: Scope ID (injected from DI context)

        Returns:
            List of nodes that have this origin_hash

        Raises:
            TypeError: If node_type is provided and any found node is not of that type
        """
        if sid:
            query = """
                MATCH (n:Node {origin_hash: $origin, sid: $sid})
                RETURN n
            """
            results = list(graph_db.execute_and_fetch(query, {"origin": origin_hash, "sid": sid}))
        else:
            query = """
                MATCH (n:Node {origin_hash: $origin})
                RETURN n
            """
            results = list(graph_db.execute_and_fetch(query, {"origin": origin_hash}))

        nodes = [row["n"] for row in results]
        if node_type is not None:
            for node in nodes:
                if not isinstance(node, node_type):
                    raise TypeError(
                        f"Expected {node_type.__name__}, got {type(node).__name__}"
                    )
        return nodes

    def find_lineage(
        self,
        hash: str,
        node_type: Optional[type[T]] = None,
    ) -> list[BaseNode]:
        """
        Find the full lineage chain for a node (all ancestors via origin_hash).

        Args:
            hash: The hash of the node to trace
            node_type: If provided, validates all nodes in lineage are of this type

        Returns:
            List of nodes in lineage order (oldest first, node itself last)

        Raises:
            TypeError: If node_type is provided and any node in lineage is not of that type
        """
        lineage = []
        current_hash = hash

        while current_hash:
            node = self.find_by_hash(hash=current_hash)
            if node is None:
                break

            if node_type is not None and not isinstance(node, node_type):
                raise TypeError(
                    f"Expected {node_type.__name__}, got {type(node).__name__}"
                )

            lineage.insert(0, node)

            if isinstance(node, ForkableMixin):
                current_hash = node.origin_hash
                if current_hash == hash:
                    break
            else:
                break

        return lineage

    @inject
    def is_on_branch(
        self,
        node: BaseNode,
        branch: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if a node is on a given branch.

        Args:
            node: The node to check (must be a ForkableMixin)
            branch: The branch name to verify

        Returns:
            True if node is on the branch (is the tip or an ancestor of the tip)
        """
        if not isinstance(node, ForkableMixin):
            return False

        if node.branch == branch:
            return True

        # Use node's sid for scoped query
        if not hasattr(node, 'sid') or not node.sid:
            return False

        query = """
            MATCH (tip:Node {branch: $branch, sid: $sid})
            RETURN tip
        """
        results = list(graph_db.execute_and_fetch(query, {"branch": branch, "sid": node.sid}))

        if not results:
            return False

        tip = results[0]["tip"]

        if not isinstance(tip, ForkableMixin):
            return False

        current_hash = tip.origin_hash
        node_hash = node.hash

        while current_hash:
            if current_hash == node_hash:
                return True

            ancestor = self.find_by_hash(hash=current_hash)
            if ancestor is None or not isinstance(ancestor, ForkableMixin):
                break

            current_hash = ancestor.origin_hash

        return False
