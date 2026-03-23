"""
NexusRepository for creating and querying Nexus nodes.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class NexusRepository:
    """
    Repository for Nexus creation and query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def create_from_wisdom_units(
        self,
        wisdom_unit_hashes: list[str],
        intent: Optional[str] = None,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Nexus:
        """
        Create a Nexus from a list of WisdomUnit hashes.

        This is the preferred way to create a Nexus programmatically:
        1. Resolves WU hashes to nodes
        2. Creates Nexus with optional intent
        3. Connects all WUs to the Nexus
        4. Commits the Nexus

        Args:
            wisdom_unit_hashes: List of WisdomUnit hashes (full or prefix)
            intent: Optional intent for the Nexus (e.g., "economic_vs_social")
            sid: Scope ID (injected from DI context)

        Returns:
            Committed Nexus node with all WUs connected

        Raises:
            ValueError: If no WU hashes provided or any WU not found in scope
        """
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        if not wisdom_unit_hashes:
            raise ValueError("At least one WisdomUnit hash is required")

        # Resolve WU hashes to nodes
        repo = NodeRepository()
        wisdom_units: list[WisdomUnit] = []

        for wu_hash in wisdom_unit_hashes:
            wu = repo.find_by_hash(wu_hash, node_type=WisdomUnit)
            if wu is None:
                raise ValueError(f"WisdomUnit not found: {wu_hash}")
            if sid and wu.sid != sid:
                raise ValueError(f"WisdomUnit {wu_hash} not in current scope")
            wisdom_units.append(wu)

        # Create Nexus
        nexus = Nexus(intent=intent) if intent else Nexus()
        nexus.save()

        # Connect WUs to Nexus (WU → Nexus)
        for wu in wisdom_units:
            wu.nexus.connect(nexus)

        # Commit Nexus
        nexus.commit()

        return nexus

    @inject
    def find_by_wisdom_units(
        self,
        wisdom_units: list[WisdomUnit],
        intent: Optional[str] = None,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Nexus]:
        """
        Find existing Nexuses that contain exactly the given WisdomUnits.

        Useful for idempotent operations - check if a Nexus already exists
        before creating a new one.

        Args:
            wisdom_units: List of WisdomUnits to search for
            intent: Optional intent to filter by
            sid: Scope ID (injected from DI context)

        Returns:
            List of Nexuses containing exactly these WUs (with optional intent match)
        """
        from dialectical_framework.graph.nodes.nexus import Nexus

        if not wisdom_units:
            return []

        # Validate all WUs belong to current scope
        if sid:
            for wu in wisdom_units:
                if wu.sid != sid:
                    return []

        wu_ids = [wu._id for wu in wisdom_units if wu._id is not None]
        if len(wu_ids) != len(wisdom_units):
            return []

        # Query for Nexuses that have exactly these WUs
        query = """
        MATCH (wu:WisdomUnit)-[:BELONGS_TO_NEXUS]->(n:Nexus)
        WHERE id(wu) IN $wu_ids
        WITH n, count(DISTINCT wu) AS matched_count
        // Ensure nexus has exactly these WUs (no more, no less)
        MATCH (all_wu:WisdomUnit)-[:BELONGS_TO_NEXUS]->(n)
        WITH n, matched_count, count(DISTINCT all_wu) AS total_count
        WHERE matched_count = $expected_count AND total_count = $expected_count
        RETURN n
        """

        params = {
            "wu_ids": wu_ids,
            "expected_count": len(wisdom_units),
        }

        results = list(graph_db.execute_and_fetch(query, params))
        nexuses = [result["n"] for result in results]

        # Filter by intent if specified
        if intent is not None:
            nexuses = [n for n in nexuses if n.intent == intent]

        return nexuses

    @inject
    def get_all(
        self,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[Nexus]:
        """
        Get all Nexuses in the current scope.

        Args:
            sid: Scope ID (injected from DI context)

        Returns:
            List of all Nexuses in scope
        """
        from dialectical_framework.graph.nodes.nexus import Nexus

        if not sid:
            return []

        query = """
        MATCH (n:Nexus)
        WHERE n.sid = $sid
        RETURN n
        """

        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return [result["n"] for result in results]
