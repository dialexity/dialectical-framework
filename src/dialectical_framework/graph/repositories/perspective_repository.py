"""
PerspectiveRepository for complex query operations and lifecycle management.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

import logging
from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

logger = logging.getLogger(__name__)

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
    def find_all_active(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Perspective]:
        """
        Find all non-discarded Perspectives in the current scope, ordered by commit time.

        Returns:
            List of active (non-discarded) Perspectives
        """
        if not sid:
            return []

        query = """
        MATCH (pp:Perspective {sid: $sid})
        WHERE pp.discarded IS NULL AND pp.hash IS NOT NULL
        RETURN pp
        ORDER BY pp.committed_at
        """
        try:
            results = list(graph_db.execute_and_fetch(query, {"sid": sid}))
            return [r["pp"] for r in results]
        except Exception:
            # Fail-soft (a read fault must not crash a live conversation) but
            # never SILENT: "the graph is empty" and "the query failed" lead to
            # opposite conclusions, and this list feeds the Advisor's context
            # dump. Swallowed, a fault degrades the Advisor to an arm with no
            # memory while every tool still reports success — observed in
            # `claim2-weak-r1`, where two cells recorded `anchor:ok` several
            # times over and then summarised the graph as `perspectives=0`.
            logger.exception("find_all_active failed for sid=%s", sid)
            return []

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
        """

        results = graph_db.execute_and_fetch(query, {"component_id": component._id})
        return [(result["pp"], result["rel_type"]) for result in results]

    @inject
    def find_by_statements(
        self,
        components: list[Statement],
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> dict[int, list[tuple[Perspective, str]]]:
        """Run `find_by_statement` for MANY components in one query.

        `Wheel._perspectives` asks this question once per endpoint of every edge — 2N
        round-trips for an N-perspective wheel — and then throws most answers away,
        because it already holds the cycle's `perspective_hashes` and filters against
        them. Batching does not change that filter; it only stops paying per component.
        In one k=4 `build_wheels` this shape was the single most expensive query in the
        run, and `_perspectives` is recomputed by ~20 call sites per wheel.

        Returns a map keyed by `component._id` (the graph's node id) holding that
        component's rows, so the CALLER keeps driving the iteration order — which is
        load-bearing: `_perspectives` order becomes `polar_segments` order, i.e. the
        wheel's arrangement.

        Rows for one component come back in the same order as the single-component
        query's, and that is what makes this substitutable — pinned differentially
        against the per-component path in `tests/test_perspectives_batched_lookup.py`,
        including a component that matches both legs at once.

        The explicit leg marker and sort are INSURANCE, not a tested claim: Memgraph
        already emits `UNION ALL`'s legs in order, so dropping the sort changes nothing
        observable today (verified by mutation). It is here because `UNION`'s dedup
        offers no such guarantee once more than one component is in flight, and the
        result order is load-bearing upstream. Dedup is reproduced in Python instead, in
        order, which is the part that would otherwise be lost by moving to `UNION ALL`.
        """
        # Deduplicated, order preserved. Endpoints repeat — each statement in a wheel's
        # chain is the source of one edge and the target of another.
        component_ids: list[int] = []
        asked: set[int] = set()
        for component in components:
            if component._id is None:
                continue
            # Same scope guard as the single-component form.
            if sid and component.sid != sid:
                continue
            if component._id not in asked:
                asked.add(component._id)
                component_ids.append(component._id)
        if not component_ids:
            return {}

        query = """
        // Aspect positions (T+, T-, A+, A-) directly on Perspective
        MATCH (c:Statement)-[r]->(pp:Perspective)
        WHERE id(c) IN $component_ids
        AND type(r) IN ['T_PLUS', 'T_MINUS', 'A_PLUS', 'A_MINUS']
        RETURN 0 AS leg, id(c) AS component_id, pp, type(r) AS rel_type

        UNION ALL

        // T and A positions via Polarity
        MATCH (c:Statement)-[r]->(p:Polarity)<-[:HAS_POLARITY]-(pp:Perspective)
        WHERE id(c) IN $component_ids
        AND type(r) IN ['T', 'A']
        RETURN 1 AS leg, id(c) AS component_id, pp, type(r) AS rel_type
        """

        legs: dict[int, list[tuple[int, Perspective, str]]] = {}
        for result in graph_db.execute_and_fetch(
            query, {"component_ids": component_ids}
        ):
            legs.setdefault(result["component_id"], []).append(
                (result["leg"], result["pp"], result["rel_type"])
            )

        found: dict[int, list[tuple[Perspective, str]]] = {}
        for component_id, rows in legs.items():
            # Stable, so the DB's order within a leg survives.
            rows.sort(key=lambda row: row[0])
            # `UNION ALL` above keeps duplicates that `UNION` would have dropped;
            # drop them here instead, keeping the first occurrence. Keyed on `_id`
            # rather than `hash` because that is what Cypher's own row dedup compares
            # (node identity), and because an uncommitted Perspective has no hash — two
            # distinct ones would collapse into a single row.
            seen: set[tuple[Optional[int], str]] = set()
            ordered: list[tuple[Perspective, str]] = []
            for _, pp, rel_type in rows:
                key = (pp._id, rel_type)
                if key in seen:
                    continue
                seen.add(key)
                ordered.append((pp, rel_type))
            found[component_id] = ordered

        return found

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


