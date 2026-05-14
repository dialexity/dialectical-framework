"""
Repository for Case node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.case import Case


class CaseRepository:
    """
    Repository for Case node queries.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_sid(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Optional[Case]:
        """
        Find the Case node for the current scope.

        Returns:
            The Case node if found, None otherwise
        """
        if not sid:
            return None

        query = """
        MATCH (c:Case {sid: $sid})
        RETURN c
        """
        results = list(graph_db.execute_and_fetch(query, {"sid": sid}))

        if not results:
            return None

        return results[0]["c"]

