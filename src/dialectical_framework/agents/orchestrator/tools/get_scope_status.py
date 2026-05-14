"""
GetScopeStatus: Quick counts of all node types in scope.
"""

from __future__ import annotations

from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import llm

from dialectical_framework.agents.reasonable_concern import ReasonableConcern
from dialectical_framework.enums.di import DI


class GetScopeStatus(ReasonableConcern[str]):
    """Queries node counts within the current scope."""

    @inject
    async def resolve(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
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
            self._report.ok = False
            self._report.summary = f"Error: {e}"
            return f"Error querying scope status: {e}"

        if not results:
            self._report.ok = True
            self._report.summary = "No case found"
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

        self._report.ok = True
        self._report.summary = "Status retrieved"
        return "\n".join(lines)


@llm.tool
async def get_scope_status() -> str:
    """Show counts of all node types (Inputs, Statements, Perspectives, Cycles, Wheels, Transformations) in the current scope."""
    concern = GetScopeStatus()
    return await concern.resolve()
