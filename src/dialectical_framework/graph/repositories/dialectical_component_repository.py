"""
DialecticalComponentRepository for complex query operations.

This repository separates data access logic from the DialecticalComponent node model,
keeping the model clean and declarative while centralizing complex queries.

Key concepts:
- **Vocabulary**: The set of DialecticalComponents available in a given context (Input or Nexus)
- **Vocabulary Context**: The closest Input (Gen-0) or Nexus (Gen-1+) that bounds a node's vocabulary
- **Root Inputs**: All original Input sources that contributed to a component's existence
"""

from __future__ import annotations

from typing import Optional, Union, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.brainstorm import Brainstorm
    from dialectical_framework.graph.nodes.base_node import BaseNode
    from dialectical_framework.graph.nodes.rationale import Rationale


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

        # Two separate queries combined with UNION for Memgraph compatibility
        query = """
        // Core positions (T, T+, T-, A, A+, A-) directly on WU
        MATCH (c:DialecticalComponent)-[r]->(wu:WisdomUnit)
        WHERE id(wu) = $wisdom_unit_id
        AND type(r) IN ['T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS']
        RETURN c, r.alias AS alias

        UNION

        // Synthesis positions (S+, S-) via Synthesis node
        MATCH (c:DialecticalComponent)-[r]->(synth:Synthesis)-[:SYNTHESIS_OF]->(wu:WisdomUnit)
        WHERE id(wu) = $wisdom_unit_id
        AND type(r) IN ['S_PLUS', 'S_MINUS']
        RETURN c, r.alias AS alias
        """

        results = graph_db.execute_and_fetch(query, {"wisdom_unit_id": wisdom_unit._id})
        return [(result["c"], result["alias"]) for result in results]

    @inject
    def get_vocabulary(
        self,
        context: Union[Input, Nexus, Brainstorm],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> set[DialecticalComponent]:
        """
        Get all DialecticalComponents in the vocabulary of the given context.

        Vocabulary is bounded by context type:
        - **Input**: Components directly created via HAS_STATEMENT from this Input
        - **Brainstorm**: Gen-0 vocabulary - all components from HAS_INPUT Inputs plus
          derivative dx:// Inputs within the Brainstorm's scope
        - **Nexus**: Gen-1+ vocabulary - all components available for building WisdomUnits:
          - Input-born components from WUs in this Nexus (pulled into vocabulary)
          - Synthesis components (S+/S-) from WUs in this Nexus
          - Components from dx:// referenced Inputs (via DialexityInputResolver)
          - Inherited vocabulary from parent Nexuses (via origin_hash lineage from clone())

        The Nexus boundary prevents traversal into other Nexuses' territories.

        Args:
            context: Input, Brainstorm (Gen-0), or Nexus (Gen-1+)
            graph_db: Database connection (injected via DI)

        Returns:
            Set of DialecticalComponents available in this vocabulary context

        Example:
            repo = DialecticalComponentRepository()

            # Single Input vocabulary
            input_vocab = repo.get_vocabulary(input_node)

            # Gen-0: Components from a Brainstorm
            brainstorm_vocab = repo.get_vocabulary(brainstorm)

            # Gen-1+: Components available in a Nexus context
            nexus_vocab = repo.get_vocabulary(nexus)

            # Check if a component is in vocabulary
            if component in nexus_vocab:
                print("Component available for Gen-1 WisdomUnits")
        """
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.brainstorm import Brainstorm

        if context._id is None:
            return set()

        if isinstance(context, Input):
            return self._get_input_vocabulary(context, graph_db)

        elif isinstance(context, Brainstorm):
            return self._get_brainstorm_vocabulary(context, graph_db)

        elif isinstance(context, Nexus):
            # Get own vocabulary first
            vocabulary = self._get_nexus_own_vocabulary(context, graph_db)

            # Recursively inherit from parent Nexuses (via origin_hash lineage)
            visited: set[str] = {context.hash}
            self._collect_inherited_vocabulary(context, vocabulary, visited, graph_db)

            return vocabulary

        else:
            raise ValueError(f"Context must be Input, Brainstorm, or Nexus, got {type(context)}")

    def _get_input_vocabulary(
        self,
        input_node: Input,
        graph_db: Union[Memgraph, Neo4j]
    ) -> set[DialecticalComponent]:
        """
        Get vocabulary for a single Input (Gen-0 context).

        Includes:
        1. Components directly linked via HAS_STATEMENT
        2. Components from Ideas (via DISTILLED_TO → HAS_STATEMENT)

        For dx:// Inputs, validates that the reference traces back to
        a valid Gen-0 root (non-dx:// Input). If unresolvable, returns empty.

        Args:
            input_node: The Input to get vocabulary for
            graph_db: Database connection

        Returns:
            Set of DialecticalComponents in this Input's vocabulary
        """
        if input_node._id is None:
            return set()

        content = getattr(input_node, 'content', None)

        # If dx:// Input, validate it traces to Gen-0 root
        if content and content.startswith('dx://'):
            if not self._input_traces_to_gen0_root(input_node, graph_db, visited=set()):
                return set()  # Unresolvable dx:// - no vocabulary

        # Query both direct HAS_STATEMENT and via Ideas
        query = """
        MATCH (input:Input) WHERE id(input) = $input_id

        // 1. Direct HAS_STATEMENT components
        OPTIONAL MATCH (input)-[:HAS_STATEMENT]->(direct_comp:DialecticalComponent)

        // 2. Components via Ideas (Input → DISTILLED_TO → Ideas → HAS_STATEMENT)
        OPTIONAL MATCH (input)-[:DISTILLED_TO]->(ideas:Ideas)-[:HAS_STATEMENT]->(ideas_comp:DialecticalComponent)

        // Collect all components
        WITH collect(DISTINCT direct_comp) + collect(DISTINCT ideas_comp) AS all_comps
        UNWIND all_comps AS comp
        WITH comp WHERE comp IS NOT NULL
        RETURN DISTINCT comp
        """
        results = graph_db.execute_and_fetch(query, {"input_id": input_node._id})
        return {record["comp"] for record in results if record["comp"] is not None}

    def _get_brainstorm_vocabulary(
        self,
        brainstorm: Brainstorm,
        graph_db: Union[Memgraph, Neo4j]
    ) -> set[DialecticalComponent]:
        """
        Get vocabulary for a Brainstorm (Gen-0 context).

        Includes:
        1. Components from HAS_INPUT Inputs (direct and via Ideas)
        2. Components from dx:// HAS_INPUT Inputs that trace to valid Gen-0 roots
        3. Components from derivative dx:// Inputs (not HAS_INPUT connected) that
           reference Rationales/Components within this Brainstorm's scope

        Args:
            brainstorm: The Brainstorm to get vocabulary for
            graph_db: Database connection

        Returns:
            Set of DialecticalComponents in this Brainstorm's Gen-0 vocabulary
        """
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        if brainstorm._id is None:
            return set()

        components: set[DialecticalComponent] = set()

        # 1. Iterate through all HAS_INPUT Inputs
        for input_node, _ in brainstorm.inputs.all():
            content = getattr(input_node, 'content', None)

            # Check if this Input is dx:// and needs validation
            if content and content.startswith('dx://'):
                # Validate that dx:// traces back to a Gen-0 root
                if not self._input_traces_to_gen0_root(input_node, graph_db, visited=set()):
                    continue  # Skip - not a valid Gen-0 source

            # Include components from this Input
            for comp, _ in input_node.statements.all():
                components.add(comp)

            # Include components from Ideas
            for ideas, _ in input_node.ideas.all():
                for comp, _ in ideas.statements.all():
                    components.add(comp)

        # 2. Include derivative dx:// Input components (not connected via HAS_INPUT)
        derivative_comps = self._trace_brainstorm_dx_references(brainstorm, graph_db)
        components.update(derivative_comps)

        return components

    def _trace_brainstorm_dx_references(
        self,
        brainstorm: Brainstorm,
        graph_db: Union[Memgraph, Neo4j]
    ) -> set[DialecticalComponent]:
        """
        Find derivative dx:// Input components within a Brainstorm's scope.

        Derivative Inputs are NOT connected via HAS_INPUT but reference content
        (Rationales, Components) that belongs to this Brainstorm's scope via dx:// URIs.

        Args:
            brainstorm: The Brainstorm to trace dx:// references for
            graph_db: Database connection

        Returns:
            Set of DialecticalComponents from derivative dx:// Inputs
        """
        if brainstorm._id is None:
            return set()

        # Get the Brainstorm's sid for scope validation
        brainstorm_sid = brainstorm.sid
        if not brainstorm_sid:
            return set()

        # Query to find derivative dx:// Input components
        query = """
        MATCH (brainstorm:Brainstorm) WHERE id(brainstorm) = $brainstorm_id

        // Collect Components from HAS_INPUT Inputs (and their Ideas)
        OPTIONAL MATCH (brainstorm)-[:HAS_INPUT]->(input:Input)-[:HAS_STATEMENT]->(comp:DialecticalComponent)
        OPTIONAL MATCH (brainstorm)-[:HAS_INPUT]->(input2:Input)-[:DISTILLED_TO]->(ideas:Ideas)-[:HAS_STATEMENT]->(ideas_comp:DialecticalComponent)

        // Collect Rationales that EXPLAIN these Components
        OPTIONAL MATCH (comp)<-[:EXPLAINS]-(rat1:Rationale)
        OPTIONAL MATCH (ideas_comp)<-[:EXPLAINS]-(rat2:Rationale)

        // Collect all target hashes (Components + Rationales)
        WITH brainstorm,
             collect(DISTINCT comp.hash) + collect(DISTINCT ideas_comp.hash) +
             collect(DISTINCT rat1.hash) + collect(DISTINCT rat2.hash) AS target_hashes

        // Filter out nulls
        WITH brainstorm, [h IN target_hashes WHERE h IS NOT NULL] AS valid_hashes

        // Find Inputs with dx:// content referencing any target hash (same sid)
        UNWIND valid_hashes AS target_hash
        MATCH (input:Input)
        WHERE input.content STARTS WITH ('dx://' + brainstorm.sid + '/')
        AND input.content CONTAINS target_hash
        // Exclude Inputs already connected via HAS_INPUT
        AND NOT (brainstorm)-[:HAS_INPUT]->(input)

        // Get HAS_STATEMENT components from matching derivative Inputs
        MATCH (input)-[:HAS_STATEMENT]->(derived:DialecticalComponent)
        RETURN DISTINCT derived AS comp
        """

        results = list(graph_db.execute_and_fetch(query, {"brainstorm_id": brainstorm._id}))
        return {record["comp"] for record in results if record["comp"] is not None}

    def _input_traces_to_gen0_root(
        self,
        input_node: Input,
        graph_db: Union[Memgraph, Neo4j],
        visited: set[str]
    ) -> bool:
        """
        Check if a dx:// Input traces back to a valid Gen-0 root.

        Recursively follows dx:// references until we find:
        - A non-dx:// Input → Valid Gen-0 root (return True)
        - Unresolvable reference → Invalid (return False)
        - Circular reference → Invalid (return False)

        Args:
            input_node: The Input to trace
            graph_db: Database connection
            visited: Set of already-visited hashes (cycle detection)

        Returns:
            True if traces back to valid Gen-0 root, False otherwise
        """
        from dialectical_framework.graph.dialexity_input_resolver import DialexityInputResolver
        from dialectical_framework.graph.repositories.node_repository import NodeRepository
        from dialectical_framework.graph.nodes.rationale import Rationale
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        content = getattr(input_node, 'content', None)
        if not content:
            return False

        # Non-dx:// Input is a valid Gen-0 root
        if not content.startswith('dx://'):
            return True

        # Cycle detection
        input_hash = getattr(input_node, 'hash', None) or str(input_node._id)
        if input_hash in visited:
            return False  # Circular reference
        visited.add(input_hash)

        try:
            resolver = DialexityInputResolver()
            hash_repo = NodeRepository()

            # Parse dx:// URI
            sid, branch, hash_or_prefix = resolver.parse_uri(content)

            # Look up the referenced node
            node = hash_repo.find_by_hash(hash_or_prefix)
            if node is None:
                try:
                    node = hash_repo.find_by_prefix(
                        hash_or_prefix,
                        min_length=resolver.MIN_HASH_PREFIX_LENGTH,
                    )
                except ValueError:
                    return False  # Ambiguous or not found

            if node is None:
                return False  # Unresolvable

            # Validate sid matches
            if node.sid != sid:
                return False  # Scope mismatch

            # Trace based on node type
            if isinstance(node, Rationale):
                return self._trace_rationale_to_gen0_input(node, graph_db, visited)
            elif isinstance(node, DialecticalComponent):
                return self._trace_component_to_gen0_input(node, graph_db, visited)
            else:
                return False  # Unsupported node type

        except Exception:
            return False  # Parse error or other failure

    def _trace_rationale_to_gen0_input(
        self,
        rationale: Rationale,
        graph_db: Union[Memgraph, Neo4j],
        visited: set[str]
    ) -> bool:
        """Trace a Rationale to see if it leads to a Gen-0 root Input."""
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
        from dialectical_framework.graph.nodes.transformation import Transformation

        explanation_result = rationale.explanation.get()
        if not explanation_result:
            return False

        explained_node, _ = explanation_result

        if isinstance(explained_node, DialecticalComponent):
            return self._trace_component_to_gen0_input(explained_node, graph_db, visited)

        if isinstance(explained_node, WisdomUnit):
            t_result = explained_node.t.get()
            if t_result:
                comp, _ = t_result
                return self._trace_component_to_gen0_input(comp, graph_db, visited)

        if isinstance(explained_node, Transformation):
            wu_result = explained_node.wisdom_unit.get()
            if wu_result:
                wu, _ = wu_result
                t_result = wu.t.get()
                if t_result:
                    comp, _ = t_result
                    return self._trace_component_to_gen0_input(comp, graph_db, visited)

        return False

    def _trace_component_to_gen0_input(
        self,
        component: DialecticalComponent,
        graph_db: Union[Memgraph, Neo4j],
        visited: set[str]
    ) -> bool:
        """Trace a Component to see if its birth Input is a Gen-0 root."""
        if component._id is None:
            return False

        # Find the Input that has this Component via HAS_STATEMENT
        # Path 1: Direct Input -> Component
        # Path 2: Input -> Ideas -> Component
        query = """
        MATCH (comp:DialecticalComponent) WHERE id(comp) = $comp_id

        // Path 1: Direct Input -> Component
        OPTIONAL MATCH (comp)<-[:HAS_STATEMENT]-(direct_input:Input)

        // Path 2: Ideas -> Component, then Ideas <- Input
        OPTIONAL MATCH (comp)<-[:HAS_STATEMENT]-(ideas:Ideas)<-[:DISTILLED_TO]-(ideas_input:Input)

        WITH coalesce(direct_input, ideas_input) AS input
        WHERE input IS NOT NULL
        RETURN input
        LIMIT 1
        """
        results = list(graph_db.execute_and_fetch(query, {"comp_id": component._id}))

        if not results:
            return False  # No Input found (might be synthesis component)

        birth_input = results[0]["input"]
        return self._input_traces_to_gen0_root(birth_input, graph_db, visited)

    def _get_nexus_own_vocabulary(
        self,
        nexus: Nexus,
        graph_db: Union[Memgraph, Neo4j]
    ) -> set[DialecticalComponent]:
        """
        Get vocabulary directly belonging to a single Nexus (no inheritance).

        This is the base vocabulary from WUs, Syntheses, Cycles, Wheels, and Rationales
        that are directly connected to this Nexus.
        """
        from dialectical_framework.graph.nodes.nexus import Nexus

        if nexus._id is None:
            return set()

        # Note: We explicitly list structural relationship types to avoid traversing
        # semantic relationships (OPPOSITE_OF, POSITIVE_SIDE_OF, NEGATIVE_SIDE_OF, SIMILAR_TO)
        # which can create exponential path explosion between components.
        query = """
        MATCH (nexus:Nexus) WHERE id(nexus) = $nexus_id

        // 1. WU position components (Input-born, included in Nexus vocabulary)
        OPTIONAL MATCH (nexus)<-[:BELONGS_TO_NEXUS]-(wu:WisdomUnit)
        OPTIONAL MATCH (wu)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(pos_comp:DialecticalComponent)

        // 2. Synthesis components (S+/S-) via Transformation
        OPTIONAL MATCH (wu)<-[:IS_SPIRAL_OF]-(trans:Transformation)<-[:SYNTHESIS_OF]-(synth:Synthesis)
        OPTIONAL MATCH (synth)<-[:S_PLUS|S_MINUS]-(synth_comp:DialecticalComponent)

        // Collect all components
        WITH collect(DISTINCT pos_comp) + collect(DISTINCT synth_comp) AS all_comps
        UNWIND all_comps AS comp
        WITH comp
        WHERE comp IS NOT NULL
        RETURN DISTINCT comp
        """

        results = graph_db.execute_and_fetch(query, {"nexus_id": nexus._id})
        vocabulary = {record["comp"] for record in results if record["comp"] is not None}

        # Add dx:// referenced Input components
        vocabulary.update(self._trace_dx_references_in_vocabulary(nexus, graph_db))

        return vocabulary

    def _trace_dx_references_in_vocabulary(
        self,
        nexus: Nexus,
        graph_db: Union[Memgraph, Neo4j]
    ) -> set[DialecticalComponent]:
        """
        Trace dx:// references in Input nodes connected to Nexus.

        If an Input's content is a dx:// URI pointing to a Rationale or Component
        that's part of this Nexus, include that Input's HAS_STATEMENT components
        in the vocabulary.

        Uses a pure Cypher approach:
        1. Collect all hashes of valid dx:// targets in the Nexus (Rationales, Components)
        2. Find Inputs whose dx:// content CONTAINS any of those hashes
        3. Return the Input's HAS_STATEMENT components

        Args:
            nexus: The Nexus to trace dx:// references for
            graph_db: Database connection

        Returns:
            Set of DialecticalComponents from dx:// referenced Inputs
        """
        if nexus._id is None:
            return set()

        # Get the Nexus sid for scope validation
        nexus_sid = nexus.sid
        if not nexus_sid:
            # No sid = no scope, skip dx:// tracing
            return set()

        # Single Cypher query that:
        # 1. Collects hashes of valid dx:// targets in the Nexus
        # 2. Finds Inputs with dx:// content containing those hashes (same sid)
        # 3. Returns HAS_STATEMENT components from those Inputs
        #
        # Valid dx:// targets are:
        # - Rationales that EXPLAIN WUs in this Nexus
        # - Rationales that EXPLAIN Components in WUs in this Nexus
        # - Rationales that EXPLAIN Transformations in this Nexus
        # - Components that are positions in WUs in this Nexus
        query = """
        MATCH (nexus:Nexus) WHERE id(nexus) = $nexus_id

        // Collect valid target hashes from the Nexus
        // Path 1: Rationales that EXPLAIN WUs in this Nexus
        OPTIONAL MATCH (nexus)<-[:BELONGS_TO_NEXUS]-(wu:WisdomUnit)<-[:EXPLAINS]-(rat1:Rationale)

        // Path 2: Rationales that EXPLAIN Components in WUs in this Nexus
        OPTIONAL MATCH (nexus)<-[:BELONGS_TO_NEXUS]-(wu2:WisdomUnit)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(pos_comp:DialecticalComponent)<-[:EXPLAINS]-(rat2:Rationale)

        // Path 3: Rationales that EXPLAIN Transformations in this Nexus
        OPTIONAL MATCH (nexus)<-[:BELONGS_TO_NEXUS]-(wu3:WisdomUnit)<-[:IS_SPIRAL_OF]-(trans:Transformation)<-[:EXPLAINS]-(rat3:Rationale)

        // Path 4: Components that are positions in WUs in this Nexus
        OPTIONAL MATCH (nexus)<-[:BELONGS_TO_NEXUS]-(wu4:WisdomUnit)<-[:T|T_PLUS|T_MINUS|A|A_PLUS|A_MINUS]-(comp:DialecticalComponent)

        // Collect all target hashes
        WITH nexus,
             collect(DISTINCT rat1.hash) + collect(DISTINCT rat2.hash) +
             collect(DISTINCT rat3.hash) + collect(DISTINCT comp.hash) AS target_hashes

        // Filter out nulls and flatten
        WITH nexus, [h IN target_hashes WHERE h IS NOT NULL] AS valid_hashes

        // Find Inputs with dx:// content containing any target hash
        // The URI must start with dx://<nexus_sid>/ to ensure scope match
        UNWIND valid_hashes AS target_hash
        MATCH (input:Input)
        WHERE input.content STARTS WITH ('dx://' + nexus.sid + '/')
        AND input.content CONTAINS target_hash

        // Get HAS_STATEMENT components from matching Inputs
        MATCH (input)-[:HAS_STATEMENT]->(derived:DialecticalComponent)
        RETURN DISTINCT derived AS comp
        """

        results = graph_db.execute_and_fetch(query, {"nexus_id": nexus._id})
        return {record["comp"] for record in results if record["comp"] is not None}

    def _collect_inherited_vocabulary(
        self,
        nexus: Nexus,
        vocabulary: set[DialecticalComponent],
        visited: set[str],
        graph_db: Union[Memgraph, Neo4j]
    ) -> None:
        """
        Recursively collect vocabulary from parent Nexuses.

        A Nexus inherits vocabulary from its parent (via origin_hash lineage).
        This method traverses the ancestry chain and collects all inherited components.

        Args:
            nexus: Current Nexus to check for parents
            vocabulary: Set to add inherited components to (modified in place)
            visited: Set of already-visited Nexus identities (prevents cycles)
            graph_db: Database connection
        """
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.repositories.node_repository import NodeRepository

        # Check for parent Nexus via origin_hash (lineage tracking)
        if nexus.origin_hash:
            hash_repo = NodeRepository()
            parent = hash_repo.find_by_hash(nexus.origin_hash)
            if parent and isinstance(parent, Nexus) and parent.hash not in visited:
                visited.add(parent.hash)
                parent_vocab = self._get_nexus_own_vocabulary(parent, graph_db)
                vocabulary.update(parent_vocab)
                self._collect_inherited_vocabulary(parent, vocabulary, visited, graph_db)

    @inject
    def get_vocabulary_contexts(
        self,
        node: BaseNode,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> list[Union[Input, Nexus]]:
        """
        Find all vocabulary contexts (Input or Nexus) for any node.

        A component can belong to multiple vocabulary contexts when:
        - Multiple Inputs extracted the same statement (content-addressable)
        - Multiple Ideas extracted the same statement
        - Component is used in multiple Nexuses

        Context resolution by node type:
        - **Input**: Returns [itself] (Input is a vocabulary context)
        - **Nexus**: Returns [itself] (Nexus is a vocabulary context)
        - **DialecticalComponent**: Returns all Inputs/Ideas sources + all Nexuses it's in
        - **WisdomUnit**: Returns all Nexuses it belongs to
        - **Cycle**: Returns all Nexuses it belongs to
        - **Wheel**: Returns Nexuses via its Cycle
        - **Transition**: Returns Nexuses via its Cycle/Transformation
        - **Rationale**: Returns contexts of what it explains
        - **Synthesis**: Returns Nexuses of its WisdomUnit

        Args:
            node: Any BaseNode to find vocabulary contexts for
            graph_db: Database connection (injected via DI)

        Returns:
            List of Input/Nexus contexts (empty list if none found)

        Example:
            repo = DialecticalComponentRepository()

            # Find all contexts for a component
            contexts = repo.get_vocabulary_contexts(component)
            for ctx in contexts:
                if isinstance(ctx, Input):
                    print(f"Gen-0 context: {ctx.content}")
                elif isinstance(ctx, Nexus):
                    print(f"Gen-1+ context: {ctx.hash}")

            # Check membership
            if repo.is_in_vocabulary(component, target_input):
                print("Component belongs to this vocabulary")
        """
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.nodes.nexus import Nexus

        # Input and Nexus are vocabulary contexts themselves (no DB query needed)
        if isinstance(node, Input):
            return [node]
        if isinstance(node, Nexus):
            return [node]

        if node._id is None:
            return []

        # Query to find all Inputs and Nexuses
        query = """
        MATCH (n) WHERE id(n) = $node_id

        // Collect all Input sources (component can have multiple HAS_STATEMENT)
        OPTIONAL MATCH (n)<-[:HAS_STATEMENT]-(input:Input)
        WITH n, collect(DISTINCT input) AS inputs

        // Collect all Ideas sources
        OPTIONAL MATCH (n)<-[:HAS_STATEMENT]-(ideas:Ideas)<-[:DISTILLED_TO]-(ideas_input:Input)
        WITH n, inputs, collect(DISTINCT ideas_input) AS ideas_inputs

        // Collect Nexus via various paths
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

        // Path 6: Synthesis -> Transformation -> WU -> Nexus
        OPTIONAL MATCH (n)-[:SYNTHESIS_OF]->(trans:Transformation)-[:IS_SPIRAL_OF]->(wu2:WisdomUnit)-[:BELONGS_TO_NEXUS]->(nexus6:Nexus)

        // Path 7: Rationale -> explained entity -> ... -> Nexus (bounded traversal)
        OPTIONAL MATCH (n)-[:EXPLAINS]->(explained)
        OPTIONAL MATCH (explained)-[*0..5]-(nexus7:Nexus)
        WHERE nexus7:Nexus

        // Return all contexts
        WITH inputs, ideas_inputs,
             [x IN [nexus1, nexus2, nexus3, nexus4, nexus5, nexus6, nexus7] WHERE x IS NOT NULL] AS nexuses
        RETURN inputs, ideas_inputs, nexuses
        """

        results = list(graph_db.execute_and_fetch(query, {"node_id": node._id}))

        if not results:
            return []

        result = results[0]
        contexts: list[Union[Input, Nexus]] = []

        def get_node_id(n) -> Optional[int]:
            """Get node ID from either ORM object or raw mgclient.Node."""
            if hasattr(n, '_id'):
                return n._id
            elif hasattr(n, 'id'):
                return n.id
            return None

        seen_ids: set[int] = set()

        # Collect all Nexuses first (they take priority in Gen-1+ mode)
        nexuses = result.get("nexuses", []) or []
        for nexus in nexuses:
            if nexus:
                nid = get_node_id(nexus)
                if nid and nid not in seen_ids:
                    seen_ids.add(nid)
                    # Load as proper Nexus object
                    loaded = Nexus(_id=nid).load(graph_db)
                    contexts.append(loaded)

        # If no Nexuses, include Inputs (Gen-0 mode)
        if not contexts:
            inputs = result.get("inputs", []) or []
            ideas_inputs = result.get("ideas_inputs", []) or []
            for inp in inputs:
                if inp:
                    nid = get_node_id(inp)
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        # Load as proper Input object
                        loaded = Input(_id=nid).load(graph_db)
                        contexts.append(loaded)
            for inp in ideas_inputs:
                if inp:
                    nid = get_node_id(inp)
                    if nid and nid not in seen_ids:
                        seen_ids.add(nid)
                        # Load as proper Input object
                        loaded = Input(_id=nid).load(graph_db)
                        contexts.append(loaded)

        return contexts

    @inject
    def is_in_vocabulary(
        self,
        component: DialecticalComponent,
        context: Union[Input, Nexus],
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> bool:
        """
        Check if a component belongs to a specific vocabulary context.

        This is the primary method for vocabulary validation. A component
        belongs to a vocabulary if:
        - It was extracted from that Input (via HAS_STATEMENT)
        - It was extracted from Ideas belonging to that Input
        - It's part of a Nexus vocabulary (position components or synthesis)
        - It has no vocabulary context (derived component - allowed anywhere)

        Args:
            component: The DialecticalComponent to check
            context: The vocabulary context (Input or Nexus) to check against
            graph_db: Database connection (injected via DI)

        Returns:
            True if component belongs to the vocabulary, False otherwise

        Example:
            repo = DialecticalComponentRepository()

            # Check if component can be used in a WisdomUnit's vocabulary
            if repo.is_in_vocabulary(new_component, target_input):
                wu.t.connect(new_component)  # OK
            else:
                raise ValueError("Component not in vocabulary")
        """
        from dialectical_framework.graph.nodes.input import Input
        from dialectical_framework.graph.nodes.nexus import Nexus

        # Get all contexts for this component
        contexts = self.get_vocabulary_contexts(component)

        # Derived components (no context) are allowed anywhere
        if not contexts:
            return True

        # Check if the target context is among the component's contexts
        context_hash = context.hash if context.hash else str(context._id)
        for ctx in contexts:
            ctx_hash = ctx.hash if ctx.hash else str(ctx._id)
            if ctx_hash == context_hash:
                return True

        # For Nexus context, also check if component is in the vocabulary set
        if isinstance(context, Nexus):
            vocabulary = self.get_vocabulary(context)
            vocabulary_hashes = {c.hash for c in vocabulary}
            if component.hash in vocabulary_hashes:
                return True

        return False

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

        For a Gen-0 component, returns its single Input.
        For a Gen-1+ component, returns all Inputs from the Nexus that produced it.
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
                print(f"  - {input_node.content}")
        """
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

        return {record["input"] for record in results if record["input"] is not None}

