"""
InputRepository for querying Input nodes.

All queries are scoped by case_id (injected from DI context) to prevent cross-user data leaks.
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

    All queries are automatically scoped by case_id (injected from DI context).
    """

    # TODO: Inputs that are referencing DialecticalComponent nodes via dx:// should be excluded I guess, Rationales are ok?
    @inject
    def get_all(
        self,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Input]:
        """
        Get all Input nodes in the current scope.

        Args:
            case_id: Case ID (injected from DI context)

        Returns:
            List of Input nodes with matching case_id
        """
        if not case_id:
            return []

        query = """
        MATCH (i:Input)
        WHERE i.case_id = $case_id
        RETURN i
        """
        results = graph_db.execute_and_fetch(query, {"case_id": case_id})
        return [record["i"] for record in results if record["i"] is not None]
