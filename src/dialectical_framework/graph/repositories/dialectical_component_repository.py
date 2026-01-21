"""
DialecticalComponentRepository for complex query operations.

This repository separates data access logic from the DialecticalComponent node model,
keeping the model clean and declarative while centralizing complex queries.

Key concepts:
- **Vocabulary**: The set of DialecticalComponents available in a given context (Input or Nexus)
- **Vocabulary Context**: The closest Input (Gen-1) or Nexus (Gen-2+) that bounds a node's vocabulary
- **Root Inputs**: All original Input sources that contributed to a component's existence
"""

from __future__ import annotations

from typing import Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.base_node import BaseNode


class DialecticalComponentRepository:
    """
    Repository for DialecticalComponent query operations.

    This class handles complex queries and traversals for DialecticalComponent nodes,
    separating data access logic from domain models following the Repository pattern.

    Example usage:
        from dialectical_framework.graph.repositories.dialectical_component_repository import DialecticalComponentRepository

        wu = WisdomUnit()
        wu.save()

        repo = DialecticalComponentRepository()
        components = repo.find_by_wisdom_unit(wu)
        for comp, alias in components:
            print(f"Component {comp.statement} has alias {alias}")
    """

    @inject
    def find_by_wisdom_unit(
        self,
        wisdom_unit: WisdomUnit,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[tuple[DialecticalComponent, str]]:
        """
        Find all DialecticalComponents belonging to a WisdomUnit with their aliases.

        Args:
            wisdom_unit: The WisdomUnit to query for
            graph_db: Database connection (injected via DI)

        Returns:
            List of tuples: (DialecticalComponent, alias)
            Example: [(comp1, "T"), (comp2, "T+"), (comp3, "A-")]
        """
        if wisdom_unit._id is None:
            return []

        query = """
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(wu) = $wisdom_unit_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS', 'S_PLUS', 'S_MINUS']
        RETURN c, r.alias as alias
        """

        results = graph_db.execute_and_fetch(query, {"wisdom_unit_id": wisdom_unit._id})
        return [(result["c"], result["alias"]) for result in results]

    @inject
    def get_vocabulary(
        self,
        context: Union[Input, Nexus],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> set[DialecticalComponent]:
        """
        Get all DialecticalComponents in the vocabulary of the given context.

        Vocabulary is bounded by context type:
        - **Input**: Components directly created via HAS_STATEMENT from this Input
        - **Nexus**: All components available for building WisdomUnits in this analytical context:
          - Input-born components from WUs in this Nexus (pulled into vocabulary)
          - Synthesis components (S+/S-) from WUs in this Nexus
          - HAS_STATEMENT components from anywhere in the Nexus tree (Transitions, Rationales, etc.)

        The Nexus boundary prevents traversal into other Nexuses' territories.

        Args:
            context: Either an Input (Gen-1 vocabulary) or Nexus (Gen-2+ vocabulary)
            graph_db: Database connection (injected via DI)

        Returns:
            Set of DialecticalComponents available in this vocabulary context

        Example:
            repo = DialecticalComponentRepository()

            # Gen-1: Components from an Input
            input_vocab = repo.get_vocabulary(input_node)

            # Gen-2+: Components available in a Nexus context
            nexus_vocab = repo.get_vocabulary(nexus)

            # Check if a component is in vocabulary
            if component in nexus_vocab:
                print("Component available for Gen-2 WisdomUnits")
        """
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        if context._id is None:
            return set()

        if isinstance(context, Input):
            query = """
            MATCH (input:Input)-[:HAS_STATEMENT]->(comp:DialecticalComponent)
            WHERE id(input) = $context_id
            RETURN DISTINCT comp
            """
        elif isinstance(context, Nexus):
            query = """
            MATCH (nexus:Nexus) WHERE id(nexus) = $context_id

            // 1. WU position components (Input-born, included in Nexus vocabulary)
            OPTIONAL MATCH (nexus)<-[:BELONGS_TO_NEXUS]-(wu:WisdomUnit)
            OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(pos_comp:DialecticalComponent)

            // 2. Synthesis components (S+/S-)
            OPTIONAL MATCH (wu)<-[:SYNTHESIS_OF]-(synth:Synthesis)
            OPTIONAL MATCH (synth)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

            // 3. HAS_STATEMENT from anywhere in the Nexus tree (bounded traversal)
            // Traverse from Nexus through any path, stop at Nexus boundaries
            OPTIONAL MATCH path = (nexus)-[*1..10]-(entity)
            WHERE NONE(n IN nodes(path)[1..] WHERE n:Nexus)
            OPTIONAL MATCH (entity)-[:HAS_STATEMENT]->(hs_comp:DialecticalComponent)

            // Collect all components
            WITH collect(DISTINCT pos_comp) + collect(DISTINCT synth_comp) + collect(DISTINCT hs_comp) AS all_comps
            UNWIND all_comps AS comp
            WHERE comp IS NOT NULL
            RETURN DISTINCT comp
            """
        else:
            raise ValueError(f"Context must be Input or Nexus, got {type(context)}")

        results = graph_db.execute_and_fetch(query, {"context_id": context._id})

        components: set[DialecticalComponent] = set()
        for record in results:
            comp_node = record["comp"]
            # GQLAlchemy returns node objects directly
            if isinstance(comp_node, DialecticalComponent):
                components.add(comp_node)
            elif hasattr(comp_node, "_properties"):
                # Reconstruct from raw node data if needed
                comp = DialecticalComponent(**comp_node._properties)
                comp._id = comp_node._id
                components.add(comp)

        return components

    @inject
    def get_vocabulary_context(
        self,
        node: BaseNode,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Union[Input, Nexus, None]:
        """
        Find the closest vocabulary context (Input or Nexus) for any node.

        This determines which vocabulary a node belongs to:
        - **Input**: Returns itself (Input is a vocabulary context)
        - **Nexus**: Returns itself (Nexus is a vocabulary context)
        - **DialecticalComponent**: Returns Input if Input-born, or Nexus if synthesis-born
        - **WisdomUnit**: Returns the Nexus it belongs to (first one if multiple)
        - **Cycle**: Returns the Nexus it belongs to
        - **Wheel**: Returns the Nexus via its Cycle
        - **Transition**: Returns the Nexus via its Cycle/Transformation
        - **Rationale**: Returns the context of what it explains
        - **Synthesis**: Returns the Nexus of its WisdomUnit

        Args:
            node: Any BaseNode to find the vocabulary context for
            graph_db: Database connection (injected via DI)

        Returns:
            Input (for Gen-1), Nexus (for Gen-2+), or None if not determinable

        Example:
            repo = DialecticalComponentRepository()

            # Find context for a component
            context = repo.get_vocabulary_context(component)
            if isinstance(context, Input):
                print("Gen-1 component from Input")
            elif isinstance(context, Nexus):
                print("Gen-2+ component from Nexus analysis")

            # Find context for a wheel
            context = repo.get_vocabulary_context(wheel)
            # Returns the Nexus the wheel belongs to
        """
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.nodes.nexus import Nexus

        if node._id is None:
            return None

        # Input and Nexus are vocabulary contexts themselves
        if isinstance(node, Input):
            return node
        if isinstance(node, Nexus):
            return node

        # Query to find closest Input or Nexus
        query = """
        MATCH (n) WHERE id(n) = $node_id

        // Try to find Input (for Input-born components)
        OPTIONAL MATCH (n)<-[:HAS_STATEMENT]-(input:Input)

        // Try to find Nexus via various paths
        // Path 1: Component -> WU -> Nexus
        OPTIONAL MATCH (n)-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]->(wu:WisdomUnit)-[:BELONGS_TO_NEXUS]->(nexus1:Nexus)

        // Path 2: WU -> Nexus directly
        OPTIONAL MATCH (n)-[:BELONGS_TO_NEXUS]->(nexus2:Nexus)

        // Path 3: Cycle -> Nexus
        OPTIONAL MATCH (n)<-[:HAS_CYCLE]-(nexus3:Nexus)

        // Path 4: Wheel -> Cycle -> Nexus
        OPTIONAL MATCH (n)-[:HAS_WHEEL]->(cycle:Cycle)<-[:HAS_CYCLE]-(nexus4:Nexus)

        // Path 5: Transition -> Cycle -> Nexus
        OPTIONAL MATCH (n)-[:BELONGS_TO_CYCLE]->(cycle2)-[:HAS_CYCLE|IS_SPIRAL_OF*1..2]-(nexus5:Nexus)

        // Path 6: Synthesis -> WU -> Nexus
        OPTIONAL MATCH (n)-[:SYNTHESIS_OF]->(wu2:WisdomUnit)-[:BELONGS_TO_NEXUS]->(nexus6:Nexus)

        // Path 7: Rationale -> explained entity -> ... -> Nexus (bounded traversal)
        OPTIONAL MATCH (n)-[:EXPLAINS]->(explained)
        OPTIONAL MATCH path = (explained)-[*0..5]-(nexus7:Nexus)
        WHERE nexus7:Nexus

        // Path 8: Component born from Transition/Rationale -> trace to Nexus
        OPTIONAL MATCH (n)<-[:HAS_STATEMENT]-(source)
        WHERE NOT source:Input
        OPTIONAL MATCH path2 = (source)-[*1..6]-(nexus8:Nexus)
        WHERE nexus8:Nexus AND NONE(intermediate IN nodes(path2)[1..-1] WHERE intermediate:Nexus)

        // Return first match: Input takes priority (Gen-1), then Nexus (Gen-2+)
        WITH input,
             coalesce(nexus1, nexus2, nexus3, nexus4, nexus5, nexus6, nexus7, nexus8) AS nexus
        RETURN input, nexus
        """

        results = list(graph_db.execute_and_fetch(query, {"node_id": node._id}))

        if not results:
            return None

        result = results[0]

        # Input-born takes priority (Gen-1)
        if result.get("input"):
            input_node = result["input"]
            if isinstance(input_node, Input):
                return input_node
            elif hasattr(input_node, "_properties"):
                inp = Input(**input_node._properties)
                inp._id = input_node._id
                return inp

        # Nexus (Gen-2+)
        if result.get("nexus"):
            nexus_node = result["nexus"]
            if isinstance(nexus_node, Nexus):
                return nexus_node
            elif hasattr(nexus_node, "_properties"):
                nex = Nexus(**nexus_node._properties)
                nex._id = nexus_node._id
                return nex

        return None

    @inject
    def get_root_inputs(
        self,
        node: BaseNode,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> set[Input]:
        """
        Get all original Input sources that contributed to this node.

        Recursively traverses through Nexuses to collect all root Inputs.
        This answers: "What primary sources contributed to this insight?"

        For a Gen-1 component, returns its single Input.
        For a Gen-2+ component, returns all Inputs from the Nexus that produced it.
        For a Wheel, returns all Inputs from all WUs in its Nexus hierarchy.

        Args:
            node: Any BaseNode to trace provenance for
            graph_db: Database connection (injected via DI)

        Returns:
            Set of Input nodes that are the ultimate sources

        Example:
            repo = DialecticalComponentRepository()

            # Trace a wheel's roots
            roots = repo.get_root_inputs(wheel)
            print(f"This wheel synthesizes {len(roots)} original sources:")
            for input_node in roots:
                print(f"  - {input_node.content_uri}")
        """
        from dialectical_framework.graph.nodes.input import Input

        if node._id is None:
            return set()

        # Query that recursively traverses through Nexuses to find all root Inputs
        query = """
        MATCH (n) WHERE id(n) = $node_id

        // Find all paths from this node to Input nodes
        // Traverse through: components, WUs, Nexuses, Cycles, Wheels, etc.
        // Stop at Input nodes (they are the roots)
        MATCH path = (n)-[*0..15]-(comp:DialecticalComponent)<-[:HAS_STATEMENT]-(input:Input)

        RETURN DISTINCT input
        """

        results = graph_db.execute_and_fetch(query, {"node_id": node._id})

        inputs = set()
        for record in results:
            input_node = record["input"]
            if isinstance(input_node, Input):
                inputs.add(input_node)
            elif hasattr(input_node, "_properties"):
                inp = Input(**input_node._properties)
                inp._id = input_node._id
                inputs.add(inp)

        return inputs

