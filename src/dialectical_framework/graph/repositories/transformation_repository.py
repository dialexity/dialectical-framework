"""
Repository for Transformation node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.repositories.wheel_repository import WheelRepository


@dataclass
class CoarserTransformation:
    """A parent Transformation from a coarser (smaller) wheel."""

    transformation: Transformation
    layer: int


class TransformationRepository:
    """
    Repository for Transformation node queries.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_nexus(
        self,
        nexus: Nexus,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Transformation]:
        """
        Find all Transformations belonging to a Nexus.

        Args:
            nexus: The Nexus to search within
            graph_db: Graph database (injected)
            sid: Case ID (injected from DI context)

        Returns:
            List of Transformation nodes in this Nexus
        """
        from dialectical_framework.graph.nodes.transformation import Transformation as TransformationNode

        query = """
        MATCH (tr:Transformation)-[:BELONGS_TO_NEXUS]->(n:Nexus)
        WHERE id(n) = $nexus_id AND tr.sid = $sid
        RETURN tr
        ORDER BY id(tr)
        """
        results = list(graph_db.execute_and_fetch(query, {
            "nexus_id": nexus._id,
            "sid": sid,
        }))

        return [
            row["tr"] for row in results
            if isinstance(row.get("tr"), TransformationNode)
        ]

    @inject
    def find_by_edge(
        self,
        edge: Transition,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Transformation]:
        """
        Find Transformations linked to this specific edge.

        Returns all Transformation variants attached to the given Transition
        (multiple variants at different proactiveness levels can exist on one edge).

        Args:
            edge: The wheel edge (Transition) to find Transformations for
            graph_db: Graph database (injected)
            sid: Case ID (injected from DI context)

        Returns:
            List of Transformations on this edge
        """
        from dialectical_framework.graph.nodes.transformation import Transformation as TransformationNode

        if edge._id is None:
            return []

        query = """
        MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(t:Transition)
        WHERE id(t) = $edge_id AND tr.sid = $sid
        RETURN tr
        ORDER BY id(tr)
        """
        results = list(graph_db.execute_and_fetch(query, {
            "edge_id": edge._id,
            "sid": sid,
        }))

        return [
            row["tr"] for row in results
            if isinstance(row.get("tr"), TransformationNode)
        ]

    @inject
    def find_parent_transformations(
        self,
        edge: Transition,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[CoarserTransformation]:
        """
        Find all coarser (parent) Transformations recursively from layer 1 up to L-1.

        For an edge X→Y at layer L, the parent at layer L-1 is determined by
        which PPs are present in the coarser wheel:
        - Both source_pp AND target_pp present → same edge X→Y exists (port candidate)
        - Only source_pp present (target_pp missing) → edge departing from X
        - Only target_pp present (source_pp missing) → edge arriving at Y

        Parents are found recursively: first find L-1 parents using the current
        edge's source/target, then find THEIR parents using the parent edge's
        source/target. This chains transitively:
            T3→T2 (L3) → T1→T2 (L2) → T1→A1 (L1)

        Args:
            edge: The wheel edge (Transition) whose parents we want
            graph_db: Graph database (injected)
            sid: Case ID (injected from DI context)

        Returns:
            List of CoarserTransformation, ordered coarsest-first (layer 1, 2, ... L-1)
        """
        from dialectical_framework.graph.repositories.wheel_repository import WheelRepository

        wheel = self._resolve_wheel(edge)
        if not wheel:
            return []

        current_layer = wheel.polarity_count
        if current_layer <= 1:
            return []

        nexus = self._resolve_nexus(wheel)
        if not nexus:
            return []

        wheel_repo = WheelRepository()
        all_pps = wheel._perspectives

        results: list[CoarserTransformation] = []
        seen_edge_ids: set[int] = set()

        self._collect_parents_recursive(
            edge, current_layer, all_pps, nexus, wheel_repo, results, seen_edge_ids
        )

        results.sort(key=lambda ct: ct.layer)
        return results

    def _collect_parents_recursive(
        self,
        edge: Transition,
        edge_layer: int,
        all_pps: list[Perspective],
        nexus: Nexus,
        wheel_repo: WheelRepository,
        results: list[CoarserTransformation],
        seen_edge_ids: set[int],
    ) -> None:
        """
        Recursively collect parent Transformations by finding L-1 parents,
        then finding their parents in turn.
        """
        if edge_layer <= 1:
            return

        source_pp, target_pp = self._resolve_edge_pps(edge)
        if not source_pp or not target_pp:
            return

        source_stmt = self._get_edge_source_stmt(edge)
        target_stmt = self._get_edge_target_stmt(edge)
        if not source_stmt or not target_stmt:
            return

        parent_layer = edge_layer - 1
        candidate_wheels = self._find_wheels_at_layer(
            wheel_repo, all_pps, parent_layer, nexus
        )

        for parent_wheel in candidate_wheels:
            parent_pp_hashes = {pp.hash for pp in parent_wheel._perspectives}
            has_source = source_pp.hash in parent_pp_hashes
            has_target = target_pp.hash in parent_pp_hashes

            if not has_source and not has_target:
                continue

            parent_edge = self._find_matching_parent_edge(
                parent_wheel, source_stmt, target_stmt, has_source, has_target
            )
            if not parent_edge or parent_edge._id in seen_edge_ids:
                continue

            seen_edge_ids.add(parent_edge._id)

            for tr in parent_wheel.transformations:
                if self._transformation_on_edge(tr, parent_edge):
                    results.append(CoarserTransformation(
                        transformation=tr, layer=parent_layer
                    ))

            # Recurse: find this parent edge's parents
            self._collect_parents_recursive(
                parent_edge, parent_layer, all_pps, nexus, wheel_repo, results, seen_edge_ids
            )

    def _find_matching_parent_edge(
        self,
        parent_wheel: Wheel,
        source_stmt: Statement,
        target_stmt: Statement,
        has_source: bool,
        has_target: bool,
    ) -> Optional[Transition]:
        """
        Find the parent edge in a coarser wheel that this edge subdivides.

        Rules:
        - Both PPs present → edge with same source AND target
        - Only source PP → edge departing from same source statement
        - Only target PP → edge arriving at same target statement
        """

        for parent_edge in parent_wheel.edges:
            pe_source_result = parent_edge.source.get()
            pe_target_result = parent_edge.target.get()
            if not pe_source_result or not pe_target_result:
                continue

            pe_source, _ = pe_source_result
            pe_target, _ = pe_target_result

            if has_source and has_target:
                if pe_source.hash == source_stmt.hash and pe_target.hash == target_stmt.hash:
                    return parent_edge
            elif has_source:
                if pe_source.hash == source_stmt.hash:
                    return parent_edge
            elif has_target:
                if pe_target.hash == target_stmt.hash:
                    return parent_edge

        return None

    def _transformation_on_edge(
        self,
        transformation: Transformation,
        edge: Transition,
    ) -> bool:
        """Check if a Transformation is linked to the given edge."""
        edge_result = transformation.edge.get()
        if not edge_result:
            return False
        tr_edge, _ = edge_result
        return tr_edge._id == edge._id

    def _resolve_wheel(self, edge: Transition) -> Optional[Wheel]:
        """Derive Wheel from an edge's cycle relationship."""
        from dialectical_framework.graph.nodes.wheel import Wheel as WheelNode

        cycle_result = edge.cycle.get()
        if not cycle_result:
            return None
        container, _ = cycle_result
        if isinstance(container, WheelNode):
            return container
        return None

    def _resolve_nexus(self, wheel: Wheel) -> Optional[Nexus]:
        """Derive Nexus from a wheel's Perspectives."""
        for pp in wheel._perspectives:
            nexus_result = pp.nexus.get()
            if nexus_result:
                return nexus_result[0]
        return None

    def _resolve_edge_pps(
        self, edge: Transition
    ) -> tuple[Optional[Perspective], Optional[Perspective]]:
        """Resolve which PPs the edge's source and target statements belong to."""
        from dialectical_framework.graph.repositories.perspective_repository import PerspectiveRepository

        source_result = edge.source.get()
        target_result = edge.target.get()
        if not source_result or not target_result:
            return None, None

        source_stmt, _ = source_result
        target_stmt, _ = target_result

        pp_repo = PerspectiveRepository()
        source_pps = pp_repo.find_by_statement(source_stmt)
        target_pps = pp_repo.find_by_statement(target_stmt)

        if not source_pps or not target_pps:
            return None, None

        return source_pps[0][0], target_pps[0][0]

    def _get_edge_source_stmt(self, edge: Transition) -> Optional[Statement]:
        """Get the source Statement of an edge."""
        result = edge.source.get()
        if result:
            return result[0]
        return None

    def _get_edge_target_stmt(self, edge: Transition) -> Optional[Statement]:
        """Get the target Statement of an edge."""
        result = edge.target.get()
        if result:
            return result[0]
        return None

    def _find_wheels_at_layer(
        self,
        wheel_repo: WheelRepository,
        wheel_pps: list[Perspective],
        target_layer: int,
        nexus: Nexus,
    ) -> list[Wheel]:
        """Find wheels at a specific layer whose PP set is a subset of the current wheel's PPs."""
        from itertools import combinations

        results: list[Wheel] = []
        for combo in combinations(wheel_pps, target_layer):
            wheels = wheel_repo.find_by_layer(list(combo), nexus=nexus)
            results.extend(wheels)
        return results
