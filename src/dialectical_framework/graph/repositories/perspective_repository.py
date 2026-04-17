"""
PerspectiveRepository for complex query operations and lifecycle management.

All queries are scoped by case_id (injected from DI context) to prevent cross-user data leaks.
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.polarity import Polarity


class PerspectiveRepository:
    """
    Repository for Perspective query operations and lifecycle management.

    All queries are automatically scoped by case_id (injected from DI context).
    """

    @inject
    def find_by_polarity(
        self,
        polarity: Polarity,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Perspective]:
        """
        Find Perspectives that reference the given Polarity.

        Args:
            polarity: The Polarity (T-A pair) to query for
            case_id: Case ID (injected from DI context)

        Returns:
            List of Perspectives connected to this Polarity
        """
        if polarity._id is None:
            return []

        # Validate polarity belongs to current scope
        if case_id and polarity.case_id != case_id:
            return []

        query = """
        MATCH (pp:Perspective)-[:HAS_POLARITY]->(p:Polarity)
        WHERE id(p) = $polarity_id
        RETURN pp
        """

        results = graph_db.execute_and_fetch(query, {"polarity_id": polarity._id})
        return [result["pp"] for result in results]

    @inject
    def find_by_dialectical_component(
        self,
        component: DialecticalComponent,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[Perspective, str]]:
        """
        Find all Perspectives that contain this component.

        Args:
            component: The DialecticalComponent to query for
            case_id: Case ID (injected from DI context)

        Returns:
            List of tuples: (Perspective, relationship_type)
        """
        if component._id is None:
            return []

        # Validate component belongs to current scope
        if case_id and component.case_id != case_id:
            return []

        query = """
        // Angle positions (T+, T-, A+, A-) directly on Perspective
        MATCH (c:DialecticalComponent)-[r]->(pp:Perspective)
        WHERE id(c) = $component_id
        AND type(r) IN ['T_PLUS', 'T_MINUS', 'A_PLUS', 'A_MINUS']
        RETURN pp, type(r) AS rel_type

        UNION

        // T and A positions via Polarity
        MATCH (c:DialecticalComponent)-[r]->(p:Polarity)<-[:HAS_POLARITY]-(pp:Perspective)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'A']
        RETURN pp, type(r) AS rel_type

        UNION

        // Synthesis positions (S+, S-) via Synthesis node
        MATCH (c:DialecticalComponent)-[r]->(synth:Synthesis)-[:SYNTHESIS_OF]->(pp:Perspective)
        WHERE id(c) = $component_id
        AND type(r) IN ['S_PLUS', 'S_MINUS']
        RETURN pp, type(r) AS rel_type
        """

        results = graph_db.execute_and_fetch(query, {"component_id": component._id})
        return [(result["pp"], result["rel_type"]) for result in results]

    @inject
    def safe_delete(
        self,
        perspective: Perspective,
        force_gc: bool = True,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Safely delete a Perspective and its complete subgraph.

        Args:
            perspective: The Perspective to delete
            force_gc: If True (default), aggressive GC mode. If False, conservative mode.
            case_id: Case ID (injected from DI context)

        Returns:
            True if deleted, False if kept or not in scope
        """
        if perspective._id is None:
            return False

        # Validate Perspective belongs to current scope
        if case_id and perspective.case_id != case_id:
            return False

        if force_gc:
            if self.in_use(perspective, case_id=case_id, graph_db=graph_db):
                return False
        else:
            if not self.is_isolated(perspective, case_id=case_id, graph_db=graph_db):
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

        # Delete the complete Perspective subgraph
        delete_subgraph_query = """
        MATCH (pp:Perspective) WHERE id(pp) = $pp_id

        // Get angle components directly on Perspective (T+, T-, A+, A-)
        OPTIONAL MATCH (pp)<-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]-(angle_component)
        // Get Polarity and T/A components through it
        OPTIONAL MATCH (pp)-[:HAS_POLARITY]->(polarity:Polarity)
        OPTIONAL MATCH (polarity)<-[:T|A]-(polarity_comp)
        OPTIONAL MATCH (pp)<-[:EXPLAINS]-(pp_rationale)
        OPTIONAL MATCH (angle_component)<-[:EXPLAINS]-(comp_rationale)
        OPTIONAL MATCH (polarity_comp)<-[:EXPLAINS]-(pol_comp_rationale)
        OPTIONAL MATCH (pp)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:EXPLAINS]-(trans_rationale)
        OPTIONAL MATCH (transformation)<-[:AC|RE|AC_PLUS|AC_MINUS|RE_PLUS|RE_MINUS]-(trans_component)
        OPTIONAL MATCH (pp)<-[:SYNTHESIS_OF]-(synthesis:Synthesis)
        OPTIONAL MATCH (synthesis)<-[:EXPLAINS]-(synth_rationale)
        OPTIONAL MATCH (synthesis)<-[:S_PLUS|S_MINUS]-(synth_component)

        WITH pp, polarity,
             collect(DISTINCT angle_component) + collect(DISTINCT polarity_comp) AS components,
             collect(DISTINCT pp_rationale) + collect(DISTINCT comp_rationale) + collect(DISTINCT pol_comp_rationale) +
             collect(DISTINCT trans_rationale) +
             collect(DISTINCT synth_rationale) AS direct_rationales,
             collect(DISTINCT transformation) AS transformations,
             collect(DISTINCT trans_component) AS trans_components,
             collect(DISTINCT synthesis) AS syntheses,
             collect(DISTINCT synth_component) AS synth_components

        UNWIND CASE WHEN size(direct_rationales) > 0 THEN direct_rationales ELSE [null] END AS rat
        OPTIONAL MATCH (rat)<-[:CRITIQUES*0..10]-(critique_chain:Rationale)
        WHERE rat IS NOT NULL

        WITH pp, components, transformations, trans_components, syntheses, synth_components,
             direct_rationales, collect(DISTINCT critique_chain) AS critique_rationales

        WITH pp, components, transformations, trans_components, syntheses, synth_components,
             direct_rationales + critique_rationales AS rationales

        FOREACH (rat IN rationales | DETACH DELETE rat)
        FOREACH (tcomp IN trans_components | DETACH DELETE tcomp)
        FOREACH (transformation IN transformations | DETACH DELETE transformation)

        WITH pp, components, synth_components, syntheses
        UNWIND CASE WHEN size(synth_components) > 0 THEN synth_components ELSE [null] END AS scomp

        OPTIONAL MATCH (scomp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_pp:Perspective)
        WHERE scomp IS NOT NULL AND other_pp <> pp

        OPTIONAL MATCH (scomp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans_ref:Transition)
        OPTIONAL MATCH (trans_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE scomp IS NOT NULL

        WITH pp, components, syntheses, scomp,
             count(DISTINCT other_synth) + count(DISTINCT cycle_or_spiral) AS synth_vocab_count

        FOREACH (_ IN CASE WHEN scomp IS NOT NULL AND synth_vocab_count = 0 THEN [1] ELSE [] END |
            DETACH DELETE scomp
        )

        WITH DISTINCT pp, components, syntheses
        FOREACH (synth IN syntheses | DETACH DELETE synth)

        WITH pp, components
        UNWIND CASE WHEN size(components) > 0 THEN components ELSE [null] END AS comp

        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_pp:Perspective)
        WHERE comp IS NOT NULL AND other_pp <> pp

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(any_synth:Synthesis)
        WHERE comp IS NOT NULL

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition_ref:Transition)
        OPTIONAL MATCH (transition_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (transition_ref)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(pp)

        WITH pp, comp,
             count(DISTINCT other_pp) + count(DISTINCT any_synth) + count(DISTINCT cycle_or_spiral) AS vocab_count

        FOREACH (_ IN CASE WHEN comp IS NOT NULL AND vocab_count = 0 THEN [1] ELSE [] END |
            DETACH DELETE comp
        )

        WITH DISTINCT pp
        DETACH DELETE pp
        """
        graph_db.execute(delete_subgraph_query, {"pp_id": perspective._id})

        # Delete orphaned Polarities and their components
        # (Polarities that are no longer connected to any Perspective)

        # Step 1: Delete orphaned components from orphaned Polarities (only if not used elsewhere)
        delete_orphaned_polarity_comps_query = """
        MATCH (pol:Polarity)
        WHERE NOT exists((pol)<-[:HAS_POLARITY]-(:Perspective))
        MATCH (pol)<-[:T|A]-(comp:DialecticalComponent)
        // Only delete components if they're not used elsewhere
        WHERE NOT exists((comp)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(:Perspective))
        AND NOT exists((comp)-[:T|A]->(:Polarity)<-[:HAS_POLARITY]-(:Perspective))
        AND NOT exists((comp)-[:S_PLUS|S_MINUS]->(:Synthesis))
        AND NOT exists((comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(:Transition))
        DETACH DELETE comp
        """
        graph_db.execute(delete_orphaned_polarity_comps_query)

        # Step 2: Delete orphaned Polarities (now that components are handled)
        delete_orphaned_polarity_query = """
        MATCH (pol:Polarity)
        WHERE NOT exists((pol)<-[:HAS_POLARITY]-(:Perspective))
        DETACH DELETE pol
        """
        graph_db.execute(delete_orphaned_polarity_query)

        return True

    @inject
    def is_isolated(
        self,
        perspective: Perspective,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if a Perspective is isolated (not part of vocabulary at any level).

        Args:
            perspective: The Perspective to check
            case_id: Case ID (injected from DI context)

        Returns:
            True if isolated, False if in vocabulary or not in scope
        """
        if perspective._id is None:
            return True

        # Validate Perspective belongs to current scope
        if case_id and perspective.case_id != case_id:
            return False  # Not in scope = treat as not isolated (don't allow operations)

        query = """
        MATCH (pp:Perspective) WHERE id(pp) = $pp_id

        // Check if Perspective is used in any Cycle (via perspective_hashes property)
        OPTIONAL MATCH (cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)
        WHERE pp.hash IN cycle.perspective_hashes

        // Check if Perspective is referenced by any Transformation via Wheel
        OPTIONAL MATCH (wheel2:Wheel)-[:HAS_TRANSFORMATION]->(external_trans:Transformation)
        WHERE pp.hash IN (()-[:HAS_WHEEL]->(wheel2)<-[:HAS_WHEEL]-(cycle2:Cycle)).perspective_hashes

        // Get angle components directly on Perspective (T+, T-, A+, A-)
        OPTIONAL MATCH (pp)<-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]-(angle_component:DialecticalComponent)
        // Get T/A components through Polarity
        OPTIONAL MATCH (pp)-[:HAS_POLARITY]->(polarity:Polarity)<-[:T|A]-(polarity_comp:DialecticalComponent)

        OPTIONAL MATCH (pp)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH pp,
             count(DISTINCT wheel) AS wheel_count,
             count(DISTINCT external_trans) AS ac_re_count,
             collect(DISTINCT angle_component) + collect(DISTINCT polarity_comp) + collect(DISTINCT synth_comp) AS all_components

        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        // Check if component is used in other Perspectives directly
        OPTIONAL MATCH (comp)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(other_pp:Perspective)
        WHERE comp IS NOT NULL AND other_pp <> pp

        // Check if component is used in other Perspectives through Polarity
        OPTIONAL MATCH (comp)-[:T|A]->(other_pol:Polarity)<-[:HAS_POLARITY]-(other_pp_pol:Perspective)
        WHERE comp IS NOT NULL AND other_pp_pol <> pp

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_pp2:Perspective)
        WHERE comp IS NOT NULL AND other_pp2 <> pp

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans:Transition)
        OPTIONAL MATCH (trans)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL

        WITH wheel_count, ac_re_count,
             count(DISTINCT other_pp) + count(DISTINCT other_pp_pol) + count(DISTINCT other_pp2) + count(DISTINCT cycle_or_spiral) AS component_vocab_count

        RETURN wheel_count > 0 OR ac_re_count > 0 OR component_vocab_count > 0 AS not_isolated
        """
        result = list(graph_db.execute_and_fetch(query, {"pp_id": perspective._id}))
        if result:
            return not result[0]["not_isolated"]

        return True

    @inject
    def count_usage(
        self,
        perspective: Perspective,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> int:
        """
        Count distinct structural containers where this Perspective is used.

        Args:
            perspective: The Perspective to count usage for
            case_id: Case ID (injected from DI context)

        Returns:
            Count of distinct containers (0 if not in scope)
        """
        if perspective._id is None:
            return 0

        # Validate Perspective belongs to current scope
        if case_id and perspective.case_id != case_id:
            return 0

        query = """
        MATCH (pp:Perspective) WHERE id(pp) = $pp_id

        // Check if Perspective is used in any Cycle (via perspective_hashes property)
        OPTIONAL MATCH (cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)
        WHERE pp.hash IN cycle.perspective_hashes

        // Check if Perspective is referenced by any Transformation
        OPTIONAL MATCH (wheel2:Wheel)-[:HAS_TRANSFORMATION]->(trans:Transformation)
        WHERE pp.hash IN (()-[:HAS_WHEEL]->(wheel2)<-[:HAS_WHEEL]-(cycle2:Cycle)).perspective_hashes

        RETURN count(DISTINCT wheel) + count(DISTINCT trans) AS usage_count
        """
        result = list(graph_db.execute_and_fetch(query, {"pp_id": perspective._id}))
        if result:
            return result[0]["usage_count"]

        return 0

    @inject
    def in_use(
        self,
        perspective: Perspective,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if Perspective is actively in use.

        Args:
            perspective: The Perspective to check
            case_id: Case ID (injected from DI context)

        Returns:
            True if in use, False if orphaned or not in scope
        """
        return self.count_usage(perspective, case_id=case_id, graph_db=graph_db) > 0

    @inject
    def is_shared(
        self,
        perspective: Perspective,
        case_id: Optional[str] = Provide[DI.case_id],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if any of this Perspective's components are shared.

        Args:
            perspective: The Perspective to check
            case_id: Case ID (injected from DI context)

        Returns:
            True if any component is shared, False otherwise or not in scope
        """
        if perspective._id is None:
            return False

        # Validate Perspective belongs to current scope
        if case_id and perspective.case_id != case_id:
            return False

        query = """
        MATCH (pp:Perspective) WHERE id(pp) = $pp_id

        // Get angle components directly on Perspective (T+, T-, A+, A-)
        OPTIONAL MATCH (pp)<-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]-(angle_component:DialecticalComponent)
        // Get T/A components through Polarity
        OPTIONAL MATCH (pp)-[:HAS_POLARITY]->(polarity:Polarity)<-[:T|A]-(polarity_comp:DialecticalComponent)

        OPTIONAL MATCH (pp)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH pp, collect(DISTINCT angle_component) + collect(DISTINCT polarity_comp) + collect(DISTINCT synth_comp) AS all_components

        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        // Check if component is used in other Perspectives directly
        OPTIONAL MATCH (comp)-[:T_PLUS|T_MINUS|A_PLUS|A_MINUS]->(other_pp:Perspective)
        WHERE comp IS NOT NULL AND other_pp <> pp

        // Check if component is used in other Perspectives through Polarity
        OPTIONAL MATCH (comp)-[:T|A]->(other_pol:Polarity)<-[:HAS_POLARITY]-(other_pp_pol:Perspective)
        WHERE comp IS NOT NULL AND other_pp_pol <> pp

        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_pp2:Perspective)
        WHERE comp IS NOT NULL AND other_pp2 <> pp

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition:Transition)
        OPTIONAL MATCH (transition)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL

        WITH count(DISTINCT other_pp) + count(DISTINCT other_pp_pol) + count(DISTINCT other_pp2) + count(DISTINCT cycle_or_spiral) AS shared_count

        RETURN shared_count > 0 AS has_shared
        """
        result = list(graph_db.execute_and_fetch(query, {"pp_id": perspective._id}))
        if result:
            return result[0]["has_shared"]

        return False
