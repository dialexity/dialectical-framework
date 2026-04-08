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
    from dialectical_framework.graph.nodes.polarity import Polarity


class WisdomUnitRepository:
    """
    Repository for WisdomUnit query operations and lifecycle management.

    All queries are automatically scoped by sid (injected from DI context).
    """

    @inject
    def find_by_polarity(
        self,
        polarity: Polarity,
        sid: Optional[str] = Provide[DI.sid],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[WisdomUnit]:
        """
        Find WisdomUnits that reference the given Polarity.

        Args:
            polarity: The Polarity (T-A pair) to query for
            sid: Scope ID (injected from DI context)

        Returns:
            List of WisdomUnits connected to this Polarity
        """
        if polarity._id is None:
            return []

        # Validate polarity belongs to current scope
        if sid and polarity.sid != sid:
            return []

        query = """
        MATCH (wu:WisdomUnit)-[:HAS_POLARITY]->(p:Polarity)
        WHERE id(p) = $polarity_id
        RETURN wu
        """

        results = graph_db.execute_and_fetch(query, {"polarity_id": polarity._id})
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
        // Pole positions (T+, T-, A+, A-) directly on WU
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['T_PLUS', 'T_MINUS', 'A_PLUS', 'A_MINUS']
        RETURN wu, type(r) AS rel_type

        UNION

        // T and A positions via Polarity
        MATCH (c:DialecticalComponent)-[r]->(p:Polarity)<-[:HAS_POLARITY]-(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'A']
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
        AND NOT exists((stmt_comp)-[:T|A]->(:Polarity))
        DETACH DELETE stmt_comp
        """
        graph_db.execute(delete_orphaned_stmt_query)

        # Delete the complete WU subgraph
        delete_subgraph_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Get pole components directly on WU (T+, T-, A+, A-)
        OPTIONAL MATCH (wu)<-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]-(pole_component)
        // Get Polarity and T/A components through it
        OPTIONAL MATCH (wu)-[:HAS_POLARITY]->(polarity:Polarity)
        OPTIONAL MATCH (polarity)<-[:T|A]-(polarity_comp)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(wu_rationale)
        OPTIONAL MATCH (pole_component)<-[:EXPLAINS]-(comp_rationale)
        OPTIONAL MATCH (polarity_comp)<-[:EXPLAINS]-(pol_comp_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:EXPLAINS]-(trans_rationale)
        OPTIONAL MATCH (transformation)<-[:AC|RE|AC_PLUS|AC_MINUS|RE_PLUS|RE_MINUS]-(trans_component)
        OPTIONAL MATCH (wu)<-[:SYNTHESIS_OF]-(synthesis:Synthesis)
        OPTIONAL MATCH (synthesis)<-[:EXPLAINS]-(synth_rationale)
        OPTIONAL MATCH (synthesis)<-[:S_PLUS|S_MINUS]-(synth_component)

        WITH wu, polarity,
             collect(DISTINCT pole_component) + collect(DISTINCT polarity_comp) AS components,
             collect(DISTINCT wu_rationale) + collect(DISTINCT comp_rationale) + collect(DISTINCT pol_comp_rationale) +
             collect(DISTINCT trans_rationale) +
             collect(DISTINCT synth_rationale) AS direct_rationales,
             collect(DISTINCT transformation) AS transformations,
             collect(DISTINCT trans_component) AS trans_components,
             collect(DISTINCT synthesis) AS syntheses,
             collect(DISTINCT synth_component) AS synth_components

        UNWIND CASE WHEN size(direct_rationales) > 0 THEN direct_rationales ELSE [null] END AS rat
        OPTIONAL MATCH (rat)<-[:CRITIQUES*0..10]-(critique_chain:Rationale)
        WHERE rat IS NOT NULL

        WITH wu, components, transformations, trans_components, syntheses, synth_components,
             direct_rationales, collect(DISTINCT critique_chain) AS critique_rationales

        WITH wu, components, transformations, trans_components, syntheses, synth_components,
             direct_rationales + critique_rationales AS rationales

        FOREACH (rat IN rationales | DETACH DELETE rat)
        FOREACH (tcomp IN trans_components | DETACH DELETE tcomp)
        FOREACH (transformation IN transformations | DETACH DELETE transformation)

        WITH wu, components, synth_components, syntheses
        UNWIND CASE WHEN size(synth_components) > 0 THEN synth_components ELSE [null] END AS scomp

        OPTIONAL MATCH (scomp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_wu:WisdomUnit)
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

        # Delete orphaned Polarities and their components
        # (Polarities that are no longer connected to any WisdomUnit)

        # Step 1: Delete orphaned components from orphaned Polarities (only if not used elsewhere)
        delete_orphaned_polarity_comps_query = """
        MATCH (pol:Polarity)
        WHERE NOT exists((pol)<-[:HAS_POLARITY]-(:WisdomUnit))
        MATCH (pol)<-[:T|A]-(comp:DialecticalComponent)
        // Only delete components if they're not used elsewhere
        WHERE NOT exists((comp)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(:WisdomUnit))
        AND NOT exists((comp)-[:T|A]->(:Polarity)<-[:HAS_POLARITY]-(:WisdomUnit))
        AND NOT exists((comp)-[:S_PLUS|S_MINUS]->(:Synthesis))
        AND NOT exists((comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(:Transition))
        DETACH DELETE comp
        """
        graph_db.execute(delete_orphaned_polarity_comps_query)

        # Step 2: Delete orphaned Polarities (now that components are handled)
        delete_orphaned_polarity_query = """
        MATCH (pol:Polarity)
        WHERE NOT exists((pol)<-[:HAS_POLARITY]-(:WisdomUnit))
        DETACH DELETE pol
        """
        graph_db.execute(delete_orphaned_polarity_query)

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

        // Check if WU is used in any Cycle (via wisdom_unit_hashes property)
        OPTIONAL MATCH (cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)
        WHERE wu.hash IN cycle.wisdom_unit_hashes

        // Check if WU is referenced by any Transformation via Wheel
        OPTIONAL MATCH (wheel2:Wheel)-[:HAS_TRANSFORMATION]->(external_trans:Transformation)
        WHERE wu.hash IN (()-[:HAS_WHEEL]->(wheel2)<-[:HAS_WHEEL]-(cycle2:Cycle)).wisdom_unit_hashes

        // Get pole components directly on WU (T+, T-, A+, A-)
        OPTIONAL MATCH (wu)<-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]-(pole_component:DialecticalComponent)
        // Get T/A components through Polarity
        OPTIONAL MATCH (wu)-[:HAS_POLARITY]->(polarity:Polarity)<-[:T|A]-(polarity_comp:DialecticalComponent)

        OPTIONAL MATCH (wu)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH wu,
             count(DISTINCT wheel) AS wheel_count,
             count(DISTINCT external_trans) AS ac_re_count,
             collect(DISTINCT pole_component) + collect(DISTINCT polarity_comp) + collect(DISTINCT synth_comp) AS all_components

        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        // Check if component is used in other WUs directly
        OPTIONAL MATCH (comp)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        // Check if component is used in other WUs through Polarity
        OPTIONAL MATCH (comp)-[:T|A]->(other_pol:Polarity)<-[:HAS_POLARITY]-(other_wu_pol:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu_pol <> wu

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_wu2:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu2 <> wu

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans:Transition)
        OPTIONAL MATCH (trans)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL

        WITH wheel_count, ac_re_count,
             count(DISTINCT other_wu) + count(DISTINCT other_wu_pol) + count(DISTINCT other_wu2) + count(DISTINCT cycle_or_spiral) AS component_vocab_count

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

        // Check if WU is used in any Cycle (via wisdom_unit_hashes property)
        OPTIONAL MATCH (cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)
        WHERE wu.hash IN cycle.wisdom_unit_hashes

        // Check if WU is referenced by any Transformation
        OPTIONAL MATCH (wheel2:Wheel)-[:HAS_TRANSFORMATION]->(trans:Transformation)
        WHERE wu.hash IN (()-[:HAS_WHEEL]->(wheel2)<-[:HAS_WHEEL]-(cycle2:Cycle)).wisdom_unit_hashes

        RETURN count(DISTINCT wheel) + count(DISTINCT trans) AS usage_count
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

        // Get pole components directly on WU (T+, T-, A+, A-)
        OPTIONAL MATCH (wu)<-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]-(pole_component:DialecticalComponent)
        // Get T/A components through Polarity
        OPTIONAL MATCH (wu)-[:HAS_POLARITY]->(polarity:Polarity)<-[:T|A]-(polarity_comp:DialecticalComponent)

        OPTIONAL MATCH (wu)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH wu, collect(DISTINCT pole_component) + collect(DISTINCT polarity_comp) + collect(DISTINCT synth_comp) AS all_components

        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        // Check if component is used in other WUs directly
        OPTIONAL MATCH (comp)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        // Check if component is used in other WUs through Polarity
        OPTIONAL MATCH (comp)-[:T|A]->(other_pol:Polarity)<-[:HAS_POLARITY]-(other_wu_pol:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu_pol <> wu

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_wu2:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu2 <> wu

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition:Transition)
        OPTIONAL MATCH (transition)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL

        WITH count(DISTINCT other_wu) + count(DISTINCT other_wu_pol) + count(DISTINCT other_wu2) + count(DISTINCT cycle_or_spiral) AS shared_count

        RETURN shared_count > 0 AS has_shared
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        if result:
            return result[0]["has_shared"]

        return False
