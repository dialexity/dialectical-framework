"""
Repository for live database schema discovery.

Unlike other repositories, these queries are NOT scoped by sid — they inspect
the global database schema (labels, relationship types) for LLM context building.
"""

from __future__ import annotations

from typing import Union

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI


class SchemaRepository:
    """
    Repository for live database schema discovery.

    Provides the Orchestrator with current node labels and relationship types
    for system prompt construction.
    """

    @inject
    def get_node_labels(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> set[str]:
        """
        Get all distinct node labels currently in the database.

        Filters out base labels (Node, Assessable) that are implementation details.

        Returns:
            Set of label strings
        """
        try:
            results = list(
                graph_db.execute_and_fetch(
                    "MATCH (n) RETURN DISTINCT labels(n) AS labels"
                )
            )
            all_labels: set[str] = set()
            for row in results:
                all_labels.update(row["labels"])
            all_labels.discard("Node")
            all_labels.discard("Assessable")
            return all_labels
        except Exception:
            return set()

    @inject
    def get_relationship_types(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[str]:
        """
        Get all distinct relationship types currently in the database.

        Returns:
            Sorted list of relationship type strings
        """
        try:
            results = list(
                graph_db.execute_and_fetch(
                    "MATCH ()-[r]->() RETURN DISTINCT type(r) AS rel_type"
                )
            )
            return sorted(row["rel_type"] for row in results)
        except Exception:
            return []
