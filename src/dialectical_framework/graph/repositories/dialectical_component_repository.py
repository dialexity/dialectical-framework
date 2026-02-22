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
