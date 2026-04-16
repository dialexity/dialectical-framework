"""
Repository for Wheel node queries.

All queries are scoped by case_id (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.settings import Settings
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class WheelRepository:
    """
    Repository for Wheel node queries.

    All queries are automatically scoped by case_id (injected from DI context).
    """

    @staticmethod
    def _get_canonical_signature(hashes: list[str]) -> str:
        """
        Get canonical signature for hash ordering (rotation-invariant).

        Args:
            hashes: List of hashes in order

        Returns:
            Canonical string signature (colon-joined, lex-smallest rotation)
        """
        if not hashes:
            return ""

        # Find canonical rotation (lexicographically smallest)
        rotations = [hashes[i:] + hashes[:i] for i in range(len(hashes))]
        canonical = min(rotations)
        return ":".join(canonical)

    @inject
    def find_by_component_sequence(
        self,
        components: list[DialecticalComponent],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> Optional[Wheel]:
        """
        Find a Wheel with exactly the given component sequence (rotation-invariant).

        Args:
            components: List of DialecticalComponents in order
            case_id: Case ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            Existing Wheel if found, None otherwise
        """
        from dialectical_framework.graph.nodes.wheel import Wheel

        if not components:
            return None

        comp_hashes = [c.hash for c in components]
        target_signature = self._get_canonical_signature(comp_hashes)

        # Query wheels that have the right number of transitions
        # A wheel with N components has N transitions (circular)
        query = """
            MATCH (w:Wheel)<-[:BELONGS_TO_CYCLE]-(t:Transition)
            WHERE w.case_id = $case_id
            WITH w, count(t) as trans_count
            WHERE trans_count = $expected_count
            RETURN w
        """
        results = list(graph_db.execute_and_fetch(query, {
            "case_id": case_id,
            "expected_count": len(comp_hashes),
        }))

        # Filter by canonical signature match
        for row in results:
            wheel: Wheel = row["w"]
            wheel_components = wheel.dialectical_components
            if wheel_components:
                wheel_hashes = [c.hash for c in wheel_components]
                wheel_signature = self._get_canonical_signature(wheel_hashes)
                if wheel_signature == target_signature:
                    return wheel

        return None

    @inject
    def get_transformations(
        self,
        wheel: Wheel,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> list[Transformation]:
        """
        Get all Transformations belonging to a wheel's edges.

        Queries transformations that point to any of the wheel's edges
        via ACTION_REFLECTION relationship, scoped by case_id.

        Args:
            wheel: The Wheel to get transformations for
            graph_db: Graph database (injected)
            case_id: Case ID (injected from DI context)

        Returns:
            List of Transformation nodes from all edges
        """
        from dialectical_framework.graph.nodes.transformation import Transformation as TransformationNode

        # Get edge IDs for this wheel
        edge_ids = [edge._id for edge in wheel.edges if edge._id is not None]
        if not edge_ids:
            return []

        # Query transformations pointing to these edges, scoped by case_id
        query = """
        MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(t:Transition)
        WHERE id(t) IN $edge_ids AND tr.case_id = $case_id
        RETURN tr
        ORDER BY id(tr)
        """
        results = list(graph_db.execute_and_fetch(query, {
            "edge_ids": edge_ids,
            "case_id": case_id,
        }))

        all_transformations: list[TransformationNode] = []
        for row in results:
            tr = row.get("tr")
            if tr and isinstance(tr, TransformationNode):
                all_transformations.append(tr)
        return all_transformations

    @inject
    def find_by_layer(
        self,
        wisdom_units: list[WisdomUnit],
        nexus: Optional[Nexus] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
    ) -> list[Wheel]:
        """
        Find all Wheels in the same layer (same WU set, any arrangement).

        A "layer" consists of all Wheels whose parent Cycles have exactly
        the same set of WisdomUnits (regardless of order).

        When nexus is provided, scopes to Wheels whose parent Cycle's WU
        hashes are all within the Nexus's WU set.

        This is used for probability normalization across competing alternatives.

        Args:
            wisdom_units: List of WisdomUnits defining the layer
            nexus: Optional Nexus to scope results to
            case_id: Case ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of Wheel nodes in this layer
        """
        if not wisdom_units:
            return []

        wu_hashes = sorted([wu.hash for wu in wisdom_units])

        # Find all Wheels belonging to Cycles with exactly these WU hashes
        query = """
            MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel)
            WHERE w.case_id = $case_id
            AND size(c.wisdom_unit_hashes) = $hash_count
            AND ALL(h IN $wu_hashes WHERE h IN c.wisdom_unit_hashes)
        """
        params: dict = {
            "case_id": case_id,
            "wu_hashes": wu_hashes,
            "hash_count": len(wu_hashes),
        }

        if nexus is not None:
            nexus_wu_hashes = [wu.hash for wu, _ in nexus.wisdom_units.all()]
            query += "    AND ALL(h IN c.wisdom_unit_hashes WHERE h IN $nexus_wu_hashes)\n"
            params["nexus_wu_hashes"] = nexus_wu_hashes

        query += "    RETURN w"

        results = list(graph_db.execute_and_fetch(query, params))

        return [row["w"] for row in results]

    @inject
    def find_parent_wheels(
        self,
        wheel: Wheel,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        case_id: Optional[str] = Provide[DI.case_id],
        settings: Settings = Provide[DI.settings],
    ) -> list[Wheel]:
        """
        Find all potential parent wheels for Transformation computation.

        Returns wheels that:
        - Have one fewer WU than this wheel
        - Have a WU set that is a subset of this wheel's WUs
        - Match the effective intent

        Args:
            wheel: The Wheel to find parents for
            graph_db: Graph database (injected)
            case_id: Case ID (injected from DI context)

        Returns:
            List of parent Wheel nodes
        """
        from dialectical_framework.graph.nodes.wheel import Wheel as WheelNode

        wheel_wu_hashes = [wu.hash for wu in wheel._wisdom_units]
        if len(wheel_wu_hashes) <= 1:
            return []  # Layer 1 wheels have no parents

        effective_intent = wheel.get_effective_intent() or settings.cycle_preset
        wheel_wu_set = set(wheel_wu_hashes)
        target_layer = len(wheel_wu_hashes) - 1

        # Get the Cycle
        cycle_result = wheel.cycle.get()
        if not cycle_result:
            return []
        cycle_obj, _ = cycle_result

        # Query all wheels belonging to this Cycle, filter in Python
        query = """
        MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel)
        WHERE id(c) = $cycle_id AND w.case_id = $case_id
        RETURN w
        """
        results = list(graph_db.execute_and_fetch(query, {
            "cycle_id": cycle_obj._id,
            "case_id": case_id,
        }))

        parents: list[WheelNode] = []
        for row in results:
            candidate: WheelNode = row["w"]
            candidate_wu_hashes = [wu.hash for wu in candidate._wisdom_units]

            # Check layer match (one fewer WU)
            if len(candidate_wu_hashes) != target_layer:
                continue

            candidate_wu_set = set(candidate_wu_hashes)

            # Check if candidate's WUs are a subset of this wheel's WUs
            if candidate_wu_set.issubset(wheel_wu_set):
                # Check intent match
                candidate_intent = candidate.get_effective_intent() or settings.cycle_preset
                if candidate_intent == effective_intent:
                    parents.append(candidate)

        return parents
