"""
Mixin for nodes that can be built incrementally before committing.

This mixin is for container nodes that need children added incrementally
before being finalized:
- Ideas: add Statements
- Perspective: add the Polarity and the four aspect Statements
- Synthesis: add S+ / S-
- Wheel: add Transitions (its edges)
- Transformation: add Transitions for each of its six positions

Cycle is NOT in that list, despite being the obvious candidate: it holds its
members as an ordered field of hashes (`set_perspectives`), not as children to
attach, so it commits atomically like any other node. Neither is Transition.

The pattern follows git's staging area concept:
- save() persists with hash=None (HEAD state, mutable)
- add children incrementally while in HEAD state
- commit() computes Merkle hash, making the node immutable
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Iterator, Self, Union

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

    Used by: Ideas, Perspective, Synthesis, Wheel, Transformation.
    NOT Cycle and NOT Transition — see the module docstring for why.

    Lifecycle:
        1. Create node: ideas = Ideas(intent="...")
        2. Save as HEAD: ideas.save()  # hash=None, saved_at=now, persisted
        3. Add children: ideas.statements.connect(statement)
        4. Commit: ideas.commit()  # committed_at set, hash computed, saved_at cleared

    After commit(), the node behaves like any other committed node.

    Subclasses MUST implement:
        - _get_commit_dependents(): Returns iterator of child nodes to verify
          before hashing. The base raises NotImplementedError, so a container
          that skips it fails at commit(), not at construction.
    """

    # These will be provided by the actual node class
    hash: str | None
    _id: Any
    committed_at: float | None

    # Tracks when save() persisted this node before commit.
    # Non-null means the node is being built. Cleared on commit().
    # Stale values (old timestamps with no commit) indicate abandoned garbage.
    saved_at: float | None

    @inject
    def save(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Self:
        """
        Persist this node as HEAD state, recording saved_at timestamp.

        saved_at marks that this node is actively being built. It is cleared
        on commit(). A stale saved_at with no commit indicates abandoned garbage.
        """
        if not self.is_committed:
            self.saved_at = time.time()
        return super().save(graph_db=graph_db)

    def _get_commit_dependents(self) -> Iterator[BaseNode]:
        """
        Get the children that must already be committed before this node can be.

        Override in subclasses to return the appropriate children:
        - Ideas: yields Statements
        - Perspective: yields the Polarity and the four aspects
        - Synthesis: yields S+ and S-
        - Wheel: yields Transitions (its edges)
        - Transformation: yields the Transition at each of its six positions

        These are the nodes commit() checks for is_committed. They are not
        necessarily the same set that ends up in the hash — that is
        _collect_structure_hash_parts()'s job, and e.g. Wheel folds in its
        cycle hash without yielding the Cycle here.

        Yields:
            Child nodes that must be committed first
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
        self.saved_at = None
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
