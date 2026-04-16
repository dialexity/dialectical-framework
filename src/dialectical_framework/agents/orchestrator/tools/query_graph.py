"""
Query tools for the Orchestrator.

Provides flexible read-only access to the graph database with automatic
session scoping to prevent cross-tenant data leakage.

All tools are stateless - session context flows via DI.
"""

from __future__ import annotations

import re
from typing import Optional, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from mirascope import BaseTool
from pydantic import Field

from dialectical_framework.enums.di import DI


def _is_schema_query(query: str) -> bool:
    """Check if query is a schema introspection query (safe without case_id scoping)."""
    query_upper = query.strip().upper()
    # Memgraph/Neo4j schema commands
    if query_upper.startswith("SHOW "):
        return True
    # Procedure calls for schema introspection
    if "CALL DB.LABELS" in query_upper:
        return True
    if "CALL DB.RELATIONSHIPTYPES" in query_upper:
        return True
    if "CALL DB.SCHEMA" in query_upper:
        return True
    if "CALL SCHEMA." in query_upper:
        return True
    # Schema queries via MATCH that only look at structure
    if "DISTINCT LABELS(N)" in query_upper and "RETURN" in query_upper:
        return True
    if "DISTINCT TYPE(R)" in query_upper and "RETURN" in query_upper:
        return True
    return False


def _inject_case_id_scoping(query: str) -> str:
    """
    Inject case_id: $case_id into all node patterns in the query.

    This ensures all data queries are automatically scoped to the current session,
    regardless of what the LLM generates. The LLM doesn't need to worry about case_id.

    Transforms:
    - (n) -> (n {case_id: $case_id})
    - (n:Label) -> (n:Label {case_id: $case_id})
    - (n:Label {prop: val}) -> (n:Label {case_id: $case_id, prop: val})
    - (n:Label {case_id: $case_id}) -> (n:Label {case_id: $case_id})  # Already has it, don't duplicate
    """

    def transform_node_pattern(match: re.Match) -> str:
        var_name = match.group(1)  # Variable name (could be empty for anonymous)
        labels = match.group(2) or ""  # :Label or :Label1:Label2 (could be None)
        props = match.group(3)  # {existing: props} or None

        if props:
            props_content = props.strip()[1:-1]  # Remove { }
            # Check if case_id: $case_id is already present - don't duplicate
            if re.search(r"\bcase_id\s*:\s*\$case_id\b", props_content):
                return match.group(0)  # Return unchanged
            # Has existing properties - prepend case_id
            # {foo: bar} -> {case_id: $case_id, foo: bar}
            new_props = f"{{case_id: $case_id, {props_content}}}"
            return f"({var_name}{labels} {new_props})"
        else:
            # No properties - add case_id
            return f"({var_name}{labels} {{case_id: $case_id}})"

    # Regex to match node patterns:
    # ( optional_var optional_labels optional_props )
    # Examples: (n), (n:Label), (:Label), (n:Label {x: 1}), (n {x: 1})
    #
    # Group 1: variable name (optional, could be empty string)
    # Group 2: labels like :Label or :Label1:Label2 (optional)
    # Group 3: properties like {foo: bar} (optional)
    node_pattern = r"\((\w*)((?::\w+)*)(\s*\{[^}]*\})?\)"

    return re.sub(node_pattern, transform_node_pattern, query)


def _has_hardcoded_case_id(query: str) -> bool:
    """
    Check if query contains a hardcoded case_id value (security risk).

    Rejects patterns like {case_id: "literal"} or {case_id: 'literal'} or case_id: $other_param
    but allows {case_id: $case_id} which we inject.
    """
    # Look for case_id with a literal string value
    if re.search(r'\bcase_id\s*:\s*["\'][^"\']+["\']', query, re.IGNORECASE):
        return True
    # Look for case_id with a different parameter (not $case_id)
    if re.search(r"\bcase_id\s*:\s*\$(?!case_id\b)\w+", query, re.IGNORECASE):
        return True
    return False


