"""
DialecticalComponentRepository for complex query operations.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class DialecticalComponentRepository:
    """
    Repository for DialecticalComponent query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_wisdom_unit(
        self,
        wisdom_unit: WisdomUnit,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[DialecticalComponent, str]]:
        """
        Find all DialecticalComponents belonging to a WisdomUnit with their aliases.

        Args:
            wisdom_unit: The WisdomUnit to query for
            sid: Scope ID (injected from DI context)

        Returns:
            List of tuples: (DialecticalComponent, alias)
        """
        if wisdom_unit._id is None:
            return []

        # Validate WU belongs to current scope
        if sid and wisdom_unit.sid != sid:
            return []

        query = """
        // Core positions (T, T+, T-, A, A+, A-) directly on WU
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(wu) = $wisdom_unit_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS']
        RETURN c, r.alias AS alias

        UNION

        // Synthesis positions (S+, S-) via Synthesis node
        MATCH (c:DialecticalComponent)-[r]->(synth:Synthesis)-[:SYNTHESIS_OF]->(wu:WisdomUnit)
        WHERE id(wu) = $wisdom_unit_id
        AND type(r) IN ['S_PLUS', 'S_MINUS']
        RETURN c, r.alias AS alias
        """

        results = graph_db.execute_and_fetch(query, {"wisdom_unit_id": wisdom_unit._id})
        return [(result["c"], result["alias"]) for result in results]

    @inject
    def get_vocabulary(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> set[DialecticalComponent]:
        """
        Get all DialecticalComponents in the current scope.

        Args:
            sid: Scope ID (injected from DI context)

        Returns:
            Set of DialecticalComponents with matching sid
        """
        if not sid:
            return set()

        query = """
        MATCH (c:DialecticalComponent)
        WHERE c.sid = $sid
        RETURN c
        """
        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return {record["c"] for record in results if record["c"] is not None}

    @inject
    def safe_delete(
        self,
        component: DialecticalComponent,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> bool:
        """
        Safely delete a DialecticalComponent if it's orphaned.

        A component is orphaned (safe to delete) if it has no structural connections:
        - Not connected to any WisdomUnit
        - Not connected to any Synthesis
        - Not connected to any Ideas or Input (via HAS_STATEMENT)
        - Not connected to any Transition

        Rationales attached to the component are deleted along with it.

        Args:
            component: The component to delete
            sid: Scope ID (injected from DI context)

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
        MATCH (c:DialecticalComponent)
        WHERE id(c) = $comp_id
        OPTIONAL MATCH (c)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(wu:WisdomUnit)
        OPTIONAL MATCH (c)-[:S_PLUS|S_MINUS]->(synth:Synthesis)
        OPTIONAL MATCH (c)<-[:HAS_STATEMENT]-(container)
        OPTIONAL MATCH (c)-[:SOURCE|TARGET]->(trans:Transition)
        OPTIONAL MATCH (c)<-[:SOURCE|TARGET]-(trans2:Transition)
        WITH c,
             count(DISTINCT wu) AS wu_count,
             count(DISTINCT synth) AS synth_count,
             count(DISTINCT container) AS container_count,
             count(DISTINCT trans) + count(DISTINCT trans2) AS trans_count
        RETURN wu_count + synth_count + container_count + trans_count AS connection_count
        """
        result = list(graph_db.execute_and_fetch(check_query, {"comp_id": component._id}))

        if not result or result[0]["connection_count"] > 0:
            return False

        # Delete rationales and the component
        delete_query = """
        MATCH (c:DialecticalComponent)
        WHERE id(c) = $comp_id
        OPTIONAL MATCH (rat:Rationale)-[:EXPLAINS]->(c)
        DETACH DELETE rat, c
        """
        graph_db.execute(delete_query, {"comp_id": component._id})
        return True

    def get_vocabulary_with_rationales(self) -> list[dict]:
        """
        Get committed vocabulary components with their rationales.

        Only returns committed components (those with hash).
        Uses best_rationale (highest-rated) for each component.

        Returns:
            List of dicts with: hash, statement, meaning, rejected, rationale
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
                "statement": comp.statement,
                "meaning": comp.meaning,
                "rejected": comp.rejected,
                "rationale": rationale_text,
            })

        return result
