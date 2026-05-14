"""
Base node class for all graph entities in the dialectical framework.

This module provides the foundational node class that all other graph nodes inherit from.
Uses content-hash (Merkle) identity: nodes are identified by the hash of their content.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional, Union, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j, Node
from gqlalchemy.models import NodeMetaclass

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin

# Re-export ImmutableNodeError for backward compatibility
from dialectical_framework.exceptions.node_errors import ImmutableNodeError

from dialectical_framework.graph.mixins.persistable_mixin import PersistableMixin


class MixinAwareNodeMeta(NodeMetaclass):
    """
    Metaclass that extends GQLAlchemy's NodeMetaclass to collect fields from PersistableMixin classes.

    This solves the problem where GQLAlchemy only sees fields from the Node inheritance chain,
    missing fields defined in mixins.
    """

    def __new__(mcs, name: str, bases: tuple, namespace: dict, **kwargs):
        # Collect field annotations from PersistableMixin bases
        mixin_annotations = {}
        mixin_defaults = {}

        for base in bases:
            if isinstance(base, type) and issubclass(base, PersistableMixin) and base is not PersistableMixin:
                # Get annotations from this mixin
                if hasattr(base, '__annotations__'):
                    for field_name, field_type in base.__annotations__.items():
                        if field_name not in namespace.get('__annotations__', {}):
                            mixin_annotations[field_name] = field_type
                            # Get default value if exists
                            if hasattr(base, field_name):
                                mixin_defaults[field_name] = getattr(base, field_name)

        # Inject mixin fields into namespace before GQLAlchemy processes it
        if mixin_annotations:
            if '__annotations__' not in namespace:
                namespace['__annotations__'] = {}
            for field_name, field_type in mixin_annotations.items():
                if field_name not in namespace['__annotations__']:
                    # Use str type directly to avoid ForwardRef issues
                    namespace['__annotations__'][field_name] = str if 'str' in str(field_type) else field_type
                    if field_name in mixin_defaults:
                        namespace[field_name] = mixin_defaults[field_name]
                    else:
                        namespace[field_name] = None

        return super().__new__(mcs, name, bases, namespace, **kwargs)


class BaseNode(Node, label="Node", metaclass=MixinAwareNodeMeta):
    """
    Base class for all nodes in the dialectical graph.

    Uses Merkle (content-hash) identity:
    - hash: Primary identity, sha256 of content

    Workflow:
    1. Create node in memory, build relationships
    2. Call commit() to compute hash AND persist to database

    Attributes:
        hash: Primary identity - sha256 of structure + intent + committed_at
        sid: Scope ID - the UUID of the root Case.
        committed_at: Unix timestamp (seconds since epoch) when node was committed.
                      Part of hash for structural nodes to ensure temporal ordering.
    """

    hash: Optional[str] = None
    committed_at: Optional[float] = None  # Set at commit time, included in hash for structural nodes

    # metadata
    sid: Optional[str] = None

    def __init__(self, **data: Any) -> None:
        """
        Initialize a node.

        Auto-population:
        - sid: If not provided, reads from scope contextvar (set by app layer).
               If no scope set, remains None.

        Args:
            **data: Field values for the node
        """
        # Auto-populate sid from context if not provided
        # Reads directly from contextvar (set by app layer)
        if "sid" not in data or data["sid"] is None:
            from dialectical_framework.graph.scope_context import get_current_sid
            data["sid"] = get_current_sid()

        super().__init__(**data)

    @property
    def is_committed(self) -> bool:
        """Check if this node has been committed (has hash)."""
        return self.hash is not None

    @property
    def short_hash(self) -> Optional[str]:
        """Get the first 7 characters of the hash, or None if not committed."""
        return self.hash[:7] if self.hash else None

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect the parts that make up this node's structure hash.

        This method should be overridden in subclasses to return the node's
        structural content parts (e.g., statement text, connected component hashes).

        Returns:
            List of strings to be joined for hash computation

        Raises:
            NotImplementedError: If not overridden in subclass
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _collect_structure_hash_parts()"
        )

    def compute_hash(self) -> str:
        """
        Compute the full content hash for this node.

        Content hash = sha256(structure_parts + intent + committed_at)

        This combines:
        - structure_parts: The node's structural content (from _collect_structure_hash_parts)
        - intent: If node has IntentMixin
        - committed_at: Unix timestamp (ensures temporal ordering for structural nodes)

        Returns:
            sha256 hex string

        Raises:
            ValueError: If committed_at is not set (must be set before computing hash)
        """
        if self.committed_at is None:
            raise ValueError(
                "committed_at must be set before computing hash. "
                "This should be done automatically by save() or commit()."
            )

        # Collect structure parts from subclass
        parts = self._collect_structure_hash_parts()

        # Add intent if present (from IntentMixin)
        if isinstance(self, IntentMixin) and self.intent:
            parts.append(self.intent)

        # Add committed_at timestamp (ensures temporal ordering)
        parts.append(str(self.committed_at))

        combined = "\n".join(parts)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    @inject
    def save(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Self:
        """
        Persist this node to the database.

        Behavior depends on commit state:
        - Before commit: Persists as HEAD state (hash=None, mutable)
        - After commit: Persists metadata changes only (hash unchanged)

        For content-addressable nodes (same hash = same identity), if a node
        with the same hash already exists, reuses the existing node instead
        of creating a duplicate.

        For initial persistence with hash computation, use commit() instead.

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If structural fields have been modified after commit

        Note:
            After commit, only metadata fields should be modified before calling save().
            Metadata fields are marked with '# metadata' comments in node classes.
        """
        # Verify hash integrity for committed nodes
        if self.is_committed:
            current_hash = self.compute_hash()
            if current_hash != self.hash:
                raise ImmutableNodeError(
                    f"Cannot save committed node: structural fields have been modified. "
                    f"Expected hash {self.hash[:7]}..., got {current_hash[:7]}... "
                    f"Create a new node instead of modifying committed nodes."
                )

        # Dedup check: if hash is set but no _id, check for existing node
        # This handles content-addressable nodes (Rationale, Estimation) where
        # same content should resolve to same node (unique constraint on hash)
        if self.hash and self._id is None:
            from dialectical_framework.graph.repositories.node_repository import NodeRepository
            existing = NodeRepository().find_by_hash(self.hash)
            if existing is not None:
                self._id = existing._id
                return self

        result = graph_db.save_node(self)
        # GQLAlchemy returns a new node object with _id set - capture it
        if result is not None and result._id is not None:
            self._id = result._id
        return self

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Self:
        """
        Commit this node: compute hash and persist to database.

        Like git commit - computes identity hash and writes to object store.
        After commit, the node's structure is immutable.

        For content-addressable nodes (Rationale, Estimation) where committed_at
        is not part of the hash, committing the same content twice will reuse
        the existing node (deduplication).

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
        """
        if self.is_committed:
            raise ImmutableNodeError(
                f"Node already committed with hash {self.hash[:7]}..."
            )

        # Set committed_at BEFORE computing hash (it's part of the hash for structural nodes)
        self.committed_at = time.time()
        self.hash = self.compute_hash()

        # Dedup check: for content-addressable nodes (Rationale, Estimation),
        # the same content produces the same hash. Reuse existing if found.
        from dialectical_framework.graph.repositories.node_repository import NodeRepository
        existing = NodeRepository().find_by_hash(self.hash)
        if existing is not None:
            self._id = existing._id
            return self

        self.save()
        return self

    def clone(self, destination_sid: Optional[str] = None) -> Self:
        """
        Clone this node, creating a new uncommitted copy.

        Clone semantics:
        - hash = None (uncommitted, must call commit())
        - sid = destination_sid if provided, otherwise inherited

        Args:
            destination_sid: Optional scope ID for the clone

        Returns:
            New uncommitted node instance

        Raises:
            ValueError: If source node has not been committed
        """
        if not self.is_committed:
            raise ValueError("Cannot clone uncommitted node. Call commit() first.")

        data: dict[str, Any] = {}
        excluded_fields = {'hash', '_id', 'committed_at'}

        for field_name in self.__fields__:
            if field_name not in excluded_fields:
                data[field_name] = getattr(self, field_name)

        if destination_sid is not None:
            data['sid'] = destination_sid

        return self.__class__(**data)

    def __repr__(self) -> str:
        """String representation of the node."""
        if self.is_committed:
            return f"{self.__class__.__name__}({self.hash[:7]})"
        return f"{self.__class__.__name__}(uncommitted)"

    def __hash__(self) -> int:
        """Hash for use in sets and dict keys. Uses id() for uncommitted nodes."""
        if self.is_committed:
            return hash(self.hash)
        return id(self)

    def __eq__(self, other: object) -> bool:
        """Equality based on hash for committed nodes, identity for uncommitted."""
        if not isinstance(other, BaseNode):
            return NotImplemented
        if self.is_committed and other.is_committed:
            return self.hash == other.hash
        # Uncommitted nodes use object identity
        return self is other