class QueryGraph(BaseTool):
    """
    Execute a Cypher query on the graph database.

    Use this for flexible exploration of the dialectical knowledge graph.
    Session scoping (case_id) is AUTOMATICALLY INJECTED - you don't need to add it.

    SCHEMA QUERIES (to understand the graph structure):
    - "SHOW SCHEMA INFO" - show all node labels and relationship types
    - "CALL db.labels() YIELD label RETURN label" - list all node labels
    - "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"

    DATA QUERIES (case_id is auto-injected, don't include it):
    - "MATCH (c:Case) RETURN c" - get session case
    - "MATCH (c:DialecticalComponent) RETURN c.statement LIMIT 10" - list components
    - "MATCH (c:Case)-[:HAS_INPUT]->(i:Input) RETURN i.content" - list inputs
    - "MATCH (wu:WisdomUnit)<-[:T]-(t) RETURN wu, t.statement" - WisdomUnits with thesis
    - "MATCH (a)-[:OPPOSITE_OF]->(b) RETURN a.statement, b.statement" - oppositions
    - "MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel) RETURN c, w" - cycle and wheels

    KEY NODE TYPES: Case, Input, DialecticalComponent, WisdomUnit,
                    Cycle, Wheel, Transformation, Transition, Synthesis, Rationale

    KEY RELATIONSHIPS: T, A, T_PLUS, T_MINUS, A_PLUS, A_MINUS (positions),
                       OPPOSITE_OF, CONTRADICTION_OF (semantic),
                       HAS_INPUT, HAS_WHEEL, HAS_TRANSFORMATION (structural)
    """

    cypher: str = Field(
        description="Cypher query. Don't include case_id - it's automatically injected for security."
    )
    limit: int = Field(
        default=50,
        description="Maximum rows to return (safety limit, not applied to schema queries)",
    )

    @inject
    async def call(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> str:
        """Execute the Cypher query with automatic case_id scoping."""
        query_upper = self.cypher.upper()

        # Security: Block write operations
        blocked_keywords = [
            "CREATE",
            "MERGE",
            "DELETE",
            "DETACH",
            "SET",
            "REMOVE",
            "DROP",
        ]
        for keyword in blocked_keywords:
            if keyword in query_upper:
                return (
                    f"Error: Write operations not allowed. Found '{keyword}' in query."
                )

        # Security: Block hardcoded case_id values (injection attempt)
        if _has_hardcoded_case_id(self.cypher):
            return (
                "Error: Hardcoded case_id values are not allowed for security reasons.\n"
                "Don't include case_id in your query - it's automatically injected."
            )

        # Check if this is a schema query (doesn't need case_id scoping)
        is_schema = _is_schema_query(self.cypher)

        # Prepare query
        if is_schema:
            query = self.cypher.strip()
        else:
            # Auto-inject case_id scoping into all node patterns
            query = _inject_case_id_scoping(self.cypher.strip())

            # Add LIMIT if not present
            if "LIMIT" not in query_upper:
                query = f"{query} LIMIT {self.limit}"

        try:
            results = list(graph_db.execute_and_fetch(query, {"case_id": case_id}))
        except Exception as e:
            return f"Query error: {e}"

        if not results:
            return "No results found."

        # Format results
        lines = [f"Found {len(results)} result(s):", ""]

        for i, row in enumerate(results[: self.limit]):
            row_parts = []
            for key, value in row.items():
                # Format node objects nicely
                if hasattr(value, "short_hash"):
                    row_parts.append(
                        f"{key}: [{value.__class__.__name__} {value.short_hash}]"
                    )
                elif hasattr(value, "statement"):
                    stmt = (
                        value.statement[:50] + "..."
                        if len(str(value.statement)) > 50
                        else value.statement
                    )
                    row_parts.append(f"{key}: {stmt}")
                else:
                    val_str = str(value)[:100]
                    row_parts.append(f"{key}: {val_str}")
            lines.append(f"{i+1}. {', '.join(row_parts)}")

        if len(results) > self.limit:
            lines.append(f"... (showing {self.limit} of {len(results)})")

        return "\n".join(lines)
