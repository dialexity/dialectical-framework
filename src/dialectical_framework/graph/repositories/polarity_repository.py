"""
PolarityRepository for complex query operations.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.polarity import Polarity
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class PolarityRepository:
    """
    Repository for Polarity query operations.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_tension(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Polarity]:
        """
        Find Polarities that have the given thesis at T and antithesis at A.

        Args:
            thesis: The DialecticalComponent at position T
            antithesis: The DialecticalComponent at position A
            sid: Case ID (injected from DI context)

        Returns:
            List of Polarities where T=thesis AND A=antithesis
        """
        if thesis._id is None or antithesis._id is None:
            return []

        # Validate both components belong to current scope
        if sid:
            if thesis.sid != sid or antithesis.sid != sid:
                return []

        query = """
        MATCH (t:DialecticalComponent)-[:T]->(p:Polarity)<-[:A]-(a:DialecticalComponent)
        WHERE id(t) = $thesis_id AND id(a) = $antithesis_id
        RETURN p
        """

        results = graph_db.execute_and_fetch(query, {
            "thesis_id": thesis._id,
            "antithesis_id": antithesis._id
        })
        return [result["p"] for result in results]

    @inject
    def find_by_component(
        self,
        component: DialecticalComponent,
        position: Optional[str] = None,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[Polarity, str]]:
        """
        Find all Polarities that contain this component.

        Args:
            component: The DialecticalComponent to query for
            position: Optional position filter ('T' or 'A')
            sid: Case ID (injected from DI context)

        Returns:
            List of tuples: (Polarity, position) where position is 'T' or 'A'
        """
        if component._id is None:
            return []

        # Validate component belongs to current scope
        if sid and component.sid != sid:
            return []

        if position:
            # Filter by specific position
            query = f"""
            MATCH (c:DialecticalComponent)-[:{position}]->(p:Polarity)
            WHERE id(c) = $component_id
            RETURN p, '{position}' AS rel_type
            """
        else:
            # All positions
            query = """
            MATCH (c:DialecticalComponent)-[r]->(p:Polarity)
            WHERE id(c) = $component_id
            AND type(r) IN ['T', 'A']
            RETURN p, type(r) AS rel_type
            """

        results = graph_db.execute_and_fetch(query, {
            "component_id": component._id
        })
        return [(result["p"], result["rel_type"]) for result in results]

    @inject
    def find_by_thesis(
        self,
        thesis: DialecticalComponent,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Polarity]:
        """
        Find all Polarities where the given component is the thesis (T).

        Args:
            thesis: The DialecticalComponent at position T
            sid: Case ID (injected from DI context)

        Returns:
            List of Polarities
        """
        results = self.find_by_component(thesis, position='T', sid=sid, graph_db=graph_db)
        return [p for p, _ in results]

    @inject
    def find_by_antithesis(
        self,
        antithesis: DialecticalComponent,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Polarity]:
        """
        Find all Polarities where the given component is the antithesis (A).

        Args:
            antithesis: The DialecticalComponent at position A
            sid: Case ID (injected from DI context)

        Returns:
            List of Polarities
        """
        results = self.find_by_component(antithesis, position='A', sid=sid, graph_db=graph_db)
        return [p for p, _ in results]

    @inject
    def find_all(
        self,
        committed_only: bool = True,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Polarity]:
        """
        Find all Polarities in the current scope.

        Args:
            committed_only: If True, only return committed Polarities (with hash)
            sid: Case ID (injected from DI context)

        Returns:
            List of Polarities
        """
        if not sid:
            return []

        if committed_only:
            query = """
            MATCH (p:Polarity)
            WHERE p.sid = $sid AND p.hash IS NOT NULL
            RETURN p
            """
        else:
            query = """
            MATCH (p:Polarity)
            WHERE p.sid = $sid
            RETURN p
            """

        results = graph_db.execute_and_fetch(query, {"sid": sid})
        return [result["p"] for result in results]
