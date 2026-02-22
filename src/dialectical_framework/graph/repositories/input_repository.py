"""
InputRepository for querying Input nodes.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input


class InputRepository:
    """
    Repository for Input query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def get_all(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Input]:
        """
        Get all Input nodes in the current scope.

        Args:
            sid: Scope ID (injected from DI context)

        Returns:
            List of Input nodes with matching sid
        """
        if not sid:
            return []

        query = """
        MATCH (i:Input)
        WHERE i.sid = $sid
        RETURN i
        """
        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return [record["i"] for record in results if record["i"] is not None]
