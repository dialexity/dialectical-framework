"""
StatementRepository for complex query operations.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.perspective import Perspective


class StatementRepository:
    """
    Repository for Statement query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_perspective(
        self,
        perspective: Perspective,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[Statement, str]]:
        """
        Find all Statements belonging to a Perspective with their aliases.

        Args:
            perspective: The Perspective to query for
            sid: Case ID (injected from DI context)

        Returns:
            List of tuples: (Statement, alias)
        """
        if perspective._id is None:
            return []

        # Validate Perspective belongs to current scope
        if sid and perspective.sid != sid:
            return []

        query = """
        // Aspect positions (T+, T-, A+, A-) directly on Perspective
        MATCH (c:Statement)-[r]->(pp:Perspective)
        WHERE id(pp) = $perspective_id
        AND type(r) IN ['T_PLUS', 'T_MINUS', 'A_PLUS', 'A_MINUS']
        RETURN c, r.alias AS alias

        UNION

        // T and A positions via Polarity
        MATCH (pp:Perspective)-[:HAS_POLARITY]->(pol:Polarity)<-[r]-(c:Statement)
        WHERE id(pp) = $perspective_id
        AND type(r) IN ['T', 'A']
        RETURN c, r.alias AS alias
        """

        results = graph_db.execute_and_fetch(query, {"perspective_id": perspective._id})
        return [(result["c"], result["alias"]) for result in results]

    @inject
    def get_vocabulary(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> set[Statement]:
        """
        Get all Statements in the current scope.

        Args:
            sid: Case ID (injected from DI context)

        Returns:
            Set of Statements with matching sid
        """
        if not sid:
            return set()

        query = """
        MATCH (c:Statement)
        WHERE c.sid = $sid
        RETURN c
        """
        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return {record["c"] for record in results if record["c"] is not None}

    @inject
    def safe_delete(
        self,
        component: Statement,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> bool:
        """
        Safely delete a Statement if it's orphaned.

        A statement is orphaned (safe to delete) if it has no structural connections:
        - Not connected to any Perspective
        - Not connected to any Synthesis
        - Not connected to any Ideas or Input (via HAS_STATEMENT)
        - Not connected to any Transition

        Rationales attached to the statement are deleted along with it.

        Args:
            component: The statement to delete
            sid: Case ID (injected from DI context)

        Returns:
            True if deleted, False if not orphaned or wrong scope
        """
        if component._id is None:
            return False

        # Validate component belongs to current scope
        if sid and component.sid != sid:
            return False

        # Check if orphaned (no structural connections)
        check_query = """
        MATCH (c:Statement)
        WHERE id(c) = $comp_id
        OPTIONAL MATCH (c)-[:T|A]->(pol:Polarity)
        OPTIONAL MATCH (c)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(pp:Perspective)
        OPTIONAL MATCH (c)-[:S_PLUS|S_MINUS]->(synth:Synthesis)
        OPTIONAL MATCH (c)<-[:HAS_STATEMENT]-(container)
        OPTIONAL MATCH (c)-[:IS_SOURCE_OF]->(trans:Transition)
        OPTIONAL MATCH (c)<-[:IS_TARGET_OF]-(trans2:Transition)
        WITH c,
             count(DISTINCT pol) AS pol_count,
             count(DISTINCT pp) AS pp_count,
             count(DISTINCT synth) AS synth_count,
             count(DISTINCT container) AS container_count,
             count(DISTINCT trans) + count(DISTINCT trans2) AS trans_count
        RETURN pol_count + pp_count + synth_count + container_count + trans_count AS connection_count
        """
        result = list(graph_db.execute_and_fetch(check_query, {"comp_id": component._id}))

        if not result or result[0]["connection_count"] > 0:
            return False

        # Delete rationales and the statement
        delete_query = """
        MATCH (c:Statement)
        WHERE id(c) = $comp_id
        OPTIONAL MATCH (rat:Rationale)-[:EXPLAINS]->(c)
        DETACH DELETE rat, c
        """
        graph_db.execute(delete_query, {"comp_id": component._id})
        return True

    @inject
    def find_unconnected(
        self,
        limit: int = 50,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Statement]:
        """
        Find Statements not connected to any Polarity or Perspective position.

        These are "orphan" statements that haven't been placed into the
        dialectical structure yet.

        Args:
            limit: Maximum number of results
            sid: Case ID (injected from DI context)

        Returns:
            List of unconnected, non-discarded Statements
        """
        if not sid:
            return []

        query = """
        MATCH (s:Statement {sid: $sid})
        WHERE s.discarded IS NULL
        AND NOT (s)-[:T]->(:Polarity)
        AND NOT (s)-[:A]->(:Polarity)
        AND NOT (s)-[:T_PLUS]->(:Perspective)
        AND NOT (s)-[:T_MINUS]->(:Perspective)
        AND NOT (s)-[:A_PLUS]->(:Perspective)
        AND NOT (s)-[:A_MINUS]->(:Perspective)
        RETURN s
        ORDER BY s.committed_at
        LIMIT $limit
        """
        try:
            results = list(graph_db.execute_and_fetch(query, {"sid": sid, "limit": limit}))
            return [r["s"] for r in results]
        except Exception:
            return []

    def get_vocabulary_with_rationales(self) -> list[dict]:
        """
        Get committed vocabulary components with their rationales.

        Only returns committed components (those with hash).
        Uses best_rationale (highest-rated) for each component.

        Returns:
            List of dicts with: hash, statement, meaning, discarded, rationale
        """
        vocab = self.get_vocabulary()

        result = []
        for comp in vocab:
            # Only include committed components
            if not comp.is_committed:
                continue

            best = comp.best_rationale
            rationale_text = best.text if best else ""

            result.append({
                "hash": comp.hash,
                "statement": comp.text,
                "meaning": comp.meaning,
                "discarded": comp.discarded,
                "rationale": rationale_text,
            })

        return result
