"""
DecisionRepository for Decision query operations.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.decision import Decision


class DecisionRepository:
    """
    Repository for Decision query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_all_active(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Decision]:
        """
        Find all non-discarded Decisions in the current scope, ordered by
        commit time (the decision timestamp).

        Returns:
            List of active (non-discarded) Decisions
        """
        if not sid:
            return []

        query = """
        MATCH (d:Decision {sid: $sid})
        WHERE d.discarded IS NULL AND d.hash IS NOT NULL
        RETURN d
        ORDER BY d.committed_at
        """
        try:
            results = list(graph_db.execute_and_fetch(query, {"sid": sid}))
            return [r["d"] for r in results]
        except Exception:
            return []

    @inject
    def find_all(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Decision]:
        """
        Find all committed Decisions in the current scope, including
        discarded ones (for inspection/history), ordered by commit time.

        Returns:
            List of all committed Decisions
        """
        if not sid:
            return []

        query = """
        MATCH (d:Decision {sid: $sid})
        WHERE d.hash IS NOT NULL
        RETURN d
        ORDER BY d.committed_at
        """
        try:
            results = list(graph_db.execute_and_fetch(query, {"sid": sid}))
            return [r["d"] for r in results]
        except Exception:
            return []
