"""
Scope status tool for the Orchestrator.

Reports counts of all node types within the current sid scope.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import BaseTool

from dialectical_framework.enums.di import DI


class GetScopeStatus(BaseTool):
    """
    Show counts of all node types in the current scope.

    Returns a summary of how many Inputs, Statements, Perspectives,
    Cycles, Wheels, and Transformations exist in this scope.
    Use this to get a quick overview of what has been built so far.
    """

    @inject
    async def call(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
        """Query node counts within the current scope."""
        query = """
        MATCH (c:Case {sid: $sid})
        OPTIONAL MATCH (c)-[:HAS_INPUT]->(i:Input)
        WITH c, count(i) as input_count
        OPTIONAL MATCH (s:Statement {sid: $sid}) WHERE NOT coalesce(s.rejected, false)
        WITH c, input_count, count(s) as stmt_count
        OPTIONAL MATCH (pp:Perspective {sid: $sid})
        WITH c, input_count, stmt_count, count(pp) as pp_count
        OPTIONAL MATCH (cy:Cycle {sid: $sid})
        WITH c, input_count, stmt_count, pp_count, count(cy) as cycle_count
        OPTIONAL MATCH (w:Wheel {sid: $sid})
        WITH c, input_count, stmt_count, pp_count, cycle_count, count(w) as wheel_count
        OPTIONAL MATCH (tr:Transformation {sid: $sid})
        RETURN input_count, stmt_count, pp_count, cycle_count, wheel_count, count(tr) as tr_count
        """

        try:
            results = list(graph_db.execute_and_fetch(query, {"sid": sid}))
        except Exception as e:
            return f"Error querying scope status: {e}"

        if not results:
            return "No case found in current scope."

        row = results[0]
        lines = [
            "Scope Status:",
            f"  Inputs: {row['input_count']}",
            f"  Statements: {row['stmt_count']}",
            f"  Perspectives: {row['pp_count']}",
            f"  Cycles: {row['cycle_count']}",
            f"  Wheels: {row['wheel_count']}",
            f"  Transformations: {row['tr_count']}",
        ]

        return "\n".join(lines)
