"""
Declarative relationship management layer for GQLAlchemy.

This module provides neomodel-like declarative relationship syntax on top
of GQLAlchemy, making the code much cleaner and more maintainable.

Usage:
    class MyNode(Node):
        # Declarative relationship definition
        friends = RelationshipTo('Person', 'FRIENDS_WITH')

    # Clean API
    person1.friends.connect(person2, db=db)
    all_friends = person1.friends.all(db=db)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic, Optional, Type, TypeVar, Union, get_args

if TYPE_CHECKING:
    from gqlalchemy import Memgraph, Node
    from gqlalchemy import Relationship as GQLRelationship
else:
    # At runtime, import for actual use
    from gqlalchemy import Relationship as GQLRelationship

T = TypeVar("T", bound="Node")


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
        source_node: "Node",
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

    def connect(
        self,
        target_node: T,
        properties: Optional[dict] = None,
        db: Optional["Memgraph"] = None,
    ) -> GQLRelationship:
        """
        Create a relationship to the target node.

        Args:
            target_node: The target node to connect to
            properties: Optional properties for the relationship
            db: Database connection (uses get_db() if not provided)

        Returns:
            The created relationship

        Raises:
            ValueError: If nodes haven't been saved or cardinality constraint violated
        """
        if self.source_node._id is None:
            raise ValueError("Source node must be saved before creating relationships")
        if target_node._id is None:
            raise ValueError("Target node must be saved before creating relationships")

        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

        # Check max cardinality before adding
        if self.cardinality:
            min_card, max_card = self.cardinality
            current_count = self.count(db)

            if max_card is not None and current_count >= max_card:
                raise ValueError(
                    f"Cannot add relationship: maximum cardinality "
                    f"{max_card} already reached (current: {current_count})"
                )

        properties = properties or {}

        # Determine start and end based on direction
        if self.direction == "outgoing":
            start_id = self.source_node._id
            end_id = target_node._id
        elif self.direction == "incoming":
            start_id = target_node._id
            end_id = self.source_node._id
        else:  # any
            start_id = self.source_node._id
            end_id = target_node._id

        # Create relationship
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

    def disconnect(self, target_node: T, db: Optional["Memgraph"] = None) -> bool:
        """
        Remove relationship to the target node.

        Args:
            target_node: The target node to disconnect from
            db: Database connection (uses get_db() if not provided)

        Returns:
            True if relationship was removed, False if it didn't exist
        """
        if self.source_node._id is None or target_node._id is None:
            return False

        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

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

    def all(self, db: Optional["Memgraph"] = None) -> list[tuple[T, dict]]:
        """
        Get all connected nodes with their relationship properties.

        Args:
            db: Database connection (uses get_db() if not provided)

        Returns:
            List of tuples: (target_node, relationship_properties)
        """
        if self.source_node._id is None:
            return []

        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

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
        RETURN target, properties(r) as rel_props
        """

        results = db.execute_and_fetch(query, {"source_id": self.source_node._id})
        return [(result["target"], result["rel_props"]) for result in results]

    def get(
        self,
        target_node: Optional[T] = None,
        **filters
    ) -> Optional[tuple[T, dict]]:
        """
        Get a specific connected node.

        Args:
            target_node: Specific target node to find
            **filters: Property filters for the target node

        Returns:
            Tuple of (target_node, relationship_properties) or None
        """
        all_results = self.all()

        if target_node is not None:
            for node, props in all_results:
                if node._id == target_node._id:
                    return (node, props)
            return None

        if filters:
            for node, props in all_results:
                match = all(
                    getattr(node, key, None) == value
                    for key, value in filters.items()
                )
                if match:
                    return (node, props)
            return None

        # Return first if no filters
        return all_results[0] if all_results else None

    def count(self, db: Optional["Memgraph"] = None) -> int:
        """
        Count connected nodes.

        Args:
            db: Database connection (uses get_db() if not provided)

        Returns:
            Number of connected nodes
        """
        if self.source_node._id is None:
            return 0

        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

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

    def validate_cardinality(self, db: Optional["Memgraph"] = None) -> tuple[bool, Optional[str]]:
        """
        Check if current count satisfies cardinality constraint.

        Args:
            db: Database connection (uses get_db() if not provided)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not self.cardinality:
            return (True, None)

        min_card, max_card = self.cardinality
        current_count = self.count(db)

        if current_count < min_card:
            return (False, f"Requires at least {min_card}, found {current_count}")

        if max_card is not None and current_count > max_card:
            return (False, f"Maximum {max_card} allowed, found {current_count}")

        return (True, None)


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
