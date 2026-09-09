"""
Repository for Wheel node queries.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.perspective import Perspective


#: Canonical component signature per wheel, keyed by (sid, wheel id).
#:
#: `find_by_component_sequence` is called once per candidate arrangement and asks
#: the DB for every wheel of the right size, then reads each one's components to
#: compare. So each new arrangement re-reads every wheel already built at that
#: size, and one read is 1 + 4N queries: `Wheel.statements` reads `self.edges`,
#: `edges` runs `order_transitions` which walks the chain with its own
#: `source.get()`/`target.get()`, and then the `statements` loop reads both
#: endpoints again. Measured at k=4 perspectives (96 wheels), that one call site
#: opens 196,568 of 303,101 total charges — 65% of all client traffic, in a phase
#: that is 116s of a 145s wall. See `tests/probe_build_wheels_offprovider.py`.
#:
#: Safe to cache: a wheel's transitions are written once when it is created and
#: no path in this framework rewires or deletes them, so a signature never goes
#: stale. Keyed by internal id, which assumes ids are not reused — true here for
#: the same reason (nothing deletes a Wheel or a Transition). `clear_signature_cache`
#: exists for tests, which do delete.
#:
#: Bounded so a long-lived process does not accumulate a signature for every wheel
#: it has ever touched. The cap is far above any single build — the pattern is a
#: tight burst over one nexus's wheels (96 at k=4), so eviction only ever reaches
#: entries from finished work.
_SIGNATURE_CACHE_MAX = 50_000
_signature_cache: OrderedDict[tuple[Optional[str], Optional[int]], str] = OrderedDict()


def clear_signature_cache() -> None:
    """Drop all cached wheel signatures. For tests that delete graph data."""
    _signature_cache.clear()


class WheelRepository:
    """
    Repository for Wheel node queries.

    All queries are automatically scoped by sid (injected from DI context).
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

    @classmethod
    def _signature_of(cls, wheel: Wheel, sid: Optional[str]) -> str:
        """
        Canonical signature of a wheel's component sequence, read at most once.

        Empty string for a wheel with no components — matching the caller's old
        `if wheel_components:` skip, since a target signature built from a
        non-empty sequence can never equal "".
        """
        key = (sid, wheel._id)
        if key in _signature_cache:
            return _signature_cache[key]

        components = wheel.statements
        signature = (
            cls._get_canonical_signature([c.hash for c in components])
            if components
            else ""
        )
        if wheel._id is not None:
            _signature_cache[key] = signature
            if len(_signature_cache) > _SIGNATURE_CACHE_MAX:
                _signature_cache.popitem(last=False)
        return signature

    @inject
    def find_by_component_sequence(
        self,
        components: list[Statement],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> Optional[Wheel]:
        """
        Find a Wheel with exactly the given component sequence (rotation-invariant).

        Args:
            components: List of Statements in order
            sid: Case ID (injected from DI context)
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
            WHERE w.sid = $sid
            WITH w, count(t) as trans_count
            WHERE trans_count = $expected_count
            RETURN w
        """
        results = list(graph_db.execute_and_fetch(query, {
            "sid": sid,
            "expected_count": len(comp_hashes),
        }))

        # Filter by canonical signature match
        for row in results:
            wheel: Wheel = row["w"]
            if self._signature_of(wheel, sid) == target_signature:
                return wheel

        return None

    @inject
    def get_transformations(
        self,
        wheel: Wheel,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Transformation]:
        """
        Get all Transformations belonging to a wheel's edges.

        Queries transformations that point to any of the wheel's edges
        via ACTION_REFLECTION relationship, scoped by sid.

        Args:
            wheel: The Wheel to get transformations for
            graph_db: Graph database (injected)
            sid: Case ID (injected from DI context)

        Returns:
            List of Transformation nodes from all edges
        """
        from dialectical_framework.graph.nodes.transformation import Transformation as TransformationNode

        # Get edge IDs for this wheel
        edge_ids = [edge._id for edge in wheel.edges if edge._id is not None]
        if not edge_ids:
            return []

        # Query transformations pointing to these edges, scoped by sid
        query = """
        MATCH (tr:Transformation)-[:ACTION_REFLECTION]->(t:Transition)
        WHERE id(t) IN $edge_ids AND tr.sid = $sid
        RETURN tr
        ORDER BY id(tr)
        """
        results = list(graph_db.execute_and_fetch(query, {
            "edge_ids": edge_ids,
            "sid": sid,
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
        perspectives: list[Perspective],
        nexus: Optional[Nexus] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[Wheel]:
        """
        Find all Wheels in the same layer (same Perspective set, any arrangement).

        A "layer" consists of all Wheels whose parent Cycles have exactly
        the same set of Perspectives (regardless of order).

        When nexus is provided, scopes to Wheels whose parent Cycle's
        Perspective hashes are all within the Nexus's Perspective set.

        This is used for probability normalization across competing alternatives.

        Args:
            perspectives: List of Perspectives defining the layer
            nexus: Optional Nexus to scope results to
            sid: Case ID (injected from DI context)
            graph_db: Graph database (injected)

        Returns:
            List of Wheel nodes in this layer
        """
        if not perspectives:
            return []

        pp_hashes = sorted([pp.hash for pp in perspectives if pp.hash is not None])

        # Find all Wheels belonging to Cycles with exactly these Perspective hashes
        query = """
            MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel)
            WHERE w.sid = $sid
            AND size(c.perspective_hashes) = $hash_count
            AND ALL(h IN $pp_hashes WHERE h IN c.perspective_hashes)
        """
        params: dict = {
            "sid": sid,
            "pp_hashes": pp_hashes,
            "hash_count": len(pp_hashes),
        }

        if nexus is not None:
            nexus_pp_hashes = [pp.hash for pp, _ in nexus.perspectives.all()]
            query += "    AND ALL(h IN c.perspective_hashes WHERE h IN $nexus_pp_hashes)\n"
            params["nexus_pp_hashes"] = nexus_pp_hashes

        query += "    RETURN w\n    ORDER BY w.committed_at ASC, id(w) ASC"

        results = list(graph_db.execute_and_fetch(query, params))

        return [row["w"] for row in results]

    @inject
    def find_by_nexus(
        self,
        nexus: Nexus,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
        sid: Optional[str] = Provide[DI.sid],
    ) -> list[tuple[Cycle, Wheel]]:
        """
        Find every Wheel under a Nexus, at any layer, with its parent Cycle.

        Same nexus scoping as `find_by_layer` (a Cycle belongs to a Nexus when
        all of its Perspective hashes are the Nexus's), but across all layers
        instead of one — the whole-exploration read a status pass needs.

        The parent Cycle comes back in the same row on purpose: a caller
        reporting per-wheel status needs the arrangement each wheel implements
        (and its layer), and re-reading `wheel.cycle` afterwards would be one
        extra relationship read per wheel.

        Returns:
            (Cycle, Wheel) pairs, largest layer first
        """
        nexus_pp_hashes = [
            pp.hash for pp, _ in nexus.perspectives.all() if pp.hash is not None
        ]
        if not sid or not nexus_pp_hashes:
            return []

        query = """
            MATCH (c:Cycle)-[:HAS_WHEEL]->(w:Wheel)
            WHERE w.sid = $sid AND c.sid = $sid
            AND w.hash IS NOT NULL AND c.hash IS NOT NULL
            AND size(c.perspective_hashes) > 0
            AND ALL(h IN c.perspective_hashes WHERE h IN $nexus_pp_hashes)
            RETURN c, w
            ORDER BY size(c.perspective_hashes) DESC, c.committed_at ASC,
                     w.committed_at ASC, id(w) ASC
        """
        results = list(
            graph_db.execute_and_fetch(
                query, {"sid": sid, "nexus_pp_hashes": nexus_pp_hashes}
            )
        )

        return [(row["c"], row["w"]) for row in results]

