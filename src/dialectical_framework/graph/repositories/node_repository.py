"""
Repository for content-hash based node lookups.

Provides git-style short prefix lookup for nodes.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.mixins.forkable_mixin import ForkableMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode


class NodeRepository:
    """
    Repository for content-hash based node lookups.

    Provides methods to find nodes by their hash or a prefix thereof,
    similar to how git allows short commit hashes.

    Example:
        repo = NodeRepository()

        # Full hash lookup
        node = repo.find_by_hash("abc123def456...")

        # Short prefix lookup (git-style)
        node = repo.find_by_prefix("abc123d")  # At least 7 chars
    """

    @inject
    def find_by_hash(
        self,
        hash: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Optional[BaseNode]:
        """
        Find a node by its exact hash.

        Args:
            hash: The full hash to search for

        Returns:
            The node if found, None otherwise
        """
        query = """
            MATCH (n:Node {hash: $hash})
            RETURN n
        """
        results = list(graph_db.execute_and_fetch(query, {"hash": hash}))
        if results:
            return results[0]["n"]
        return None

    @inject
    def find_by_prefix(
        self,
        prefix: str,
        min_length: int = 7,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Optional[BaseNode]:
        """
        Find a node by hash prefix (git-style short hash lookup).

        Args:
            prefix: The prefix of the hash (minimum 7 characters)
            min_length: Minimum prefix length required (default 7, like git)

        Returns:
            The node if exactly one match found, None otherwise

        Raises:
            ValueError: If prefix is too short
            ValueError: If multiple nodes match the prefix (ambiguous)

        Example:
            # If node has hash "abc123def456789..."
            node = repo.find_by_prefix("abc123d")  # Works
            node = repo.find_by_prefix("abc")      # Raises ValueError (too short)
        """
        if len(prefix) < min_length:
            raise ValueError(
                f"Prefix must be at least {min_length} characters, got {len(prefix)}"
            )

        # Use STARTS WITH for prefix matching
        query = """
            MATCH (n:Node)
            WHERE n.hash STARTS WITH $prefix
            RETURN n
        """
        results = list(graph_db.execute_and_fetch(query, {"prefix": prefix}))

        if not results:
            return None

        if len(results) > 1:
            raise ValueError(
                f"Ambiguous prefix '{prefix}': matches {len(results)} nodes. "
                f"Use a longer prefix."
            )

        return results[0]["n"]

    @inject
    def find_by_origin(
        self,
        origin_hash: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[BaseNode]:
        """
        Find all nodes that were cloned from a given origin.

        Args:
            origin_hash: The hash of the original node

        Returns:
            List of nodes that have this origin_hash
        """
        query = """
            MATCH (n:Node {origin_hash: $origin})
            RETURN n
        """
        results = list(graph_db.execute_and_fetch(query, {"origin": origin_hash}))
        return [row["n"] for row in results]

    @inject
    def find_lineage(
        self,
        hash: str,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[BaseNode]:
        """
        Find the full lineage chain for a node (all ancestors via origin_hash).

        Traces back through origin_hash to find all ancestor nodes.

        Args:
            hash: The hash of the node to trace

        Returns:
            List of nodes in lineage order (oldest first, node itself last)
        """
        lineage = []
        current_hash = hash

        while current_hash:
            node = self.find_by_hash(current_hash)
            if node is None:
                break

            lineage.insert(0, node)  # Add to front (oldest first)

            # Move to parent - only ForkableMixin nodes have origin_hash
            if isinstance(node, ForkableMixin):
                current_hash = node.origin_hash
                if current_hash == hash:
                    break  # Prevent infinite loop (shouldn't happen but be safe)
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

        Branch is a mutable pointer that only lives on the tip of a lineage chain.
        To check if a node is "on" a branch, we need to:
        1. Find the branch tip (node with branch == requested_branch)
        2. Walk backward via origin_hash to collect the lineage
        3. Check if the requested node's hash is in that lineage

        Args:
            node: The node to check (must be a ForkableMixin)
            branch: The branch name to verify

        Returns:
            True if node is on the branch (is the tip or an ancestor of the tip)
        """
        if not isinstance(node, ForkableMixin):
            return False

        # Check if this node IS the branch tip
        if node.branch == branch:
            return True

        # Node is not the tip - find the tip and check if node is an ancestor
        # Find branch tip: node with this branch label in the same scope
        query = """
            MATCH (tip:Node {branch: $branch, sid: $sid})
            RETURN tip
        """
        results = list(graph_db.execute_and_fetch(query, {"branch": branch, "sid": node.sid}))

        if not results:
            # No tip found with this branch - node cannot be on it
            return False

        tip = results[0]["tip"]

        # Walk backward from tip via origin_hash to check if node is in lineage
        if not isinstance(tip, ForkableMixin):
            return False

        current_hash = tip.origin_hash
        node_hash = node.hash

        while current_hash:
            if current_hash == node_hash:
                return True

            ancestor = self.find_by_hash(current_hash)
            if ancestor is None or not isinstance(ancestor, ForkableMixin):
                break

            current_hash = ancestor.origin_hash

        return False
