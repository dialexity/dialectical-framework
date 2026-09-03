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
        Find nodes by a list of hashes or hash prefixes within the current scope.

        Prefix matching, exactly as `find_by_hash` does — because a hash the
        framework hands out must be usable to look the node back up, and the
        framework deliberately hands out both forms: full on creation, then
        `short_hash` everywhere it is rendered into a prompt, to save tokens.

        This used to match on equality (`n.hash IN $hashes`), which made it
        unreachable for the short form and broke `ingest` outright: it reported
        `short_hash` and passed that same 7-char string here, matched nothing,
        and then reported success with "No tensions extracted" — advising the
        model to stop ingesting. `anchor` shared the bug more quietly, losing
        its inputs' provenance edges without saying so.

        Hashes matching no node are skipped, not raised: a batch caller asking
        for several inputs should not lose all of them because one went away.
        Callers that need to know compare the returned count against what they
        asked for — `SurfaceTheses` and `AnchorTheses` both do.

        Args:
            hashes: Full hashes or unambiguous prefixes, mixed freely
            node_type: If provided, filters to only nodes of this type
            sid: Case ID (injected from DI context)

        Returns:
            Matching nodes, deduplicated, in the order their hashes were
            requested. Ordered on purpose: these nodes are joined into prompts,
            so a stable request must render a stable prompt or it costs a
            provider prefix-cache miss and makes runs non-reproducible.

        Raises:
            ValueError: If a single prefix matches more than one node. Loud
                rather than silent for the same reason as `find_by_hash`:
                quietly substituting some other node's content into an analysis
                is worse than refusing to guess.
        """
        if not sid or not hashes:
            return []

        label = node_type.__name__ if node_type else "Node"
        # UNWIND rather than `any(h IN $hashes ...)` so the matching prefix comes
        # back with the node: without it an ambiguous prefix is undetectable.
        query = f"""
            UNWIND $hashes AS prefix
            MATCH (n:{label})
            WHERE n.sid = $sid AND n.hash IS NOT NULL AND n.hash STARTS WITH prefix
            RETURN prefix, n
        """
        results = list(
            graph_db.execute_and_fetch(query, {"hashes": hashes, "sid": sid})
        )

        by_prefix: dict[str, list[T]] = {}
        for record in results:
            node = record["n"]
            if node is None:
                continue
            by_prefix.setdefault(record["prefix"], []).append(node)

        ambiguous = {p: len(ns) for p, ns in by_prefix.items() if len(ns) > 1}
        if ambiguous:
            detail = ", ".join(
                f"'{p}' matches {count} nodes" for p, count in sorted(ambiguous.items())
            )
            raise ValueError(f"Ambiguous hash prefix: {detail}. Use a longer prefix.")

        ordered: list[T] = []
        seen: set[str] = set()
        for prefix in hashes:
            for node in by_prefix.get(prefix, ()):
                if node.hash not in seen:
                    seen.add(node.hash)
                    ordered.append(node)
        return ordered

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

    @inject
    def delete_explanation_rationales(
        self,
        node: BaseNode,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[str]:
        """
        Delete all Rationales that EXPLAIN the given node (with their critiques).

        Used to replace prior analytical explanations before persisting fresh
        ones (e.g. re-estimation of causality). Critique rationales attached
        to the deleted rationales are removed as well.

        Args:
            node: The explained node (must be saved and in current scope)
            sid: Case ID (injected from DI context)

        Returns:
            Hashes of the deleted Rationale nodes (for event emission)
        """
        if node._id is None:
            return []

        # Validate node belongs to current scope
        if sid and node.sid != sid:
            return []

        query = """
        MATCH (rat:Rationale)-[:EXPLAINS]->(n)
        WHERE id(n) = $node_id
        OPTIONAL MATCH (crit:Rationale)-[:CRITIQUES]->(rat)
        WITH collect(DISTINCT rat) + collect(DISTINCT crit) AS to_delete
        UNWIND to_delete AS r
        WITH DISTINCT r, r.hash AS rat_hash
        DETACH DELETE r
        RETURN rat_hash
        """
        results = list(graph_db.execute_and_fetch(query, {"node_id": node._id}))
        return [r["rat_hash"] for r in results if r["rat_hash"] is not None]
