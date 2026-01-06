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
        Safely delete a WisdomUnit and its isolated subgraph.

        Performs isolation check before deletion:
        1. Checks if WisdomUnit has any incoming relationships
        2. Checks if any connected nodes (components, rationales) have external references
        3. Only deletes if the entire subgraph is isolated (not shared)

        This prevents accidentally deleting components that are reused across
        multiple WisdomUnits (e.g., shared thesis components).

        The deletion is recursive and includes:
        - The WisdomUnit itself
        - All connected DialecticalComponents (T, A, T+, T-, A+, A-)
        - All rationales attached to the WisdomUnit
        - All rationales attached to the components

        Args:
            wisdom_unit: The WisdomUnit to delete
            graph_db: Database connection (injected via DI)

        Returns:
            True if deleted (subgraph was isolated)
            False if kept (subgraph has external references)

        Example:
            # Delete an AC/RE WisdomUnit that's no longer referenced
            old_ac_re = transformation.ac_re.get()[0]
            transformation.ac_re.disconnect(old_ac_re)
            repo.safe_delete(old_ac_re)  # Cleans up if isolated
        """
        if wisdom_unit._id is None:
            return False  # Not saved, nothing to delete

        # Check if subgraph is isolated using dedicated method
        if not self.is_isolated(wisdom_unit, graph_db=graph_db):
            # Subgraph is shared with other parts of the graph - don't delete
            # Keep as orphan for future garbage collection
            return False

        # Subgraph is fully isolated - safe to recursively delete everything
        # HAS_STATEMENT is a boundary: disconnect link, delete component only if orphaned

        # Handle HAS_STATEMENT boundary (do this BEFORE deleting rationales)
        # Step 1: Disconnect all HAS_STATEMENT links from this WU's rationales
        disconnect_has_statement_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(rationale)
        OPTIONAL MATCH (rationale)-[has_stmt:HAS_STATEMENT]->(stmt_comp:DialecticalComponent)
        WHERE has_stmt IS NOT NULL
        DELETE has_stmt
        """
        graph_db.execute(disconnect_has_statement_query, {"wu_id": wisdom_unit._id})

        # Step 2: Delete orphaned HAS_STATEMENT components (not in any WU)
        # This query finds all DialecticalComponents with no polarity relationships
        # (orphaned components that aren't part of any WisdomUnit)
        delete_orphaned_stmt_query = """
        MATCH (stmt_comp:DialecticalComponent)
        WHERE NOT exists((stmt_comp)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(:WisdomUnit))
        AND NOT exists((stmt_comp)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-())
        DETACH DELETE stmt_comp
        """
        graph_db.execute(delete_orphaned_stmt_query)

        # Finally, delete the WU and all its subgraph (including Transformation and Transitions)
        delete_subgraph_query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(rationale)
        OPTIONAL MATCH (component)<-[:EXPLAINS]-(component_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:BELONGS_TO_CYCLE]-(transition:Transition)
        WITH wu,
             collect(DISTINCT component) AS components,
             collect(DISTINCT rationale) + collect(DISTINCT component_rationale) AS rationales,
             collect(DISTINCT transformation) AS transformations,
             collect(DISTINCT transition) AS transitions
        FOREACH (comp IN components | DETACH DELETE comp)
        FOREACH (rat IN rationales | DETACH DELETE rat)
        FOREACH (trans IN transitions | DETACH DELETE trans)
        FOREACH (transformation IN transformations | DETACH DELETE transformation)
        DETACH DELETE wu
        """
        graph_db.execute(delete_subgraph_query, {"wu_id": wisdom_unit._id})

        return True

    @inject
    def _has_incoming_references(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """Check if WU has incoming references from outside its subgraph.

        Excludes internal structural relationships:
        - Polarity relationships (T, T_PLUS, etc.) from components
        - EXPLAINS from rationales
        - IS_SPIRAL_OF from transformations
        """
        if wisdom_unit._id is None:
            return False

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id
        OPTIONAL MATCH (external)-[r]->(wu)
        WHERE external IS NOT NULL
          AND type(r) <> 'T'
          AND type(r) <> 'T_PLUS'
          AND type(r) <> 'T_MINUS'
          AND type(r) <> 'A'
          AND type(r) <> 'A_PLUS'
          AND type(r) <> 'A_MINUS'
          AND type(r) <> 'S_PLUS'
          AND type(r) <> 'S_MINUS'
          AND type(r) <> 'EXPLAINS'
          AND type(r) <> 'IS_SPIRAL_OF'
        RETURN count(r) > 0 AS has_refs
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        return result[0]["has_refs"] if result else False

    @inject
    def _components_have_external_refs(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """Check if WU's components have refs from/to outside subgraph.

        Checks both:
        - Incoming refs to components (external->component)
        - Outgoing refs from components (component->external) for polarity relationships
        """
        if wisdom_unit._id is None:
            return False

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Find subgraph nodes
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(rationale)
        OPTIONAL MATCH (component)<-[:EXPLAINS]-(component_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:BELONGS_TO_CYCLE]-(transition:Transition)

        WITH wu,
             [wu] + collect(DISTINCT component) + collect(DISTINCT rationale) +
             collect(DISTINCT component_rationale) + collect(DISTINCT transformation) +
             collect(DISTINCT transition) AS all_subgraph_nodes,
             collect(DISTINCT component) AS components

        // Check for external refs (both incoming and outgoing)
        UNWIND components AS comp

        // Check incoming refs (excluding transition rels and EXPLAINS/HAS_STATEMENT)
        OPTIONAL MATCH (external_in)-[r_in]->(comp)
        WHERE external_in IS NOT NULL
          AND NOT external_in IN all_subgraph_nodes
          AND type(r_in) <> 'EXPLAINS'
          AND type(r_in) <> 'HAS_STATEMENT'
          AND type(r_in) <> 'IS_SOURCE_OF'
          AND type(r_in) <> 'IS_TARGET_OF'

        // Check outgoing polarity refs (component shared across multiple WUs)
        OPTIONAL MATCH (comp)-[r_out]->(external_out)
        WHERE external_out IS NOT NULL
          AND NOT external_out IN all_subgraph_nodes
          AND (type(r_out) = 'T' OR type(r_out) = 'T_PLUS' OR type(r_out) = 'T_MINUS'
               OR type(r_out) = 'A' OR type(r_out) = 'A_PLUS' OR type(r_out) = 'A_MINUS'
               OR type(r_out) = 'S_PLUS' OR type(r_out) = 'S_MINUS')

        RETURN count(r_in) + count(r_out) > 0 AS has_refs
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        return result[0]["has_refs"] if result else False

    @inject
    def _rationales_explain_external(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """Check if WU's rationales explain anything outside the subgraph."""
        if wisdom_unit._id is None:
            return False

        query = """
        MATCH (wu:WisdomUnit) WHERE id(wu) = $wu_id

        // Find subgraph nodes
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(component)
        OPTIONAL MATCH (wu)<-[:EXPLAINS]-(rationale)
        OPTIONAL MATCH (component)<-[:EXPLAINS]-(component_rationale)
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(transformation:Transformation)
        OPTIONAL MATCH (transformation)<-[:BELONGS_TO_CYCLE]-(transition:Transition)

        WITH wu,
             [wu] + collect(DISTINCT component) + collect(DISTINCT rationale) +
             collect(DISTINCT component_rationale) + collect(DISTINCT transformation) +
             collect(DISTINCT transition) AS all_subgraph_nodes,
             collect(DISTINCT rationale) + collect(DISTINCT component_rationale) AS rationales

        // Check if any rationale explains something outside
        WITH all_subgraph_nodes,
             CASE WHEN size(rationales) > 0 THEN rationales ELSE [null] END AS rationales_safe
        UNWIND rationales_safe AS rat
        OPTIONAL MATCH (rat)-[:EXPLAINS]->(external)
        WHERE rat IS NOT NULL
          AND external IS NOT NULL
          AND NOT external IN all_subgraph_nodes
        RETURN count(external) > 0 AS has_refs
        """
        result = list(graph_db.execute_and_fetch(query, {"wu_id": wisdom_unit._id}))
        return result[0]["has_refs"] if result else False

    @inject
    def is_isolated(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if a WisdomUnit and its subgraph are isolated (not referenced externally).

        A WisdomUnit is isolated if:
        1. WU has no incoming relationships (disconnected from parent structures)
        2. Components have no incoming relationships except from WU and rationales
        3. Rationales don't EXPLAIN anything outside the WU subgraph

        Rationales and Estimations are treated as "attributes" - they belong to what
        they explain and are deleted together with their parent.

        CRITIQUES relationships are ignored (rationales critiquing each other are
        still attributes of the same subgraph).

        HAS_STATEMENT is treated as a boundary - components referenced this way
        live independently and are handled specially during deletion.

        Args:
            wisdom_unit: The WisdomUnit to check
            graph_db: Database connection (injected via DI)

        Returns:
            True if isolated (safe to delete), False if has external references

        Example:
            if repo.is_isolated(old_ac_re):
                repo.safe_delete(old_ac_re)
        """
        if wisdom_unit._id is None:
            return True  # Not saved = isolated by definition

        # Check each isolation criteria separately for easier debugging
        # Note: Don't pass graph_db explicitly - DI will inject it for each helper
        if self._has_incoming_references(wisdom_unit):
            return False

        if self._components_have_external_refs(wisdom_unit):
            return False

        if self._rationales_explain_external(wisdom_unit):
            return False

        return True
