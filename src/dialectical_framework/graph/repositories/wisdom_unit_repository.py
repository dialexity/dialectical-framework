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

        wu = WisdomUnit(intent="preset:general_concepts")
        wu.save()

        repo = WisdomUnitRepository()
        deleted = repo.safe_delete(wu)
        if deleted:
            print(f"WisdomUnit {wu.hash} and its isolated subgraph deleted")
        else:
            print(f"WisdomUnit {wu.hash} is shared, kept as orphan")
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
            component.commit()

            repo = WisdomUnitRepository()
            wisdom_units = repo.find_by_dialectical_component(component)
            for wu, rel_type in wisdom_units:
                print(f"Component belongs to {wu.hash} as {rel_type}")
        """
        if component._id is None:
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
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Safely delete a WisdomUnit and its complete subgraph.

        **Deletion Modes:**

        **Garbage Collection Mode (force_gc=True, default):**
        1. **Aggressive WU Deletion** - Only check Level 2 (use in_use()):
           - If WU in use (in wheel or as ac_re) → Keep (return False)
           - If WU NOT in use → Delete WU structure (ignore component sharing)
           - This cleans up orphaned WUs that aren't actively used
           - **Components are preserved:** Shared components are DETACHED (kept in graph),
             only orphaned components are DELETED

        **Conservative Mode (force_gc=False):**
        1. **Full Vocabulary Check** (via is_isolated()):
           - Checks if WU is in use (Level 2 vocabulary)
           - Checks if any component is shared (Level 1 vocabulary via is_shared())
           - If NOT isolated → Keep as provenance (return False)
           - If isolated → Proceed with deletion

        **Recursive Deletion** (when deletion proceeds):
        - WisdomUnit itself
        - Transformation, Transitions, Synthesis nodes
        - Rationales, Estimations (attributes of their parents)
        - HAS_STATEMENT derived components (if orphaned)

        **DialecticalComponent Smart Handling** (always applied):
        For each component (T, A, T+, T-, A+, A-, S+, S-):
        - **If in vocabulary** (polarity rels to other WUs, in Cycles/Spirals) → DETACH only
        - **If orphaned** → DELETE component AND its rationales/estimations

        **Two-Level Vocabulary Preservation:**
        - **Level 1**: DialecticalComponents (statements) can be shared
        - **Level 2**: WisdomUnits (polarities) can be shared across wheels

        Args:
            wisdom_unit: The WisdomUnit to delete
            force_gc: If True (default), aggressive GC mode. If False, conservative mode.
            graph_db: Database connection (injected via DI)

        Returns:
            True if deleted
            False if kept (in use, or in vocabulary if force_gc=False)

        Examples:
            # GC mode (default) - deletes if not in_use()
            repo.safe_delete(wu)  # Ignores component sharing

            # Conservative mode - deletes only if isolated (not in_use AND not shared)
            repo.safe_delete(wu, force_gc=False)  # Respects all vocabulary

            # When you want to know BEFORE deleting:
            if repo.is_isolated(wu):
                print("Will be deleted in conservative mode")
            else:
                print("Will be preserved in conservative mode")

            # Decide which mode to use:
            if repo.in_use(wu):
                print("WU is in use - can't delete in any mode")
            elif repo.is_shared(wu):
                print("WU not in use but has shared components")
                repo.safe_delete(wu, force_gc=True)  # Delete WU, preserve components
            else:
                print("WU is fully isolated - can delete everything")
                repo.safe_delete(wu)  # Either mode works
        """
        if wisdom_unit._id is None:
            return False  # Not saved, nothing to delete

        if force_gc:
            # AGGRESSIVE GC MODE: Only check Level 2 (WU usage)
            # Allow deletion if WU is not in use (ignore component sharing)
            if self.in_use(wisdom_unit):
                # WU is in a wheel or used as ac_re - keep it
                return False
            # Otherwise proceed with deletion (components still handled smartly)
        else:
            # CONSERVATIVE MODE: Full vocabulary check (both levels)
            if not self.is_isolated(wisdom_unit):
                # WU or its components are in vocabulary - keep as provenance
                return False

        # Subgraph is fully isolated - safe to recursively delete everything
        # HAS_STATEMENT is a boundary: disconnect link, delete component only if orphaned

        # Step 1: Delete orphaned HAS_STATEMENT components (not in any WU or Synthesis)
        # Note: HAS_STATEMENT now only exists on Input nodes, not on Rationales/Transitions
        delete_orphaned_stmt_query = """
        MATCH (stmt_comp:DialecticalComponent)
        WHERE NOT exists((stmt_comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]->())
        AND NOT exists((stmt_comp)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS|S_PLUS|S_MINUS]-())
        DETACH DELETE stmt_comp
        """
        graph_db.execute(delete_orphaned_stmt_query)

        # Step 2: Delete the complete WU subgraph
        delete_subgraph_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Find all nodes in subgraph (direct relationships)
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

        // Collect direct rationales first
        WITH wu,
             collect(DISTINCT component) AS components,
             collect(DISTINCT wu_rationale) + collect(DISTINCT comp_rationale) +
             collect(DISTINCT trans_rationale) + collect(DISTINCT transit_rationale) +
             collect(DISTINCT synth_rationale) AS direct_rationales,
             collect(DISTINCT transformation) AS transformations,
             collect(DISTINCT transition) AS transitions,
             collect(DISTINCT synthesis) AS syntheses,
             collect(DISTINCT synth_component) AS synth_components

        // Expand to include critique chains (rationales that critique the direct rationales)
        // Direction: critique -[:CRITIQUES]-> target, so traverse INCOMING edges
        UNWIND CASE WHEN size(direct_rationales) > 0 THEN direct_rationales ELSE [null] END AS rat
        OPTIONAL MATCH (rat)<-[:CRITIQUES*0..10]-(critique_chain:Rationale)
        WHERE rat IS NOT NULL

        WITH wu, components, transformations, transitions, syntheses, synth_components,
             direct_rationales, collect(DISTINCT critique_chain) AS critique_rationales

        // Combine all rationales (direct + critique chains)
        WITH wu, components, transformations, transitions, syntheses, synth_components,
             direct_rationales + critique_rationales AS rationales

        // Delete rationales first (including critique chains)
        FOREACH (rat IN rationales | DETACH DELETE rat)
        FOREACH (trans IN transitions | DETACH DELETE trans)
        FOREACH (transformation IN transformations | DETACH DELETE transformation)

        // For synthesis components: check vocabulary status before deletion
        // Synth components are "in vocabulary" if they have S+/S- to OTHER Syntheses
        WITH wu, components, synth_components, syntheses
        UNWIND CASE WHEN size(synth_components) > 0 THEN synth_components ELSE [null] END AS scomp

        // Check if synth component is used in another WU's Synthesis (via Transformation)
        OPTIONAL MATCH (scomp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_trans:Transformation)-[:IS_SPIRAL_OF]->(other_wu:WisdomUnit)
        WHERE scomp IS NOT NULL AND other_wu <> wu

        // Check if synth component is source/target of Transition
        OPTIONAL MATCH (scomp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans_ref:Transition)
        OPTIONAL MATCH (trans_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE scomp IS NOT NULL

        WITH wu, components, syntheses, scomp,
             count(DISTINCT other_synth) + count(DISTINCT cycle_or_spiral) AS synth_vocab_count

        // Delete synth component only if orphaned
        FOREACH (_ IN CASE WHEN scomp IS NOT NULL AND synth_vocab_count = 0 THEN [1] ELSE [] END |
            DETACH DELETE scomp
        )

        WITH DISTINCT wu, components, syntheses
        FOREACH (synth IN syntheses | DETACH DELETE synth)

        // For core components: check vocabulary status before deletion
        // Core components are "in vocabulary" if they have polarity rels to other WUs
        WITH wu, components
        UNWIND CASE WHEN size(components) > 0 THEN components ELSE [null] END AS comp

        // Check 1: Core component has polarity relationships to OTHER WUs
        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        // Check 2: Core component is used as S+/S- in ANY Synthesis (possibly in other WU)
        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(any_synth:Synthesis)
        WHERE comp IS NOT NULL

        // Check 3: Component is source/target of Transition in external Cycle/Spiral
        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(transition_ref:Transition)
        OPTIONAL MATCH (transition_ref)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (transition_ref)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(wu)

        WITH wu, comp,
             count(DISTINCT other_wu) + count(DISTINCT any_synth) + count(DISTINCT cycle_or_spiral) AS vocab_count

        // Delete component only if orphaned (not in vocabulary)
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

        1. **WU Level Check**: WU is NOT in any wheel (via Nexus hierarchy)
           - No path: WU → Nexus → Cycle → Wheel

        2. **ac_re Check**: WU is NOT used as action-reflection context
           - No external Transformation references this WU via ACTION_REFLECTION

        3. **Component Level Check**: ALL components are NOT in vocabulary
           - No polarity relationships (T/A/T+/T-/A+/A-) to other WUs
           - No S+/S- relationships to other Syntheses (→ other WUs)
           - Not source/target of Transitions in external Cycles/Spirals

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

        // Level 2 Check: Is WU in any wheel via Nexus hierarchy?
        OPTIONAL MATCH (wu)-[:BELONGS_TO_NEXUS]->(nexus:Nexus)-[:HAS_CYCLE]->(cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)

        // Check if WU is used as ac_re by external Transformations
        OPTIONAL MATCH (external_trans:Transformation)-[:ACTION_REFLECTION]->(wu)
        WHERE NOT (external_trans)-[:IS_SPIRAL_OF]->(wu)

        // Level 1 Check: Are any core components (T, A, T+, T-, A+, A-) in vocabulary?
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component:DialecticalComponent)

        // Also get synthesis components via Transformation
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(trans_s:Transformation)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH wu,
             count(DISTINCT wheel) AS wheel_count,
             count(DISTINCT external_trans) AS ac_re_count,
             collect(DISTINCT component) + collect(DISTINCT synth_comp) AS all_components

        // For each component, check if it's in vocabulary
        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        // Check 1: Core component has polarity relationships to OTHER WUs
        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        // Check 2: Synthesis component is in another WU's Synthesis (via Transformation)
        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_trans_s:Transformation)-[:IS_SPIRAL_OF]->(other_wu2:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu2 <> wu

        // Check 3: Component is source/target of Transition in EXTERNAL Cycle/Spiral
        // (Exclude transitions belonging to THIS WU's own Transformation)
        OPTIONAL MATCH (comp)-[:IS_SOURCE_OF|IS_TARGET_OF]-(trans:Transition)
        OPTIONAL MATCH (trans)-[:BELONGS_TO_CYCLE]->(cycle_or_spiral)
        WHERE comp IS NOT NULL
          AND NOT (trans)-[:BELONGS_TO_CYCLE]->(:Transformation)-[:IS_SPIRAL_OF]->(wu)

        WITH wheel_count, ac_re_count,
             count(DISTINCT other_wu) + count(DISTINCT other_wu2) + count(DISTINCT cycle_or_spiral) AS component_vocab_count

        // NOT isolated if: in wheel OR used as ac_re OR any component is in vocabulary
        RETURN wheel_count > 0 OR ac_re_count > 0 OR component_vocab_count > 0 AS not_isolated
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        if result:
            return not result[0]["not_isolated"]  # Flip: not_isolated=False means isolated=True

        return True  # Default to isolated if query fails

    @inject
    def count_usage(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> int:
        """
        Count distinct structural containers where this WisdomUnit is used.

        A WU can be used in:
        - Wheels (via Nexus → Cycle → Wheel hierarchy) - Level 2 vocabulary
        - Transformations (as ac_re via ACTION_REFLECTION) - Level 2 vocabulary

        This helps determine how "valuable" a WU is as provenance.

        Args:
            wisdom_unit: The WisdomUnit to count usage for
            graph_db: Database connection (injected via DI)

        Returns:
            Count of distinct containers using this WU (0 = orphaned)

        Example:
            usage = repo.count_usage(wu)
            if usage == 0:
                # Orphaned WU, candidate for garbage collection
                repo.safe_delete(wu, force_gc=True)
            elif usage == 1:
                # Used in one place, keep as provenance
                pass
            else:
                # Heavily reused, important vocabulary
                pass
        """
        if wisdom_unit._id is None:
            return 0  # Not saved = no usage

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Count wheels via Nexus hierarchy
        OPTIONAL MATCH (wu)-[:BELONGS_TO_NEXUS]->(nexus:Nexus)-[:HAS_CYCLE]->(cycle:Cycle)-[:HAS_WHEEL]->(wheel:Wheel)

        // Count external transformations using this as ac_re
        OPTIONAL MATCH (external_trans:Transformation)-[:ACTION_REFLECTION]->(wu)
        WHERE NOT (external_trans)-[:IS_SPIRAL_OF]->(wu)

        // Return count of DISTINCT containers
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
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if WisdomUnit is actively in use (Level 2 vocabulary).

        A WU is "in use" if it's in any wheel or used as ac_re by a transformation.
        This is a convenience wrapper around count_usage() > 0.

        Args:
            wisdom_unit: The WisdomUnit to check
            graph_db: Database connection (injected via DI)

        Returns:
            True if WU is in use (count_usage() > 0)
            False if WU is orphaned (count_usage() == 0)

        Example:
            if not repo.in_use(wu):
                # WU is orphaned - candidate for GC
                repo.safe_delete(wu)  # Default GC mode deletes it
        """
        return self.count_usage(wisdom_unit) > 0

    @inject
    def is_shared(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if any of this WU's components are shared (Level 1 vocabulary).

        Components are "shared" if they have:
        - Polarity relationships to other WUs (T/A/T+/T-/A+/A-/S+/S-)
        - Transition relationships to external Cycles/Spirals

        This indicates Level 1 vocabulary value (statement provenance).

        **Relationship to other methods:**
        - is_isolated() = NOT in_use() AND NOT is_shared()
        - If is_isolated() and not is_shared() → equivalent to not in_use()

        Args:
            wisdom_unit: The WisdomUnit to check
            graph_db: Database connection (injected via DI)

        Returns:
            True if any component is shared (in vocabulary)
            False if all components are exclusive to this WU

        Example:
            if not repo.in_use(wu) and not repo.is_shared(wu):
                # No vocabulary value at any level - safe to GC
                repo.safe_delete(wu)  # Default GC mode deletes it
        """
        if wisdom_unit._id is None:
            return False  # Not saved = no sharing

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Find all core components of this WU (T, A, T+, T-, A+, A-)
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component:DialecticalComponent)

        // Also get synthesis components (S+, S-) via Transformation
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(trans:Transformation)<-[:SYNTHESIS_OF]-(synth:Synthesis)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        WITH wu, collect(DISTINCT component) + collect(DISTINCT synth_comp) AS all_components

        // For each component, check if it's shared
        UNWIND CASE WHEN size(all_components) > 0 THEN all_components ELSE [null] END AS comp

        // Check 1: Core component has polarity relationships to OTHER WUs
        OPTIONAL MATCH (comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(other_wu:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu <> wu

        // Check 2: Synthesis component is in another WU's Synthesis (via Transformation)
        OPTIONAL MATCH (comp)-[:S_PLUS|S_MINUS]->(other_synth:Synthesis)-[:SYNTHESIS_OF]->(other_trans:Transformation)-[:IS_SPIRAL_OF]->(other_wu2:WisdomUnit)
        WHERE comp IS NOT NULL AND other_wu2 <> wu

        // Check 3: Component is source/target of Transition in EXTERNAL Cycle/Spiral
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

