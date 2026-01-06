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

from typing import Generic, Optional, Type, TypeVar, Union, overload

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j, Node
from gqlalchemy import Relationship as GQLRelationship

from dialectical_framework.enums.di import DI

T = TypeVar("T", bound=Node)

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
        # Handle Union types (tuple of classes)
        if isinstance(target_class, tuple):
            self.target_class_names = [
                tc if isinstance(tc, str) else tc.__name__ for tc in target_class
            ]
            self.target_class_name = "|".join(self.target_class_names)  # For Cypher
        else:
            self.target_class_name = (
                target_class if isinstance(target_class, str) else target_class.__name__
            )
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
        source_node: Node,
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

    @inject
    def connect(
        self,
        target_node: T,
        properties: Optional[dict] = None,
        relationship: Optional[GQLRelationship] = None,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
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
        """
        db = graph_db  # Use injected db

        # Helper function to get node ID
        def get_node_id(node):
            """Get node ID, querying by uid if _id not set."""
            if node._id is not None:
                return node._id

            # Query by uid to get _id
            uid = getattr(node, "uid", None)
            if uid is None:
                raise ValueError(f"Node must be saved before creating relationships (no uid found)")

            labels = ':'.join(node.__class__.__name__.split())  # Get node label
            query = f"MATCH (n:{labels} {{uid: $uid}}) RETURN id(n) as node_id"
            result = list(db.execute_and_fetch(query, {"uid": uid}))

            if not result:
                raise ValueError(f"Node with uid={uid} not found in database")

            node_id = result[0]["node_id"]
            # Cache the ID on the node for future use
            node._id = node_id
            return node_id

        # Get IDs for both nodes
        source_id = get_node_id(self.source_node)
        target_id = get_node_id(target_node)

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

        # Build query based on direction
        if self.direction == "outgoing":
            pattern = f"(source)-[r:{self.relationship_type}]->(target:{self.target_class_name})"
        elif self.direction == "incoming":
            pattern = f"(source)<-[r:{self.relationship_type}]-(target:{self.target_class_name})"
        else:  # any
            pattern = f"(source)-[r:{self.relationship_type}]-(target:{self.target_class_name})"

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

        if self.direction == "outgoing":
            pattern = f"(source)-[:{self.relationship_type}]->(:{self.target_class_name})"
        elif self.direction == "incoming":
            pattern = f"(source)<-[:{self.relationship_type}]-(:{self.target_class_name})"
        else:
            pattern = f"(source)-[:{self.relationship_type}]-(:{self.target_class_name})"

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
    cardinality: Optional[tuple[int, Optional[int]]] = None,
) -> RelationshipManager[T]:
    """
    Define a bidirectional relationship (similar to neomodel's Relationship).

    Args:
        target_class: Target node class (name, class, or tuple for Union types).
                     Examples: "Person", Person, ("Cycle", "Spiral")
        relationship_type: Cypher relationship type (optional if model is provided,
                          will be inferred from model.type)
        model: Optional relationship model class
        cardinality: (min, max) where max=None means unbounded

    Returns:
        RelationshipManager descriptor

    Note: Named 'RelationshipBoth' to avoid shadowing GQLAlchemy's Relationship class.
    """
    return RelationshipManager(
        target_class=target_class,
        relationship_type=relationship_type,
        relationship_model=model,
        direction="any",
        cardinality=cardinality,
    )
