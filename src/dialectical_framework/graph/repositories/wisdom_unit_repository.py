"""
WisdomUnitRepository for complex query operations and lifecycle management.

This repository separates data access logic from the WisdomUnit node model,
keeping the model clean and declarative while centralizing complex queries
and safe deletion operations.
"""

from __future__ import annotations

from typing import Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class WisdomUnitRepository:
    """
    Repository for WisdomUnit query operations and lifecycle management.

    This class handles complex queries, traversals, and safe deletion operations
    for WisdomUnit nodes, following the Repository pattern.

    Example usage:
        from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository

        wu = WisdomUnit(reasoning_mode="GENERAL_CONCEPTS")
        wu.save()

        repo = WisdomUnitRepository()
        deleted = repo.safe_delete(wu)
        if deleted:
            print(f"WisdomUnit {wu.uid} and its isolated subgraph deleted")
        else:
            print(f"WisdomUnit {wu.uid} is shared, kept as orphan")
    """

    @inject
    def find_by_dialectical_component(
        self,
        component: DialecticalComponent,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[WisdomUnit, str]]:
        """
        Find all WisdomUnits that contain this component.

        Args:
            component: The DialecticalComponent to query for
            graph_db: Database connection (injected via DI)

        Returns:
            List of tuples: (WisdomUnit, relationship_type)
            Example: [(wu1, "T"), (wu2, "T_PLUS")]

        Example:
            component = DialecticalComponent(statement="Democracy")
            component.save()

            repo = WisdomUnitRepository()
            wisdom_units = repo.find_by_dialectical_component(component)
            for wu, rel_type in wisdom_units:
                print(f"Component belongs to {wu.uid} as {rel_type}")
        """
        if component._id is None:
            return []

        query = """
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(c) = $component_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS', 'S_PLUS', 'S_MINUS']
        RETURN wu, type(r) as rel_type
        """

        results = graph_db.execute_and_fetch(query, {"component_id": component._id})
        return [(result["wu"], result["rel_type"]) for result in results]

    @inject
    def safe_delete(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Safely delete a WisdomUnit and its complete subgraph.

        **Deletion Logic:**

        1. **Vocabulary Check** (via is_isolated()):
           - Checks if WU is in any wheel (Level 2 vocabulary)
           - Checks if any component is in vocabulary (Level 1 vocabulary)
           - If NOT isolated → Keep as provenance (return False)
           - If isolated → Proceed with deletion

        2. **Recursive Deletion** (if isolated):
           - WisdomUnit itself
           - Transformation, Transitions, Synthesis nodes
           - Rationales, Estimations (attributes of their parents)
           - HAS_STATEMENT derived components (if orphaned)

        3. **DialecticalComponent Smart Handling**:
           For each component (T, A, T+, T-, A+, A-, S+, S-):
           - **If in vocabulary** (polarity rels to other WUs, in Cycles/Spirals) → DETACH only
           - **If orphaned** → DELETE component AND its rationales/estimations

        **Two-Level Vocabulary Preservation:**
        - **Level 1**: DialecticalComponents (statements) can be shared
        - **Level 2**: WisdomUnits (polarities) can be shared across wheels

        Both levels are preserved when in use, keeping provenance for future reuse.

        Args:
            wisdom_unit: The WisdomUnit to delete
            graph_db: Database connection (injected via DI)

        Returns:
            True if deleted (WU was isolated)
            False if kept as provenance (WU or components in vocabulary)

        Example:
            # After disconnecting from wheel
            transformation.ac_re.disconnect(old_ac_re)
            if repo.is_isolated(old_ac_re):
                repo.safe_delete(old_ac_re)  # Deletes if truly isolated
            # Otherwise kept as Level 2 vocabulary
        """
        if wisdom_unit._id is None:
            return False  # Not saved, nothing to delete

        # PRIMARY CHECK: Is WU isolated (vocabulary check)?
        if not self.is_isolated(wisdom_unit, graph_db=graph_db):
            # WU or its components are in vocabulary - keep as provenance
            return False

        # Subgraph is fully isolated - safe to recursively delete everything
        # HAS_STATEMENT is a boundary: disconnect link, delete component only if orphaned

        # Step 1: Handle HAS_STATEMENT boundary (do this BEFORE deleting rationales/transitions)
        # Disconnect HAS_STATEMENT links from rationales and transitions
        disconnect_has_statement_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Find all rationales in subgraph (including critiques - recursive)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(wu_rationale)
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component)
        OPTIONAL MATCH (component)<-[:EXPLAINS]-(comp_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:EXPLAINS]-(trans_rationale)
        OPTIONAL MATCH (transformation)<-[:BELONGS_TO_CYCLE]-(transition:Transition)
        OPTIONAL MATCH (transition)<-[:EXPLAINS]-(transit_rationale)
        OPTIONAL MATCH (wu)<-[:SYNTHESIS_OF]-(synthesis:Synthesis)
        OPTIONAL MATCH (synthesis)<-[:EXPLAINS]-(synth_rationale)

        WITH collect(DISTINCT wu_rationale) + collect(DISTINCT comp_rationale) +
             collect(DISTINCT trans_rationale) + collect(DISTINCT transit_rationale) +
             collect(DISTINCT synth_rationale) AS all_rationales,
             collect(DISTINCT transition) AS transitions

        // Disconnect HAS_STATEMENT from rationales (including recursive critiques)
        UNWIND all_rationales AS rat
        OPTIONAL MATCH (rat)-[:CRITIQUES*0..10]->(child_rat:Rationale)
        OPTIONAL MATCH (child_rat)-[has_stmt_r:HAS_STATEMENT]->(:DialecticalComponent)
        WHERE has_stmt_r IS NOT NULL
        DELETE has_stmt_r

        WITH transitions

        // Disconnect HAS_STATEMENT from transitions (derived_statements)
        UNWIND transitions AS trans
        OPTIONAL MATCH (trans)-[has_stmt_t:HAS_STATEMENT]->(:DialecticalComponent)
        WHERE has_stmt_t IS NOT NULL
        DELETE has_stmt_t
        """
        graph_db.execute(disconnect_has_statement_query, {"wu_id": wisdom_unit._id})

        # Step 2: Delete orphaned HAS_STATEMENT components (not in any WU or Synthesis)
        delete_orphaned_stmt_query = """
        MATCH (stmt_comp:DialecticalComponent)
        WHERE NOT exists((stmt_comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]->())
        AND NOT exists((stmt_comp)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]-())
        DETACH DELETE stmt_comp
        """
        graph_db.execute(delete_orphaned_stmt_query)

        # Step 3: Delete the complete WU subgraph
        delete_subgraph_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Find all nodes in subgraph
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(wu_rationale)
        OPTIONAL MATCH (component)<-[:EXPLAINS]-(comp_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:EXPLAINS]-(trans_rationale)
        OPTIONAL MATCH (transformation)<-[:BELONGS_TO_CYCLE]-(transition:Transition)
        OPTIONAL MATCH (transition)<-[:EXPLAINS]-(transit_rationale)
        OPTIONAL MATCH (wu)<-[:SYNTHESIS_OF]-(synthesis:Synthesis)
        OPTIONAL MATCH (synthesis)<-[:EXPLAINS]-(synth_rationale)
        OPTIONAL MATCH (synthesis)<-[:S_PLUS|S_MINUS]-(synth_component)

        // Collect nodes for deletion (DETACH DELETE will handle estimations automatically)
        WITH wu,
             collect(DISTINCT component) AS components,
             collect(DISTINCT wu_rationale) AS wu_rationales,
             collect(DISTINCT comp_rationale) AS comp_rationales,
             collect(DISTINCT transformation) AS transformations,
             collect(DISTINCT trans_rationale) AS trans_rationales,
             collect(DISTINCT transition) AS transitions,
             collect(DISTINCT transit_rationale) AS transit_rationales,
             collect(DISTINCT synthesis) AS syntheses,
             collect(DISTINCT synth_rationale) AS synth_rationales,
             collect(DISTINCT synth_component) AS synth_components

        // Combine all rationales for deletion (DETACH DELETE handles recursive critiques)
        WITH wu, components, transformations, transitions, syntheses, synth_components,
             wu_rationales + comp_rationales + trans_rationales + transit_rationales + synth_rationales AS rationales

        // Delete in proper order (DETACH DELETE removes all relationships including estimations)
        FOREACH (rat IN rationales | DETACH DELETE rat)
        FOREACH (trans IN transitions | DETACH DELETE trans)
        FOREACH (transformation IN transformations | DETACH DELETE transformation)
        FOREACH (scomp IN synth_components | DETACH DELETE scomp)
        FOREACH (synth IN syntheses | DETACH DELETE synth)

        // For components: check each one's vocabulary status before deletion
        // Components are "in vocabulary" if they have polarity or synthesis relationships
        WITH wu, components
        UNWIND components AS comp

        // Disconnect component from this WU (already done by DETACH DELETE wu below)
        // Check if component is orphaned (not in vocabulary)
        OPTIONAL MATCH (comp)-[vocab_rel:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]->(other_wu)
        WHERE other_wu <> wu

        OPTIONAL MATCH (comp)<-[vocab_rel_in:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]-(other_wu_in)
        WHERE other_wu_in <> wu

        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition_ref:Transition)
        OPTIONAL MATCH (transition_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)

        WITH wu, comp,
             count(vocab_rel) + count(vocab_rel_in) + count(cycle_or_spiral) AS vocab_count

        // Delete component only if orphaned (not in vocabulary)
        FOREACH (_ IN CASE WHEN vocab_count = 0 THEN [1] ELSE [] END |
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
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if a WisdomUnit is isolated (not part of vocabulary at any level).

        **Two-Level Vocabulary Architecture:**

        1. **Level 1 Vocabulary - Statements**: DialecticalComponents
           - Can be reused across multiple WisdomUnits
           - Can be source/target in Cycles/Spirals (transitively in wheels)

        2. **Level 2 Vocabulary - Polarities**: WisdomUnits
           - Can be reused across multiple Wheels
           - Can be used as ac_re in Transformations

        **Isolation Criteria:**

        A WisdomUnit is isolated ONLY if ALL of the following are true:

        1. **WU Level Check**: WU is NOT in any wheel
           - No BELONGS_TO_WHEEL relationship to any Wheel

        2. **Component Level Check**: ALL components are NOT in vocabulary
           - No polarity relationships (T/A/T+/T-/A+/A-/S+/S-) to other WUs
           - Not source/target of Transitions in Cycles/Spirals

        If isolated, the WU can be safely deleted.
        If NOT isolated, the WU should be kept as "provenance" - higher-level vocabulary
        for future reuse.

        Args:
            wisdom_unit: The WisdomUnit to check
            graph_db: Database connection (injected via DI)

        Returns:
            True if WU and all its components are isolated (safe to delete)
            False if WU or any component is in vocabulary (keep for provenance)

        Example:
            # Check before deletion
            if repo.is_isolated(wu):
                repo.safe_delete(wu)  # Safe to delete
            else:
                # Keep as provenance (vocabulary for future wheels)
                pass
        """
        if wisdom_unit._id is None:
            return True  # Not saved = isolated by definition

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Level 2 Check: Is WU in any wheel or referenced as ac_re?
        OPTIONAL MATCH (wu)-[:BELONGS_TO_WHEEL]->(wheel:Wheel)

        // Check if WU is used as ac_re by external Transformations
        OPTIONAL MATCH (external_trans:Transformation)-[:ACTION_REFLECTION]->(wu)
        WHERE NOT (external_trans)-[:IS_SPIRAL_OF]->(wu)

        // Level 1 Check: Are any components in vocabulary?
        // Find all components of this WU
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component:DialecticalComponent)

        WITH wu,
             count(DISTINCT wheel) AS wheel_count,
             count(DISTINCT external_trans) AS ac_re_count,
             collect(DISTINCT component) AS components

        // For each component, check if it's in vocabulary
        UNWIND CASE WHEN size(components) > 0 THEN components ELSE [null] END AS comp

        // Check 1: Component has polarity relationships to OTHER WUs
        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]-(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        // Check 2: Component is source/target of Transition in EXTERNAL Cycle/Spiral
        // (Exclude transitions belonging to THIS WU's own Transformation)
        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans:Transition)
        OPTIONAL MATCH (trans)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (trans)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(wu)

        WITH wheel_count, ac_re_count,
             count(DISTINCT other_wu) + count(DISTINCT cycle_or_spiral) AS component_vocab_count

        // NOT isolated if: in wheel OR used as ac_re OR any component is in vocabulary
        RETURN wheel_count > 0 OR ac_re_count > 0 OR component_vocab_count > 0 AS not_isolated
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        if result:
            return not result[0]["not_isolated"]  # Flip: not_isolated=False means isolated=True

        return True  # Default to isolated if query fails

