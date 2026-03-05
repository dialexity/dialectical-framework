"""
WisdomUnitRepository for complex query operations and lifecycle management.

All queries are scoped by sid (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class WisdomUnitRepository:
    """
    Repository for WisdomUnit query operations and lifecycle management.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_polarity(
        self,
        thesis: DialecticalComponent,
        antithesis: DialecticalComponent,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[WisdomUnit]:
        """
        Find WisdomUnits that have the given thesis at T and antithesis at A.

        This is useful for looking up the heuristic_similarity stored on the
        ARelationship for a specific T-A pair.

        Args:
            thesis: The DialecticalComponent at position T
            antithesis: The DialecticalComponent at position A
            sid: Scope ID (injected from DI context)

        Returns:
            List of WisdomUnits where T=thesis AND A=antithesis
        """
        if thesis._id is None or antithesis._id is None:
            return []

        # Validate both components belong to current scope
        if sid:
            if thesis.sid != sid or antithesis.sid != sid:
                return []

        query = """
        MATCH (t:DialecticalComponent)-[:T]->(wu:WisdomUnit)<-[:A]-(a:DialecticalComponent)
        WHERE id(t) = $thesis_id AND id(a) = $antithesis_id
        RETURN wu
        """

        results = graph_db.execute_and_fetch(query, {
            "thesis_id": thesis._id,
            "antithesis_id": antithesis._id
        })
        return [result["wu"] for result in results]

    @inject
    def find_by_dialectical_component(
        self,
        component: DialecticalComponent,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[WisdomUnit, str]]:
        """
        Find all WisdomUnits that contain this component.

        Args:
            component: The DialecticalComponent to query for
            sid: Scope ID (injected from DI context)

        Returns:
            List of tuples: (WisdomUnit, relationship_type)
        """
        if component._id is None:
            return []

        # Validate component belongs to current scope
        if sid and component.sid != sid:
            return []

        query = """
        // Core positions (T, T+, T-, A, A+, A-) directly on WU
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS']
        RETURN wu, type(r) AS rel_type

        UNION

        // Synthesis positions (S+, S-) via Synthesis node
        MATCH (c:DialecticalComponent)-[r]->(synth:Synthesis)-[:SYNTHESIS_OF]->(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['S_PLUS', 'S_MINUS']
        RETURN wu, type(r) AS rel_type
        """

        results = graph_db.execute_and_fetch(query, {"component_id": component._id})
        return [(result["wu"], result["rel_type"]) for result in results]

    @inject
    def safe_delete(
        self,
        wisdom_unit: WisdomUnit,
        force_gc: bool = True,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Safely delete a WisdomUnit and its complete subgraph.

        Args:
            wisdom_unit: The WisdomUnit to delete
            force_gc: If True (default), aggressive GC mode. If False, conservative mode.
            sid: Scope ID (injected from DI context)

        Returns:
            True if deleted, False if kept or not in scope
        """
        if wisdom_unit._id is None:
            return False

        # Validate WU belongs to current scope
        if sid and wisdom_unit.sid != sid:
            return False

        if force_gc:
            if self.in_use(wisdom_unit, sid=sid, graph_db=graph_db):
                return False
        else:
            if not self.is_isolated(wisdom_unit, sid=sid, graph_db=graph_db):
                return False

        # Delete orphaned HAS_STATEMENT components
        delete_orphaned_stmt_query = """
        MATCH (stmt_comp:DialecticalComponent)
        WHERE NOT exists((stmt_comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]->())
        AND NOT exists((stmt_comp)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]-())
        DETACH DELETE stmt_comp
        """
        graph_db.execute(delete_orphaned_stmt_query)

        # Delete the complete WU subgraph
        delete_subgraph_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(wu_rationale)
        OPTIONAL MATCH (component)<-[:EXPLAINS]-(comp_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:EXPLAINS]-(trans_rationale)
        OPTIONAL MATCH (transformation)<-[:BELONGS_TO_CYCLE]-(transition:Transition)
        OPTIONAL MATCH (transition)<-[:EXPLAINS]-(transit_rationale)
        OPTIONAL MATCH (transformation)<-[:SYNTHESIS_OF]-(synthesis:Synthesis)
        OPTIONAL MATCH (synthesis)<-[:EXPLAINS]-(synth_rationale)
        OPTIONAL MATCH (synthesis)<-[:S_PLUS|S_MINUS]-(synth_component)

        WITH wu,
             collect(DISTINCT component) AS components,
             collect(DISTINCT wu_rationale) + collect(DISTINCT comp_rationale) +
             collect(DISTINCT trans_rationale) + collect(DISTINCT transit_rationale) +
             collect(DISTINCT synth_rationale) AS direct_rationales,
             collect(DISTINCT transformation) AS transformations,
             collect(DISTINCT transition) AS transitions,
             collect(DISTINCT synthesis) AS syntheses,
             collect(DISTINCT synth_component) AS synth_components

        UNWIND CASE WHEN size(direct_rationales) > 0 THEN direct_rationales ELSE [null] END AS rat
        OPTIONAL MATCH (rat)<-[:CRITIQUES*0..10]-(critique_chain:Rationale)
        WHERE rat IS NOT NULL

        WITH wu, components, transformations, transitions, syntheses, synth_components,
             direct_rationales, collect(DISTINCT critique_chain) AS critique_rationales

        WITH wu, components, transformations, transitions, syntheses, synth_components,
             direct_rationales + critique_rationales AS rationales

        FOREACH (rat IN rationales | DETACH DELETE rat)
        FOREACH (trans IN transitions | DETACH DELETE trans)
        FOREACH (transformation IN transformations | DETACH DELETE transformation)

        WITH wu, components, synth_components, syntheses
        UNWIND CASE WHEN size(synth_components) > 0 THEN synth_components ELSE [null] END AS scomp

        OPTIONAL MATCH (scomp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_trans:Transformation)-[:IS_SPIRAL_OF]->(other_wu:WisdomUnit)
        WHERE scomp IS NOT NULL AND other_wu <> wu

        OPTIONAL MATCH (scomp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans_ref:Transition)
        OPTIONAL MATCH (trans_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE scomp IS NOT NULL

        WITH wu, components, syntheses, scomp,
             count(DISTINCT other_synth) + count(DISTINCT cycle_or_spiral) AS synth_vocab_count

        FOREACH (_ IN CASE WHEN scomp IS NOT NULL AND synth_vocab_count = 0 THEN [1] ELSE [] END |
            DETACH DELETE scomp
        )

        WITH DISTINCT wu, components, syntheses
        FOREACH (synth IN syntheses | DETACH DELETE synth)

        WITH wu, components
        UNWIND CASE WHEN size(components) > 0 THEN components ELSE [null] END AS comp

        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(any_synth:Synthesis)
        WHERE comp IS NOT NULL

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition_ref:Transition)
        OPTIONAL MATCH (transition_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (transition_ref)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(wu)

        WITH wu, comp,
             count(DISTINCT other_wu) + count(DISTINCT any_synth) + count(DISTINCT cycle_or_spiral) AS vocab_count

        FOREACH (_ IN CASE WHEN comp IS NOT NULL AND vocab_count = 0 THEN [1] ELSE [] END |
            DETACH DELETE comp
        )

        WITH DISTINCT wu
        DETACH DELETE wu
        """
        graph_db.execute(delete_subgraph_query, {"wu_id": wisdom_unit._id})

        return True

    @inject
    def is_isolated(
        self,
        wisdom_unit: WisdomUnit,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if a WisdomUnit is isolated (not part of vocabulary at any level).

        Args:
            wisdom_unit: The WisdomUnit to check
            sid: Scope ID (injected from DI context)

        Returns:
            True if isolated, False if in vocabulary or not in scope
        """
        if wisdom_unit._id is None:
            return True

        # Validate WU belongs to current scope
        if sid and wisdom_unit.sid != sid:
            return False  # Not in scope = treat as not isolated (don't allow operations)

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        OPTIONAL MATCH (wu)-[:BELONGS_TO_NEXUS]->(nexus:Nexus)-[:HAS_CYCLE]->(cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)

        OPTIONAL MATCH (external_trans:Transformation)-[:ACTION_REFLECTION]->(wu)
        WHERE NOT (external_trans)-[:IS_SPIRAL_OF]->(wu)

        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component:DialecticalComponent)

        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(trans_s:Transformation)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH wu,
             count(DISTINCT wheel) AS wheel_count,
             count(DISTINCT external_trans) AS ac_re_count,
             collect(DISTINCT component) + collect(DISTINCT synth_comp) AS all_components

        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_trans_s:Transformation)-[:IS_SPIRAL_OF]->(other_wu2:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu2 <> wu

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans:Transition)
        OPTIONAL MATCH (trans)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (trans)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(wu)

        WITH wheel_count, ac_re_count,
             count(DISTINCT other_wu) + count(DISTINCT other_wu2) + count(DISTINCT cycle_or_spiral) AS component_vocab_count

        RETURN wheel_count > 0 OR ac_re_count > 0 OR component_vocab_count > 0 AS not_isolated
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        if result:
            return not result[0]["not_isolated"]

        return True

    @inject
    def count_usage(
        self,
        wisdom_unit: WisdomUnit,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> int:
        """
        Count distinct structural containers where this WisdomUnit is used.

        Args:
            wisdom_unit: The WisdomUnit to count usage for
            sid: Scope ID (injected from DI context)

        Returns:
            Count of distinct containers (0 if not in scope)
        """
        if wisdom_unit._id is None:
            return 0

        # Validate WU belongs to current scope
        if sid and wisdom_unit.sid != sid:
            return 0

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        OPTIONAL MATCH (wu)-[:BELONGS_TO_NEXUS]->(nexus:Nexus)-[:HAS_CYCLE]->(cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)

        OPTIONAL MATCH (external_trans:Transformation)-[:ACTION_REFLECTION]->(wu)
        WHERE NOT (external_trans)-[:IS_SPIRAL_OF]->(wu)

        RETURN count(DISTINCT wheel) + count(DISTINCT external_trans) AS usage_count
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        if result:
            return result[0]["usage_count"]

        return 0

    @inject
    def in_use(
        self,
        wisdom_unit: WisdomUnit,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if WisdomUnit is actively in use.

        Args:
            wisdom_unit: The WisdomUnit to check
            sid: Scope ID (injected from DI context)

        Returns:
            True if in use, False if orphaned or not in scope
        """
        return self.count_usage(wisdom_unit, sid=sid, graph_db=graph_db) > 0

    @inject
    def is_shared(
        self,
        wisdom_unit: WisdomUnit,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if any of this WU's components are shared.

        Args:
            wisdom_unit: The WisdomUnit to check
            sid: Scope ID (injected from DI context)

        Returns:
            True if any component is shared, False otherwise or not in scope
        """
        if wisdom_unit._id is None:
            return False

        # Validate WU belongs to current scope
        if sid and wisdom_unit.sid != sid:
            return False

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component:DialecticalComponent)

        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(trans:Transformation)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH wu, collect(DISTINCT component) + collect(DISTINCT synth_comp) AS all_components

        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_trans:Transformation)-[:IS_SPIRAL_OF]->(other_wu2:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu2 <> wu

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition:Transition)
        OPTIONAL MATCH (transition)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (transition)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(wu)

        WITH count(DISTINCT other_wu) + count(DISTINCT other_wu2) + count(DISTINCT cycle_or_spiral) AS shared_count

        RETURN shared_count > 0 AS has_shared
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        if result:
            return result[0]["has_shared"]

        return False
