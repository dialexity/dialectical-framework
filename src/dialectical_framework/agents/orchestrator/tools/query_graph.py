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
    """Check if query is a schema introspection query (safe without sid scoping)."""
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


def _inject_sid_scoping(query: str) -> str:
    """
    Inject sid: $sid into all node patterns in the query.

    This ensures all data queries are automatically scoped to the current session,
    regardless of what the LLM generates. The LLM doesn't need to worry about sid.

    Transforms:
    - (n) -> (n {sid: $sid})
    - (n:Label) -> (n:Label {sid: $sid})
    - (n:Label {prop: val}) -> (n:Label {sid: $sid, prop: val})
    - (n:Label {sid: $sid}) -> (n:Label {sid: $sid})  # Already has it, don't duplicate
    """

    def transform_node_pattern(match: re.Match) -> str:
        var_name = match.group(1)  # Variable name (could be empty for anonymous)
        labels = match.group(2) or ""  # :Label or :Label1:Label2 (could be None)
        props = match.group(3)  # {existing: props} or None

        if props:
            props_content = props.strip()[1:-1]  # Remove { }
            # Check if sid: $sid is already present - don't duplicate
            if re.search(r"\bsid\s*:\s*\$sid\b", props_content):
                return match.group(0)  # Return unchanged
            # Has existing properties - prepend sid
            # {foo: bar} -> {sid: $sid, foo: bar}
            new_props = f"{{sid: $sid, {props_content}}}"
            return f"({var_name}{labels} {new_props})"
        else:
            # No properties - add sid
            return f"({var_name}{labels} {{sid: $sid}})"

    # Regex to match node patterns:
    # ( optional_var optional_labels optional_props )
    # Examples: (n), (n:Label), (:Label), (n:Label {x: 1}), (n {x: 1})
    #
    # Group 1: variable name (optional, could be empty string)
    # Group 2: labels like :Label or :Label1:Label2 (optional)
    # Group 3: properties like {foo: bar} (optional)
    node_pattern = r"\((\w*)((?::\w+)*)(\s*\{[^}]*\})?\)"

    return re.sub(node_pattern, transform_node_pattern, query)


def _has_hardcoded_sid(query: str) -> bool:
    """
    Check if query contains a hardcoded sid value (security risk).

    Rejects patterns like {sid: "literal"} or {sid: 'literal'} or sid: $other_param
    but allows {sid: $sid} which we inject.
    """
    # Look for sid with a literal string value
    if re.search(r'\bsid\s*:\s*["\'][^"\']+["\']', query, re.IGNORECASE):
        return True
    # Look for sid with a different parameter (not $sid)
    if re.search(r"\bsid\s*:\s*\$(?!sid\b)\w+", query, re.IGNORECASE):
        return True
    return False


class QueryGraph(BaseTool):
    """
    Execute a Cypher query on the graph database.

    Use this for flexible exploration of the dialectical knowledge graph.
    Session scoping (sid) is AUTOMATICALLY INJECTED - you don't need to add it.

    SCHEMA QUERIES (to understand the graph structure):
    - "SHOW SCHEMA INFO" - show all node labels and relationship types
    - "CALL db.labels() YIELD label RETURN label" - list all node labels
    - "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType"

    DATA QUERIES (sid is auto-injected, don't include it):
    - "MATCH (b:Brainstorm) RETURN b" - get session brainstorm
    - "MATCH (c:DialecticalComponent) RETURN c.statement LIMIT 10" - list components
    - "MATCH (b:Brainstorm)-[:HAS_INPUT]->(i:Input) RETURN i.content" - list inputs
    - "MATCH (wu:WisdomUnit)<-[:T]-(t) RETURN wu, t.statement" - WisdomUnits with thesis
    - "MATCH (a)-[:OPPOSITE_OF]->(b) RETURN a.statement, b.statement" - oppositions
    - "MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel) RETURN c, w" - cycle and wheels

    KEY NODE TYPES: Brainstorm, Input, DialecticalComponent, WisdomUnit,
                    Cycle, Wheel, Transformation, Transition, Synthesis, Rationale

    KEY RELATIONSHIPS: T, A, T_PLUS, T_MINUS, A_PLUS, A_MINUS (positions),
                       OPPOSITE_OF, CONTRADICTION_OF (semantic),
                       HAS_INPUT, HAS_WHEEL, HAS_TRANSFORMATION (structural)
    """

    cypher: str = Field(
        description="Cypher query. Don't include sid - it's automatically injected for security."
    )
    limit: int = Field(
        default=50,
        description="Maximum rows to return (safety limit, not applied to schema queries)",
    )

    @inject
    async def call(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> str:
        """Execute the Cypher query with automatic sid scoping."""
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

        # Security: Block hardcoded sid values (injection attempt)
        if _has_hardcoded_sid(self.cypher):
            return (
                "Error: Hardcoded sid values are not allowed for security reasons.\n"
                "Don't include sid in your query - it's automatically injected."
            )

        # Check if this is a schema query (doesn't need sid scoping)
        is_schema = _is_schema_query(self.cypher)

        # Prepare query
        if is_schema:
            query = self.cypher.strip()
        else:
            # Auto-inject sid scoping into all node patterns
            query = _inject_sid_scoping(self.cypher.strip())

            # Add LIMIT if not present
            if "LIMIT" not in query_upper:
                query = f"{query} LIMIT {self.limit}"

        try:
            results = list(graph_db.execute_and_fetch(query, {"sid": sid}))
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
