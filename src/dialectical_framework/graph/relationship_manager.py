"""
Declarative relationship management layer for GQLAlchemy.

This module provides neomodel-like declarative relationship syntax on top
of GQLAlchemy, making the code much cleaner and more maintainable.

Usage:
    class MyNode(Node):
        # Declarative relationship definition
        friends = RelationshipTo('Person', 'FRIENDS_WITH')

    # Clean API (uses dependency injection)
    person1.friends.connect(person2)
    all_friends = person1.friends.all()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Optional, Type, TypeVar, Union, overload

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j, Node
from gqlalchemy import Relationship as GQLRelationship

from dialectical_framework.enums.di import DI

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode

T = TypeVar("T", bound="BaseNode")

# Cache for inverse relationship lookup
# Key: (source_class_name, target_class_name, relationship_type)
# Value: (inverse_manager, attr_name) or None if no inverse exists
_inverse_cache: dict[tuple[str, str, str], tuple[RelationshipManager, str] | None] = {}


def _get_all_subclasses(cls: type) -> dict[str, type]:
    """Recursively collect all subclasses of a class."""
    result = {}
    for subclass in cls.__subclasses__():
        result[subclass.__name__] = subclass
        result.update(_get_all_subclasses(subclass))
    return result


def _get_node_class_by_name(name: str) -> type | None:
    """Resolve a node class by name by searching BaseNode subclasses."""
    from dialectical_framework.graph.nodes.base_node import BaseNode
    from gqlalchemy import Node

    # Special case for base types
    if name == "Node":
        return Node
    if name == "BaseNode":
        return BaseNode

    # Dynamically discover all node subclasses
    all_classes = _get_all_subclasses(BaseNode)
    return all_classes.get(name)


def _get_label_for_class_name(class_name: str) -> str:
    """
    Get the database label for a class name (resolves class and gets its label).

    Used to convert class names like 'DialecticalComponent' to their
    database labels like 'Component'.
    """
    node_class = _get_node_class_by_name(class_name)
    if node_class is not None:
        return getattr(node_class, 'label', class_name)
    return class_name  # Fallback to class name if not found


def _get_all_labels_for_class_name(class_name: str) -> list[str]:
    """
    Get database labels for a class AND all its subclasses.

    Handles polymorphic relationships where the target might be any subclass.
    For example, 'Estimation' returns ['Estimation', 'Probability', 'Relevance',
    'CalculatedProbability', 'CalculatedRelevance', 'Feasibility'].

    Args:
        class_name: The class name to resolve

    Returns:
        List of all applicable database labels
    """
    node_class = _get_node_class_by_name(class_name)
    if node_class is None:
        return [class_name]

    labels = []

    # Add the class's own label
    own_label = getattr(node_class, 'label', class_name)
    labels.append(own_label)

    # Add labels of all subclasses
    for subclass in _get_all_subclasses(node_class).values():
        subclass_label = getattr(subclass, 'label', subclass.__name__)
        if subclass_label not in labels:
            labels.append(subclass_label)

    return labels


def _is_class_compatible(source_class_name: str, target_class_names: list[str]) -> bool:
    """
    Check if source_class_name is compatible with any of the target_class_names.

    This handles inheritance - e.g., DialecticalComponent is compatible with
    AssessableEntity because it's a subclass.

    Args:
        source_class_name: The name of the class to check
        target_class_names: List of class names that are acceptable targets

    Returns:
        True if source_class_name matches exactly or is a subclass of any target
    """
    # Quick exact match check
    if source_class_name in target_class_names:
        return True

    source_class = _get_node_class_by_name(source_class_name)
    if source_class is None:
        return False

    for target_name in target_class_names:
        target_class = _get_node_class_by_name(target_name)
        if target_class is not None and issubclass(source_class, target_class):
            return True

    return False


def _find_inverse_manager(
    source_class_name: str,
    target_class: type,
    relationship_type: str,
    source_direction: str
) -> tuple[RelationshipManager, str] | None:
    """
    Find the inverse RelationshipManager on target_class.

    Args:
        source_class_name: Name of the source class
        target_class: The class to search for inverse
        relationship_type: The relationship type to match
        source_direction: Direction of the calling relationship

    Returns:
        Tuple of (inverse RelationshipManager, attribute name) or None if not found.
        None means no cardinality constraint on the target side (implicit 0, None).
    """
    target_class_name = target_class.__name__
    cache_key = (source_class_name, target_class_name, relationship_type)

    if cache_key in _inverse_cache:
        return _inverse_cache[cache_key]

    # Determine opposite direction
    if source_direction == "outgoing":
        opposite_direction = "incoming"
    elif source_direction == "incoming":
        opposite_direction = "outgoing"
    else:  # "any" - cannot determine inverse
        _inverse_cache[cache_key] = None
        return None

    # Search target class for inverse (include private _attrs)
    for attr_name in dir(target_class):
        attr = getattr(target_class, attr_name, None)
        if not isinstance(attr, RelationshipManager):
            continue

        if (attr.relationship_type == relationship_type and
            attr.direction == opposite_direction and
            _is_class_compatible(source_class_name, attr.target_class_names)):
            result = (attr, attr_name)
            _inverse_cache[cache_key] = result
            return result

    # No inverse found = no cardinality constraint on target side (implicit 0, None)
    _inverse_cache[cache_key] = None
    return None


class RelationshipManager(Generic[T]):
    """
    Manages relationships for a node, providing a clean API similar to neomodel.

    This is a descriptor that provides declarative relationship definitions
    on GQLAlchemy nodes.
    """

    def __init__(
        self,
        target_class: str | Type[T] | tuple[str | Type[T], ...],
        relationship_type: Optional[str] = None,
        relationship_model: Optional[Type[GQLRelationship]] = None,
        direction: str = "outgoing",  # 'outgoing', 'incoming', 'any'
        cardinality: Optional[tuple[int, Optional[int]]] = None,
    ):
        """
        Initialize relationship manager.

        Args:
            target_class: Target node class (name, class, or tuple of names/classes for Union)
            relationship_type: Cypher relationship type (e.g., 'FRIENDS_WITH').
                               Optional if relationship_model is provided (will be inferred).
                               Required if relationship_model is not provided.
            relationship_model: Optional relationship model class. If provided, its type
                               will be used if relationship_type is not explicitly specified.
            direction: 'outgoing', 'incoming', or 'any'
            cardinality: (min, max) where max=None means unbounded
                Examples:
                - (1, 1): Exactly one
                - (1, None): One or more
                - (0, 1): Zero or one
                - (0, None): Zero or more
        """
        def _get_label(tc):
            """Get the database label for a class (uses GQLAlchemy's label attribute)."""
            if isinstance(tc, str):
                return tc  # String - use as-is (will be resolved later)
            # For class objects, use the GQLAlchemy label attribute
            return getattr(tc, 'label', tc.__name__)

        # Handle Union types (tuple of classes)
        if isinstance(target_class, tuple):
            self.target_class_names = [_get_label(tc) for tc in target_class]
            self.target_class_name = "|".join(self.target_class_names)  # For Cypher
        else:
            self.target_class_name = _get_label(target_class)
            self.target_class_names = [self.target_class_name]

        self.target_class = target_class
        self.relationship_model = relationship_model
        self.direction = direction
        self.cardinality = cardinality
        self.source_node = None  # Set when accessed as descriptor

        # Determine relationship_type: infer from model if not provided
        if relationship_type is None:
            if relationship_model:
                # Infer type from model
                model_type = getattr(relationship_model, 'type', None)
                if model_type:
                    relationship_type = model_type
                else:
                    raise ValueError(
                        f"Cannot infer relationship type from {relationship_model.__name__}: "
                        f"model does not have a 'type' attribute. "
                        f"Please specify relationship_type explicitly."
                    )
            else:
                raise ValueError(
                    "relationship_type is required when relationship_model is not provided"
                )
        elif relationship_model:
            # Both provided: validate they match
            model_type = getattr(relationship_model, 'type', None)
            if model_type and model_type != relationship_type:
                raise ValueError(
                    f"Relationship type mismatch: parameter specifies '{relationship_type}' "
                    f"but {relationship_model.__name__} has type='{model_type}'. "
                    f"These must match to avoid query/creation mismatches. "
                    f"Either remove the '{relationship_type}' parameter (it will be inferred) "
                    f"or ensure it matches '{model_type}'."
                )

        self.relationship_type = relationship_type

    def __set_name__(self, owner, name):
        """Called when the descriptor is assigned to a class attribute."""
        self.name = name

    @overload
    def __get__(self, instance: None, owner: type) -> RelationshipManager[T]:
        ...

    @overload
    def __get__(self, instance: Node, owner: type) -> BoundRelationshipManager[T]:
        ...

    def __get__(self, instance, owner):
        """Return a bound relationship manager when accessed on an instance."""
        if instance is None:
            return self

        # Return a bound manager that knows its source node
        bound = BoundRelationshipManager(
            source_node=instance,
            target_class_name=self.target_class_name,
            relationship_type=self.relationship_type,
            relationship_model=self.relationship_model,
            direction=self.direction,
            cardinality=self.cardinality,
        )
        return bound


class BoundRelationshipManager(Generic[T]):
    """
    A relationship manager bound to a specific node instance.

    Provides methods like .connect(), .disconnect(), .all(), etc.
    """

    def __init__(
        self,
        source_node: BaseNode,
        target_class_name: str,
        relationship_type: str,
        relationship_model: Optional[Type[GQLRelationship]],
        direction: str,
        cardinality: Optional[tuple[int, Optional[int]]] = None,
    ):
        self.source_node = source_node
        self.target_class_name = target_class_name
        self.relationship_type = relationship_type
        self.relationship_model = relationship_model
        self.direction = direction
        self.cardinality = cardinality

    def _validate_scope_compatibility(self, target_node: BaseNode) -> None:
        """
        Validate that connected nodes belong to the same scope (Brainstorm).

        When connecting two nodes, validates that their sid values are compatible:
        - If either sid is None, allow (orphan/unsaved node can join any scope)
        - If both have sid and they match, allow
        - If both have sid and they differ, raise ValueError

        This prevents accidentally mixing nodes from different Brainstorm scopes
        into the same graph structure.

        Raises:
            ValueError: If nodes have different non-None sids
        """
        source_sid = self.source_node.sid
        target_sid = target_node.sid

        # Allow if either is None (orphan/unsaved node)
        if source_sid is None or target_sid is None:
            return

        # Allow if same scope
        if source_sid == target_sid:
            return

        # Different scopes - not allowed
        source_id = self.source_node.hash or self.source_node._id or '?'
        target_id = target_node.hash or target_node._id or '?'
        raise ValueError(
            f"Cannot connect nodes from different scopes. "
            f"Source node (id={source_id}) has sid={source_sid}, "
            f"target node (id={target_id}) has sid={target_sid}. "
            f"Nodes in the same graph must belong to the same scope (Brainstorm)."
        )

    def _validate_nexus_frozen_after_cycle(self, target_node: BaseNode) -> None:
        """
        Validate that WisdomUnits cannot be added to a Nexus that already has Cycles.

        Once a Nexus has been "crystallized" into one or more Cycles, its WisdomUnit
        membership is frozen. To add more WUs, clone the Nexus to create a new one
        (lineage tracked via origin_hash).

        This is called automatically by connect() for BELONGS_TO_NEXUS relationships.

        Raises:
            ValueError: If trying to add a WU to a Nexus that already has Cycles
        """
        from dialectical_framework.graph.nodes.nexus import Nexus
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit

        # Determine which is the Nexus (could be source or target depending on direction)
        # WU.nexus is RelationshipTo (outgoing from WU to Nexus)
        # Nexus.wisdom_units is RelationshipFrom (incoming to Nexus from WU)
        if self.relationship_type != "BELONGS_TO_NEXUS":
            return  # Not a Nexus-WU connection

        # Identify the Nexus in this connection
        nexus = None
        if isinstance(self.source_node, WisdomUnit) and isinstance(target_node, Nexus):
            # wu.nexus.connect(nexus) - target is the Nexus
            nexus = target_node
        elif isinstance(self.source_node, Nexus) and isinstance(target_node, WisdomUnit):
            # nexus.wisdom_units.connect(wu) - source is the Nexus
            nexus = self.source_node

        if nexus is None:
            return  # Not a WU-Nexus connection

        # Check if Nexus already has any Cycles
        cycle_count = nexus.cycles.count()
        if cycle_count > 0:
            raise ValueError(
                f"Cannot add WisdomUnit to Nexus: Nexus already has {cycle_count} Cycle(s). "
                f"Once a Nexus has Cycles, its WisdomUnit membership is frozen. "
                f"To evolve the Nexus, clone it to create a new Nexus with different WisdomUnits "
                f"(lineage tracked via origin_hash)."
            )

    def _validate_cycle_wheel_connection(self, target_node: BaseNode) -> None:
        """
        Validate Cycle <-> Wheel connections.

        When connecting a Cycle to a Wheel (or vice versa), validates that all
        WisdomUnits referenced by the cycle are already connected to the wheel.

        This is called automatically by connect() - works regardless of which
        side initiates the connection.
        """
        from dialectical_framework.graph.nodes.cycle import Cycle
        from dialectical_framework.graph.nodes.wheel import Wheel

        # Determine which is the Cycle and which is the Wheel
        if isinstance(self.source_node, Cycle) and isinstance(target_node, Wheel):
            cycle, wheel = self.source_node, target_node
        elif isinstance(self.source_node, Wheel) and isinstance(target_node, Cycle):
            wheel, cycle = self.source_node, target_node
        else:
            return  # Not a Cycle-Wheel connection, skip validation

        # In the new architecture:
        # - Wheel gets WUs via wheel → cycle → nexus → wisdom_units
        # - When connecting, we validate that wheel's transitions reference
        #   components from the cycle's nexus

        # Get WisdomUnits from cycle's nexus
        nexus = cycle.get_nexus()
        if not nexus:
            raise ValueError(
                "Cannot connect cycle to wheel: cycle has no Nexus. "
                "Connect the cycle to a Nexus first."
            )

        nexus_wu_ids = {wu.hash for wu, _ in nexus.wisdom_units.all()}
        if not nexus_wu_ids:
            raise ValueError(
                "Cannot connect cycle to wheel: cycle's Nexus has no WisdomUnits. "
                "Connect WisdomUnits to the Nexus first."
            )

        # Get wheel's transitions
        wheel_transitions = wheel.transitions
        if not wheel_transitions:
            raise ValueError(
                "Cannot connect cycle to wheel: wheel has no transitions. "
                "Connect transitions to the wheel first."
            )

        # Collect all unique components from wheel's transitions
        from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository
        components_by_id: dict[str, Node] = {}
        for transition in wheel_transitions:
            source_result = transition.source.get()
            if source_result:
                comp = source_result[0]
                components_by_id[comp.hash] = comp
            target_result = transition.target.get()
            if target_result:
                comp = target_result[0]
                components_by_id[comp.hash] = comp

        # For each component, verify it belongs to a WU that's in the cycle's Nexus
        repo = WisdomUnitRepository()
        for component in components_by_id.values():
            from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
            assert isinstance(component, DialecticalComponent)
            component_wus = repo.find_by_dialectical_component(component)

            if not component_wus:
                stmt = getattr(component, 'statement', str(component.hash))[:50]
                raise ValueError(
                    f"Cannot connect cycle: component '{stmt}...' "
                    f"(id={component.hash}) does not belong to any WisdomUnit."
                )

            # Check if at least one of the component's WUs is in the cycle's Nexus
            component_wu_ids = {wu.hash for wu, _ in component_wus}
            if not component_wu_ids.intersection(nexus_wu_ids):
                stmt = getattr(component, 'statement', str(component.hash))[:50]
                raise ValueError(
                    f"Cannot connect cycle: component '{stmt}...' "
                    f"(id={component.hash}) belongs to WisdomUnit(s) not in the cycle's Nexus. "
                    f"Connect the WisdomUnit to the Nexus first."
                )

    def _create_wisdom_unit_semantic_relationships(self, target_node: BaseNode) -> None:
        """
        Auto-create semantic relationships when connecting components to WisdomUnit positions.

        Creates:
        - OPPOSITE_OF: T ↔ A (dialectical opposition between thesis and antithesis)
        - CONTRADICTION_OF: T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity pairs)
        - POSITIVE_SIDE_OF: T+ → T, A+ → A
        - NEGATIVE_SIDE_OF: T- → T, A- → A

        This is called automatically by connect() after successfully connecting
        a DialecticalComponent to a WisdomUnit polarity position.
        """
        from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        # Only for WU -> Component polarity connections
        polarity_types = {'T', 'T_PLUS', 'T_MINUS', 'A', 'A_PLUS', 'A_MINUS'}

        if not (isinstance(self.source_node, WisdomUnit) and
                isinstance(target_node, DialecticalComponent) and
                self.relationship_type in polarity_types):
            return  # Not a WU-component polarity connection

        wu = self.source_node
        new_comp = target_node
        position = self.relationship_type

        # Helper to safely connect without duplicate edges
        def safe_connect_semantic(source_comp: DialecticalComponent,
                                   rel_manager_name: str,
                                   target_comp: DialecticalComponent) -> None:
            """Connect if not already connected. Uses internal connect for auto-created relationships."""
            manager = getattr(source_comp, rel_manager_name)
            # Check if already connected
            existing = manager.get(target_comp)
            if existing is None:
                # Use internal connect for auto-created relationships
                # (we know they're correct based on WU structure, skip expensive validation)
                manager._connect_internal(target_comp)

        # Create POSITIVE_SIDE_OF: T+ → T, A+ → A
        if position == 'T_PLUS':
            t_result = wu.t.get()
            if t_result:
                t_comp, _ = t_result
                safe_connect_semantic(new_comp, 'positive_side_of', t_comp)
        elif position == 'A_PLUS':
            a_result = wu.a.get()
            if a_result:
                a_comp, _ = a_result
                safe_connect_semantic(new_comp, 'positive_side_of', a_comp)

        # Create NEGATIVE_SIDE_OF: T- → T, A- → A
        elif position == 'T_MINUS':
            t_result = wu.t.get()
            if t_result:
                t_comp, _ = t_result
                safe_connect_semantic(new_comp, 'negative_side_of', t_comp)
        elif position == 'A_MINUS':
            a_result = wu.a.get()
            if a_result:
                a_comp, _ = a_result
                safe_connect_semantic(new_comp, 'negative_side_of', a_comp)

        # Create OPPOSITE_OF relationships (bidirectional)
        # T ↔ A (neutral opposites)
        elif position == 'T':
            a_result = wu.a.get()
            if a_result:
                a_comp, _ = a_result
                # Bidirectional: T→A and A→T
                safe_connect_semantic(new_comp, 'oppositions', a_comp)
                safe_connect_semantic(a_comp, 'oppositions', new_comp)
        elif position == 'A':
            t_result = wu.t.get()
            if t_result:
                t_comp, _ = t_result
                # Bidirectional: A→T and T→A
                safe_connect_semantic(new_comp, 'oppositions', t_comp)
                safe_connect_semantic(t_comp, 'oppositions', new_comp)

        # Cross-polarity contradictions: T+ ↔ A-, A+ ↔ T- (bidirectional)
        # These are mutually exclusive statements (CONTRADICTION_OF, not OPPOSITE_OF)
        if position == 'T_PLUS':
            a_minus_result = wu.a_minus.get()
            if a_minus_result:
                a_minus_comp, _ = a_minus_result
                # Bidirectional: T+→A- and A-→T+
                safe_connect_semantic(new_comp, 'contradictions', a_minus_comp)
                safe_connect_semantic(a_minus_comp, 'contradictions', new_comp)
        elif position == 'A_MINUS':
            t_plus_result = wu.t_plus.get()
            if t_plus_result:
                t_plus_comp, _ = t_plus_result
                # Bidirectional: A-→T+ and T+→A-
                safe_connect_semantic(new_comp, 'contradictions', t_plus_comp)
                safe_connect_semantic(t_plus_comp, 'contradictions', new_comp)
        elif position == 'A_PLUS':
            t_minus_result = wu.t_minus.get()
            if t_minus_result:
                t_minus_comp, _ = t_minus_result
                # Bidirectional: A+→T- and T-→A+
                safe_connect_semantic(new_comp, 'contradictions', t_minus_comp)
                safe_connect_semantic(t_minus_comp, 'contradictions', new_comp)
        elif position == 'T_MINUS':
            a_plus_result = wu.a_plus.get()
            if a_plus_result:
                a_plus_comp, _ = a_plus_result
                # Bidirectional: T-→A+ and A+→T-
                safe_connect_semantic(new_comp, 'contradictions', a_plus_comp)
                safe_connect_semantic(a_plus_comp, 'contradictions', new_comp)

        # Also create relationships when T or A is connected and positive/negative sides exist
        if position == 'T':
            # T+ → T (if T+ already exists)
            t_plus_result = wu.t_plus.get()
            if t_plus_result:
                t_plus_comp, _ = t_plus_result
                safe_connect_semantic(t_plus_comp, 'positive_side_of', new_comp)
            # T- → T (if T- already exists)
            t_minus_result = wu.t_minus.get()
            if t_minus_result:
                t_minus_comp, _ = t_minus_result
                safe_connect_semantic(t_minus_comp, 'negative_side_of', new_comp)
        elif position == 'A':
            # A+ → A (if A+ already exists)
            a_plus_result = wu.a_plus.get()
            if a_plus_result:
                a_plus_comp, _ = a_plus_result
                safe_connect_semantic(a_plus_comp, 'positive_side_of', new_comp)
            # A- → A (if A- already exists)
            a_minus_result = wu.a_minus.get()
            if a_minus_result:
                a_minus_comp, _ = a_minus_result
                safe_connect_semantic(a_minus_comp, 'negative_side_of', new_comp)

    def _validate_semantic_relationship_consistency(self, target_node: BaseNode) -> None:
        """
        Validate that manual semantic relationships don't contradict WisdomUnit structure.

        When manually creating semantic relationships between components,
        this validates that the relationship doesn't contradict how the
        components are positioned within shared WisdomUnits.

        For example:
        - If T+ and T are in the same WU, T+ should be POSITIVE_SIDE_OF T, not OPPOSITE_OF T
        - If T and A are in the same WU, they should be OPPOSITE_OF, not POSITIVE_SIDE_OF

        This is called automatically by connect() for semantic relationships
        (OPPOSITE_OF, CONTRADICTION_OF, POSITIVE_SIDE_OF, NEGATIVE_SIDE_OF, SIMILAR_TO).

        Raises:
            ValueError: If the relationship contradicts WisdomUnit structure
        """
        from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent

        # Only validate Component-to-Component semantic relationships
        semantic_types = {'OPPOSITE_OF', 'CONTRADICTION_OF', 'POSITIVE_SIDE_OF', 'NEGATIVE_SIDE_OF', 'SIMILAR_TO'}

        if not (isinstance(self.source_node, DialecticalComponent) and
                isinstance(target_node, DialecticalComponent) and
                self.relationship_type in semantic_types):
            return  # Not a semantic relationship between components

        source_comp = self.source_node
        target_comp = target_node
        rel_type = self.relationship_type

        # Find shared WisdomUnits
        from dialectical_framework.graph.repositories.wisdom_unit_repository import WisdomUnitRepository
        repo = WisdomUnitRepository()

        source_wus = {wu.hash: (wu, pos) for wu, pos in repo.find_by_dialectical_component(source_comp)}
        target_wus = {wu.hash: (wu, pos) for wu, pos in repo.find_by_dialectical_component(target_comp)}

        # Find common WisdomUnits
        common_wu_uids = set(source_wus.keys()) & set(target_wus.keys())

        if not common_wu_uids:
            return  # No shared WisdomUnits, no structural constraint

        # Check each shared WisdomUnit for contradictions
        for wu_uid in common_wu_uids:
            _, source_pos = source_wus[wu_uid]
            _, target_pos = target_wus[wu_uid]

            # Define expected relationships based on positions
            # POSITIVE_SIDE_OF: T+ → T, A+ → A
            positive_side_pairs = {('T_PLUS', 'T'), ('A_PLUS', 'A')}
            # NEGATIVE_SIDE_OF: T- → T, A- → A
            negative_side_pairs = {('T_MINUS', 'T'), ('A_MINUS', 'A')}
            # OPPOSITE_OF: T ↔ A (dialectical opposition between thesis and antithesis)
            opposite_pairs = {('T', 'A'), ('A', 'T')}
            # CONTRADICTION_OF: T+ ↔ A-, A+ ↔ T- (mutually exclusive cross-polarity pairs)
            contradiction_pairs = {
                ('T_PLUS', 'A_MINUS'), ('A_MINUS', 'T_PLUS'),
                ('A_PLUS', 'T_MINUS'), ('T_MINUS', 'A_PLUS'),
            }

            pos_pair = (source_pos, target_pos)

            if rel_type == 'POSITIVE_SIDE_OF':
                # Only valid for T+ → T or A+ → A
                if pos_pair in opposite_pairs:
                    raise ValueError(
                        f"Cannot create POSITIVE_SIDE_OF between components that are opposites "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have OPPOSITE_OF relationship, not POSITIVE_SIDE_OF."
                    )
                if pos_pair in contradiction_pairs:
                    raise ValueError(
                        f"Cannot create POSITIVE_SIDE_OF between components that are contradictions "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have CONTRADICTION_OF relationship, not POSITIVE_SIDE_OF."
                    )
                if pos_pair in negative_side_pairs:
                    raise ValueError(
                        f"Cannot create POSITIVE_SIDE_OF between components where source is "
                        f"a negative side ({source_pos}) in WisdomUnit. "
                        f"Use NEGATIVE_SIDE_OF instead."
                    )

            elif rel_type == 'NEGATIVE_SIDE_OF':
                # Only valid for T- → T or A- → A
                if pos_pair in opposite_pairs:
                    raise ValueError(
                        f"Cannot create NEGATIVE_SIDE_OF between components that are opposites "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have OPPOSITE_OF relationship, not NEGATIVE_SIDE_OF."
                    )
                if pos_pair in contradiction_pairs:
                    raise ValueError(
                        f"Cannot create NEGATIVE_SIDE_OF between components that are contradictions "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have CONTRADICTION_OF relationship, not NEGATIVE_SIDE_OF."
                    )
                if pos_pair in positive_side_pairs:
                    raise ValueError(
                        f"Cannot create NEGATIVE_SIDE_OF between components where source is "
                        f"a positive side ({source_pos}) in WisdomUnit. "
                        f"Use POSITIVE_SIDE_OF instead."
                    )

            elif rel_type == 'OPPOSITE_OF':
                # Only valid for T ↔ A
                if pos_pair in positive_side_pairs or pos_pair in negative_side_pairs:
                    raise ValueError(
                        f"Cannot create OPPOSITE_OF between components that are on the same side "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have POSITIVE_SIDE_OF or NEGATIVE_SIDE_OF relationship."
                    )
                if pos_pair in contradiction_pairs:
                    raise ValueError(
                        f"Cannot create OPPOSITE_OF between cross-polarity components "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have CONTRADICTION_OF relationship, not OPPOSITE_OF."
                    )

            elif rel_type == 'CONTRADICTION_OF':
                # Only valid for T+ ↔ A-, A+ ↔ T-
                if pos_pair in positive_side_pairs or pos_pair in negative_side_pairs:
                    raise ValueError(
                        f"Cannot create CONTRADICTION_OF between components that are on the same side "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have POSITIVE_SIDE_OF or NEGATIVE_SIDE_OF relationship."
                    )
                if pos_pair in opposite_pairs:
                    raise ValueError(
                        f"Cannot create CONTRADICTION_OF between T and A components "
                        f"in WisdomUnit. Source is at {source_pos}, target is at {target_pos}. "
                        f"These positions should have OPPOSITE_OF relationship, not CONTRADICTION_OF."
                    )

    def _validate_structural_immutability(self, target_node: BaseNode, operation: str = "connect") -> None:
        """
        Validate that structural layer relationships aren't modified after commit.

        Three types of structural relationships with different validation:

        1. IdentityRelationship (IS_SOURCE_OF, IS_TARGET_OF, Polarity):
           - Defines what a node IS (its identity)
           - Blocked if SOURCE is committed (would change source's hash)

        2. ContainerMembership (BELONGS_TO_NEXUS, BELONGS_TO_CYCLE):
           - Defines container composition (incoming edges: child→container)
           - Blocked if TARGET (container) is committed
           - Committed children CAN be added to uncommitted containers

        3. OutgoingContainerMembership (HAS_STATEMENT):
           - Defines container composition (outgoing edges: container→children)
           - Blocked if SOURCE (container) is committed
           - Only applies to IncrementalBuildMixin containers

        MutableAnalyticalStructure relationships are never blocked.

        Args:
            target_node: The target node of the relationship
            operation: "connect" or "disconnect" for error message

        Raises:
            ImmutableNodeError: If trying to modify structural relationship illegally
        """
        from dialectical_framework.graph.relationships.immutable_structure import (
            IdentityRelationship,
            ContainerMembership,
            OutgoingContainerMembership,
            ImmutableStructure,
        )
        from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
        from dialectical_framework.graph.nodes.base_node import ImmutableNodeError

        if self.relationship_model is None:
            return  # No model, no validation

        # IdentityRelationship: block if SOURCE is committed
        if issubclass(self.relationship_model, IdentityRelationship):
            owner = self.source_node
            if hasattr(owner, 'is_committed') and owner.is_committed:
                raise ImmutableNodeError(
                    f"Cannot {operation} identity relationship on committed "
                    f"{owner.__class__.__name__} (hash: {owner.hash[:7]}...). "
                    f"Create a new node if you need different identity."
                )
            return

        # ContainerMembership: block if TARGET (container) is committed
        if issubclass(self.relationship_model, ContainerMembership):
            if hasattr(target_node, 'is_committed') and target_node.is_committed:
                raise ImmutableNodeError(
                    f"Cannot {operation} membership relationship to committed "
                    f"{target_node.__class__.__name__} (hash: {target_node.hash[:7]}...). "
                    f"Create a new container if you need different composition."
                )
            return

        # OutgoingContainerMembership: block if SOURCE (container) is committed
        # Only applies to IncrementalBuildMixin containers (e.g., Ideas)
        if issubclass(self.relationship_model, OutgoingContainerMembership):
            owner = self.source_node
            if isinstance(owner, IncrementalBuildMixin):
                if hasattr(owner, 'is_committed') and owner.is_committed:
                    raise ImmutableNodeError(
                        f"Cannot {operation} membership relationship from committed "
                        f"{owner.__class__.__name__} (hash: {owner.hash[:7]}...). "
                        f"Create a new container if you need different composition."
                    )
            return

        # Other ImmutableStructure subclasses: default to blocking on source commit
        if issubclass(self.relationship_model, ImmutableStructure):
            owner = self.source_node
            if hasattr(owner, 'is_committed') and owner.is_committed:
                raise ImmutableNodeError(
                    f"Cannot {operation} structural relationship on committed "
                    f"{owner.__class__.__name__} (hash: {owner.hash[:7]}...). "
                    f"Create a new node if you need different structure."
                )

    def connect(
        self,
        target_node: T,
        properties: Optional[dict] = None,
        relationship: Optional[GQLRelationship] = None,
    ) -> GQLRelationship:
        """
        Create a relationship to the target node.

        Two calling patterns supported:

        1. Pass typed relationship instance (recommended - type-safe and validated):
            wu.t.connect(component, relationship=TRelationship(alias='T1'))

            Benefits:
            - Type-safe: IDE autocomplete for relationship properties
            - Validated: alias validation happens at creation
            - Refactor-safe: renaming .alias updates all usages

        2. Pass properties dict (legacy - for backward compatibility):
            wu.t.connect(component, properties={'alias': 'T1'})

            Drawbacks:
            - Hardcoded strings (not refactor-safe)
            - No validation until save
            - No IDE autocomplete

        Note: connect() automatically sets _start_node_id and _end_node_id based on
        the relationship direction, so you don't need to specify them.

        Uses dependency injection to get the database connection.
        Tests can override the graph_db provider to use TestMemgraph/TestNeo4j.

        Args:
            target_node: The target node to connect to
            properties: Optional properties dict (legacy pattern)
            relationship: Optional typed relationship instance (recommended)

        Returns:
            The created relationship

        Raises:
            ValueError: If nodes haven't been saved or cardinality constraint violated
            ImmutableNodeError: If modifying structural relationship on committed node
        """
        # Run all validations before connecting
        # 0. Backbone immutability (structural relationships can't change after commit)
        self._validate_structural_immutability(target_node, "connect")
        # 1. Scope compatibility (nodes must belong to same scope/Brainstorm)
        self._validate_scope_compatibility(target_node)
        # 2. Cycle <-> Wheel connections require WU validation
        self._validate_cycle_wheel_connection(target_node)
        # 4. Nexus membership is frozen once Cycles exist
        self._validate_nexus_frozen_after_cycle(target_node)
        # 5. Semantic relationship consistency (component-to-component)
        self._validate_semantic_relationship_consistency(target_node)

        # Delegate to internal connect (no validation)
        # noinspection PyArgumentList
        return self._connect_internal(target_node, properties, relationship)

    @inject
    def _connect_internal(
        self,
        target_node: T,
        properties: Optional[dict] = None,
        relationship: Optional[GQLRelationship] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> GQLRelationship:
        """
        Internal connect method that skips validation.

        Used by:
        - connect() after validation passes
        - Auto-creation of semantic relationships (where we know they're correct)

        Args:
            target_node: The target node to connect to
            properties: Optional properties dict
            relationship: Optional typed relationship instance

        Returns:
            The created relationship
        """
        db = graph_db

        # Helper function to get node ID
        def get_node_id(node):
            """Get node ID, querying by hash if _id not set."""
            if node._id is not None:
                return node._id

            # Query by hash to get _id
            hash = getattr(node, "hash", None)
            if hash is None:
                raise ValueError(f"Node must be committed and saved before creating relationships (no hash found)")

            labels = node._label  # Get node label(s) from GQLAlchemy
            query = f"MATCH (n:{labels} {{hash: $hash}}) RETURN id(n) as node_id"
            result = list(db.execute_and_fetch(query, {"hash": hash}))

            if not result:
                raise ValueError(f"Node with hash={hash[:7]}... not found in database")

            node_id = result[0]["node_id"]
            # Cache the ID on the node for future use
            node._id = node_id
            return node_id

        # Get IDs for both nodes
        source_id = get_node_id(self.source_node)
        target_id = get_node_id(target_node)

        # For symmetric relationships (direction="any"), check if already connected
        # in either direction. If so, return existing relationship (idempotent).
        if self.direction == "any":
            query = f"""
            MATCH (a)-[r:{self.relationship_type}]-(b)
            WHERE id(a) = $source_id AND id(b) = $target_id
            RETURN r as relationship
            LIMIT 1
            """
            result = list(db.execute_and_fetch(query, {
                "source_id": source_id,
                "target_id": target_id
            }))
            if result:
                # Already connected - return existing relationship
                return result[0]["relationship"]

        # Check max cardinality before adding
        if self.cardinality:
            min_card, max_card = self.cardinality
            # noinspection PyArgumentList
            current_count = self.count()  # No db parameter needed, uses DI

            if max_card is not None and current_count >= max_card:
                raise ValueError(
                    f"Cannot add relationship: maximum cardinality "
                    f"{max_card} already reached (current: {current_count})"
                )

        # Check inverse cardinality (target node's constraint)
        # If no inverse is defined, it means unbounded (0, None) - no constraint
        inverse_result = _find_inverse_manager(
            source_class_name=type(self.source_node).__name__,
            target_class=type(target_node),
            relationship_type=self.relationship_type,
            source_direction=self.direction
        )

        if inverse_result is not None:
            inverse_manager, inverse_attr_name = inverse_result

            if inverse_manager.cardinality is not None:
                inv_min, inv_max = inverse_manager.cardinality

                if inv_max is not None:
                    # Count from target's perspective
                    target_bound = BoundRelationshipManager(
                        source_node=target_node,
                        target_class_name=inverse_manager.target_class_name,
                        relationship_type=inverse_manager.relationship_type,
                        relationship_model=inverse_manager.relationship_model,
                        direction=inverse_manager.direction,
                        cardinality=inverse_manager.cardinality,
                    )
                    inv_count = target_bound.count()

                    if inv_count >= inv_max:
                        raise ValueError(
                            f"Cannot add relationship: target's cardinality "
                            f"constraint violated. {target_node.__class__.__name__} "
                            f"already has {inv_count} '{inverse_attr_name}' "
                            f"relationship(s), maximum is {inv_max}."
                        )

        # Determine start and end based on direction
        if self.direction == "outgoing":
            start_id = source_id
            end_id = target_id
        elif self.direction == "incoming":
            start_id = target_id
            end_id = source_id
        else:  # any
            start_id = source_id
            end_id = target_id

        # Two patterns: typed relationship instance or properties dict
        if relationship is not None:
            # Pattern 1: Typed relationship instance (recommended - type-safe)
            # Automatically set IDs based on connect() direction
            relationship._start_node_id = start_id
            relationship._end_node_id = end_id
            rel = relationship

        else:
            # Pattern 2: Legacy properties dict (for backward compatibility)
            properties = properties or {}
            if self.relationship_model:
                rel = self.relationship_model(
                    _start_node_id=start_id,
                    _end_node_id=end_id,
                    **properties
                )
            else:
                # Use generic Relationship (dynamically created)
                rel = type(
                    f"{self.relationship_type}_Rel",
                    (GQLRelationship,),
                    {"__module__": __name__},
                    type=self.relationship_type
                )(_start_node_id=start_id, _end_node_id=end_id, **properties)

        db.save_relationship(rel)

        # Auto-create semantic relationships when connecting components to WisdomUnit
        self._create_wisdom_unit_semantic_relationships(target_node)

        return rel

    @inject
    def disconnect(
        self,
        target_node: T,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> bool:
        """
        Remove relationship to the target node. It does NOT delete the target node.

        Uses dependency injection to get the database connection.

        Args:
            target_node: The target node to disconnect from

        Returns:
            True if relationship was removed, False if it didn't exist
        """
        db = graph_db  # Use injected db
        if self.source_node._id is None or target_node._id is None:
            return False

        # Block disconnection of structural relationships on committed nodes
        self._validate_structural_immutability(target_node, "disconnect")

        # Determine direction
        if self.direction == "outgoing":
            query = f"""
            MATCH (source)-[r:{self.relationship_type}]->(target)
            WHERE id(source) = $source_id AND id(target) = $target_id
            DELETE r
            RETURN count(r) as deleted
            """
        elif self.direction == "incoming":
            query = f"""
            MATCH (source)<-[r:{self.relationship_type}]-(target)
            WHERE id(source) = $source_id AND id(target) = $target_id
            DELETE r
            RETURN count(r) as deleted
            """
        else:  # any
            query = f"""
            MATCH (source)-[r:{self.relationship_type}]-(target)
            WHERE id(source) = $source_id AND id(target) = $target_id
            DELETE r
            RETURN count(r) as deleted
            """

        result = list(db.execute_and_fetch(
            query,
            {"source_id": self.source_node._id, "target_id": target_node._id}
        ))

        return result[0]["deleted"] > 0 if result else False

    @inject
    def update_properties(
        self,
        target_node: T,
        properties: dict,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> bool:
        """
        Update properties on an existing relationship without disconnect/reconnect.

        This is useful for changing relationship properties (like alias) without
        triggering vocabulary validation, since the relationship already exists.

        Args:
            target_node: The target node of the relationship
            properties: Dict of properties to update (e.g., {'alias': 'T1'})

        Returns:
            True if relationship was updated, False if it didn't exist
        """
        db = graph_db
        if self.source_node._id is None or target_node._id is None:
            return False

        # Build SET clause for properties
        set_clauses = ", ".join(f"r.{key} = ${key}" for key in properties.keys())
        if not set_clauses:
            return False

        # Determine direction
        if self.direction == "outgoing":
            query = f"""
            MATCH (source)-[r:{self.relationship_type}]->(target)
            WHERE id(source) = $source_id AND id(target) = $target_id
            SET {set_clauses}
            RETURN count(r) as updated
            """
        elif self.direction == "incoming":
            query = f"""
            MATCH (source)<-[r:{self.relationship_type}]-(target)
            WHERE id(source) = $source_id AND id(target) = $target_id
            SET {set_clauses}
            RETURN count(r) as updated
            """
        else:  # any
            query = f"""
            MATCH (source)-[r:{self.relationship_type}]-(target)
            WHERE id(source) = $source_id AND id(target) = $target_id
            SET {set_clauses}
            RETURN count(r) as updated
            """

        params = {"source_id": self.source_node._id, "target_id": target_node._id}
        params.update(properties)

        result = list(db.execute_and_fetch(query, params))
        return result[0]["updated"] > 0 if result else False

    @inject
    def all(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> list[tuple[T, GQLRelationship]]:
        """
        Get all connected nodes with their relationship objects.

        Uses dependency injection to get the database connection.

        Returns:
            List of tuples: (target_node, relationship)
            - target_node: The connected node (type T)
            - relationship: Typed GQLAlchemy Relationship object (e.g., TRelationship with .alias)
        """
        db = graph_db  # Use injected db
        if self.source_node._id is None:
            return []

        # Resolve class names to labels, including subclass labels for polymorphic queries
        # target_class_name may be pipe-separated for union types
        class_names = self.target_class_name.split("|")
        all_labels = []
        for cn in class_names:
            all_labels.extend(_get_all_labels_for_class_name(cn))
        # Deduplicate while preserving order
        resolved_labels = "|".join(dict.fromkeys(all_labels))

        # Build query based on direction
        if self.direction == "outgoing":
            pattern = f"(source)-[r:{self.relationship_type}]->(target:{resolved_labels})"
        elif self.direction == "incoming":
            pattern = f"(source)<-[r:{self.relationship_type}]-(target:{resolved_labels})"
        else:  # any
            pattern = f"(source)-[r:{self.relationship_type}]-(target:{resolved_labels})"

        query = f"""
        MATCH {pattern}
        WHERE id(source) = $source_id
        RETURN target, r as relationship
        """

        results = db.execute_and_fetch(query, {"source_id": self.source_node._id})
        return [(result["target"], result["relationship"]) for result in results]

    def get(
        self,
        target_node: Optional[T] = None,
        **filters
    ) -> Optional[tuple[T, GQLRelationship]]:
        """
        Get a specific connected node.

        Uses dependency injection to get the database connection.

        Args:
            target_node: Specific target node to find
            **filters: Property filters for the target node

        Returns:
            Tuple of (target_node, relationship) or None
            - target_node: The connected node (type T)
            - relationship: Typed GQLAlchemy Relationship object (e.g., TRelationship with .alias)
        """
        # noinspection PyArgumentList
        all_results = self.all()  # No db parameter needed, uses DI

        if target_node is not None:
            for node, rel in all_results:
                if node._id == target_node._id:
                    return (node, rel)
            return None

        if filters:
            for node, rel in all_results:
                match = all(
                    getattr(node, key, None) == value
                    for key, value in filters.items()
                )
                if match:
                    return (node, rel)
            return None

        # Return first if no filters
        return all_results[0] if all_results else None

    @inject
    def count(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> int:
        """
        Count connected nodes.

        Uses dependency injection to get the database connection.

        Returns:
            Number of connected nodes
        """
        db = graph_db  # Use injected db
        if self.source_node._id is None:
            return 0

        # Resolve class names to labels, including subclass labels for polymorphic queries
        class_names = self.target_class_name.split("|")
        all_labels = []
        for cn in class_names:
            all_labels.extend(_get_all_labels_for_class_name(cn))
        # Deduplicate while preserving order
        resolved_labels = "|".join(dict.fromkeys(all_labels))

        if self.direction == "outgoing":
            pattern = f"(source)-[:{self.relationship_type}]->(:{resolved_labels})"
        elif self.direction == "incoming":
            pattern = f"(source)<-[:{self.relationship_type}]-(:{resolved_labels})"
        else:
            pattern = f"(source)-[:{self.relationship_type}]-(:{resolved_labels})"

        query = f"""
        MATCH {pattern}
        WHERE id(source) = $source_id
        RETURN count(*) as cnt
        """

        result = list(db.execute_and_fetch(query, {"source_id": self.source_node._id}))
        return result[0]["cnt"] if result else 0

    def validate_cardinality(self) -> tuple[bool, Optional[str]]:
        """
        Check if current count satisfies cardinality constraint.

        Uses dependency injection to get the database connection.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.cardinality:
            return True, None

        min_card, max_card = self.cardinality
        # noinspection PyArgumentList
        current_count = self.count()  # No db parameter needed, uses DI

        if current_count < min_card:
            return False, f"Requires at least {min_card}, found {current_count}"

        if max_card is not None and current_count > max_card:
            return False, f"Maximum {max_card} allowed, found {current_count}"

        return True, None

    def is_cardinality_valid(self) -> bool:
        """
        Check if current count satisfies cardinality constraint.

        Returns:
            True if cardinality is satisfied, False otherwise
        """
        is_valid, _ = self.validate_cardinality()
        return is_valid


# Convenience functions for common patterns
def RelationshipTo(
    target_class: str | Type[T] | tuple[str | Type[T], ...],
    relationship_type: Optional[str] = None,
    model: Optional[Type[GQLRelationship]] = None,
    cardinality: Optional[tuple[int, Optional[int]]] = None,
) -> RelationshipManager[T]:
    """
    Define an outgoing relationship (similar to neomodel).

    Args:
        target_class: Target node class (name, class, or tuple for Union types).
                     Examples: "Person", Person, ("Cycle", "Spiral")
        relationship_type: Cypher relationship type (optional if model is provided,
                          will be inferred from model.type)
        model: Optional relationship model class
        cardinality: (min, max) where max=None means unbounded

    Returns:
        RelationshipManager descriptor
    """
    return RelationshipManager(
        target_class=target_class,
        relationship_type=relationship_type,
        relationship_model=model,
        direction="outgoing",
        cardinality=cardinality,
    )


def RelationshipFrom(
    target_class: str | Type[T] | tuple[str | Type[T], ...],
    relationship_type: Optional[str] = None,
    model: Optional[Type[GQLRelationship]] = None,
    cardinality: Optional[tuple[int, Optional[int]]] = None,
) -> RelationshipManager[T]:
    """
    Define an incoming relationship (similar to neomodel).

    Args:
        target_class: Target node class (name, class, or tuple for Union types).
                     Examples: "Person", Person, ("Cycle", "Spiral")
        relationship_type: Cypher relationship type (optional if model is provided,
                          will be inferred from model.type)
        model: Optional relationship model class
        cardinality: (min, max) where max=None means unbounded

    Returns:
        RelationshipManager descriptor
    """
    return RelationshipManager(
        target_class=target_class,
        relationship_type=relationship_type,
        relationship_model=model,
        direction="incoming",
        cardinality=cardinality,
    )


def RelationshipBoth(
    target_class: str | Type[T] | tuple[str | Type[T], ...],
    relationship_type: Optional[str] = None,
    model: Optional[Type[GQLRelationship]] = None,
) -> RelationshipManager[T]:
    """
    Define a bidirectional/symmetric relationship.

    This is for truly symmetric relationships like "friends" where if A is
    connected to B, then B is connected to A (same edge, either direction).

    Key behaviors:
    - connect() is idempotent: if already connected in either direction, no-op
    - all()/count() query edges in both directions
    - No cardinality support (doesn't make sense for symmetric relationships)

    For relationships needing cardinality, use RelationshipTo/RelationshipFrom pairs.

    Args:
        target_class: Target node class (name, class, or tuple for Union types).
                     Examples: "Person", Person, ("Cycle", "Spiral")
        relationship_type: Cypher relationship type (optional if model is provided,
                          will be inferred from model.type)
        model: Optional relationship model class

    Returns:
        RelationshipManager descriptor

    Note: Named 'RelationshipBoth' to avoid shadowing GQLAlchemy's Relationship class.
    """
    return RelationshipManager(
        target_class=target_class,
        relationship_type=relationship_type,
        relationship_model=model,
        direction="any",
        cardinality=None,  # Cardinality not supported for symmetric relationships
    )
