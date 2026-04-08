"""
Mixin for nodes that can be built incrementally before committing.

This mixin is for container nodes that need children added incrementally
before being finalized:
- Ideas: add DialecticalComponents (statements)
- Cycle, Wheel: add Transitions
- Transformation: add Transitions for each position

The pattern follows git's staging area concept:
- save() persists with hash=None (HEAD state, mutable)
- add children incrementally while in HEAD state
- commit() computes Merkle hash, making the node immutable
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Iterator, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
from dialectical_framework.graph.mixins.persistable_mixin import PersistableMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode


class IncrementalBuildMixin(PersistableMixin):
    """
    Mixin for nodes that support incremental building before commit.

    Used by: Ideas, Cycle, Wheel, Transformation

    Lifecycle:
        1. Create node: cycle = Cycle(intent="...")
        2. Save as HEAD: cycle.save()  # hash=None, committed_at=None, persisted
        3. Add children: cycle.set_wisdom_units([wu1, wu2])
        4. Commit: cycle.commit()  # committed_at set, hash computed, immutable

    After commit(), the node behaves like any other committed node.

    Subclasses should implement:
        - _get_committed_children(): Returns iterator of child nodes for hash computation
    """

    # These will be provided by the actual node class
    hash: str | None
    _id: Any
    committed_at: float | None

    def _get_commit_dependents(self) -> Iterator[BaseNode]:
        """
        Get all committed children for hash computation.

        Override in subclasses to return the appropriate children:
        - Cycle/Wheel: yields Transitions
        - Transformation: yields Transitions for each position

        Yields:
            Child nodes that should be included in hash computation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement _get_commit_dependents()"
        )

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> IncrementalBuildMixin:
        """
        Commit this node: compute Merkle hash and make immutable.

        This finalizes the node. After commit:
        - hash is computed from children
        - No more children can be added
        - Node behaves like any other committed node

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
            ValueError: If node has not been saved yet
            ValueError: If any child is not committed
        """
        if self.is_committed:
            raise ImmutableNodeError(
                f"Node already committed with hash {self.hash[:7]}..."
            )

        if self._id is None:
            raise ValueError(
                "Cannot commit unsaved node. Call save() first."
            )

        # Verify all children are committed
        for child in self._get_commit_dependents():
            if not child.is_committed:
                raise ValueError(
                    f"All children must be committed before commit(). "
                    f"Found uncommitted {child.__class__.__name__}."
                )

        # Verify cardinality constraints are satisfied
        self._validate_all_cardinalities()

        # Set committed_at BEFORE computing hash (it's part of the hash for structural nodes)
        self.committed_at = time.time()
        self.hash = self.compute_hash()

        # No dedup for container nodes - they have relationships attached by commit time.
        # If duplicate content exists, the unique constraint on hash will throw.
        graph_db.save_node(self)
        return self

    def _validate_all_cardinalities(self) -> None:
        """
        Validate cardinality constraints for all relationship managers.

        Iterates through all RelationshipManager attributes on this class
        and validates that minimum cardinality constraints are satisfied.

        Raises:
            ValueError: If any cardinality constraint is violated
        """
        from dialectical_framework.graph.relationship_manager import RelationshipManager

        errors = []

        # Find all RelationshipManager attributes on this class
        for attr_name in dir(self.__class__):
            attr = getattr(self.__class__, attr_name, None)
            if isinstance(attr, RelationshipManager):
                # Get bound manager for this instance
                bound_manager = getattr(self, attr_name)
                is_valid, error_msg = bound_manager.validate_cardinality()
                if not is_valid:
                    errors.append(f"{attr_name}: {error_msg}")

        if errors:
            raise ValueError(
                f"Cardinality constraints violated on {self.__class__.__name__}:\n"
                + "\n".join(f"  - {e}" for e in errors)
            )

    @property
    def is_committed(self) -> bool:
        """Check if this node has been committed (has hash)."""
        return self.hash is not None
