"""
DialecticalComponentRepository for complex query operations.

This repository separates data access logic from the DialecticalComponent node model,
keeping the model clean and declarative while centralizing complex queries.

Key concepts:
- **Vocabulary**: The set of DialecticalComponents available within a scope (sid)
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

    This class handles complex queries and traversals for DialecticalComponent nodes,
    separating data access logic from domain models following the Repository pattern.

    Example usage:
        from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository

        wu = WisdomUnit()
        wu.save()

        repo = DialecticalComponentRepository()
        components = repo.find_by_wisdom_unit(wu)
        for comp, alias in components:
            print(f"Component {comp.statement} has alias {alias}")
    """

    @inject
    def find_by_wisdom_unit(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[DialecticalComponent, str]]:
        """
        Find all DialecticalComponents belonging to a WisdomUnit with their aliases.

        Args:
            wisdom_unit: The WisdomUnit to query for
            graph_db: Database connection (injected via DI)

        Returns:
            List of tuples: (DialecticalComponent, alias)
            Example: [(comp1, "T"), (comp2, "T+"), (comp3, "A-")]
        """
        if wisdom_unit._id is None:
            return []

        # Two separate queries combined with UNION for Memgraph compatibility
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

        The scope (sid) is injected from the current context. Application layer
        sets scope via `with scope(brainstorm.sid):` before calling framework methods.

        Args:
            sid: Current scope ID (injected via DI from contextvar)
            graph_db: Database connection (injected via DI)

        Returns:
            Set of DialecticalComponents with matching sid

        Example:
            repo = DialecticalComponentRepository()

            # App layer sets scope:
            with scope(brainstorm.sid):
                vocab = repo.get_vocabulary()  # sid injected automatically
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
