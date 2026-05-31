"""
Polarity node for the dialectical framework.

Polarity represents a T-A dialectical pair - the fundamental opposition
between thesis (T) and antithesis (A). This is the first structural step
in building a Perspective.
"""

from __future__ import annotations

import time
from typing import ClassVar, Optional, Union, TYPE_CHECKING, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipManager,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    TRelationship,
    ARelationship,
    HasPolarityRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.perspective import Perspective


# Position constants for Polarity
POSITION_T = "T"
POSITION_A = "A"


class Polarity(AssessableEntity, label="Polarity"):
    """
    Represents a T-A dialectical pair.

    A Polarity captures the fundamental opposition between thesis (T) and antithesis (A).
    The heuristic_similarity (HS) on the ARelationship measures how similar/related
    the T-A pair is semantically.

    Polarity is a shared structural atom — same T+A = same Polarity. The interpretive
    lens belongs on Perspective (via intent), not here.

    Lifecycle (atomic creation like Transition):
        1. polarity = Polarity()
        2. polarity.set_t(thesis, heuristic_similarity=1.0)
        3. polarity.set_a(antithesis, heuristic_similarity=0.75)
        4. polarity.commit()  # Saves, connects, computes hash atomically

    After commit(), the Polarity can be used as the basis for Perspectives, which add aspects to each side.

    Hierarchy:
        Statement(T) + Statement(A) → Polarity → Perspective

    Example:
        thesis = Statement(text="Remote work increases productivity")
        thesis.commit()

        antithesis = Statement(text="Office work enables collaboration")
        antithesis.commit()

        polarity = Polarity()
        polarity.set_t(thesis)
        polarity.set_a(antithesis, heuristic_similarity=0.72)
        polarity.commit()
    """

    # Stored hashes for hash computation (set before commit)
    _t_hash: Optional[str] = None
    _a_hash: Optional[str] = None

    # Transient refs for auto-connecting after save (not persisted)
    _t_ref: Optional[Statement] = None
    _a_ref: Optional[Statement] = None

    # Relationship properties to store until commit
    _t_hs: float = 1.0  # T always has HS=1.0 (defines the apex)
    _a_hs: Optional[float] = None

    # T position (exactly one thesis)
    t: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=TRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A position (exactly one antithesis)
    # The ARelationship stores heuristic_similarity (HS) for the T-A pair
    a: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=ARelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # Perspectives that reference this Polarity
    # One Polarity can have multiple Perspectives (different tetrad interpretations)
    perspectives: ClassVar[RelationshipManager[Perspective]] = RelationshipFrom(
        "Perspective",
        model=HasPolarityRelationship,
        cardinality=(0, None)  # Zero or more
    )

    def set_t(
        self,
        component: Statement,
        heuristic_similarity: float = 1.0,
    ) -> Self:
        """
        Set the thesis component for this polarity (before commit).

        This stores the reference for hash computation and auto-connection after save.
        The component must already be committed (have hash).

        Args:
            component: The committed thesis component
            heuristic_similarity: HS value (default 1.0 - T defines the apex)

        Returns:
            Self for chaining
        """
        if not component.is_committed:
            raise ValueError("Thesis component must be committed before setting on Polarity")
        self._t_hash = component.hash
        self._t_ref = component
        self._t_hs = heuristic_similarity
        return self

    def set_a(
        self,
        component: Statement,
        heuristic_similarity: Optional[float] = None,
    ) -> Self:
        """
        Set the antithesis component for this polarity (before commit).

        This stores the reference for hash computation and auto-connection after save.
        The component must already be committed (have hash).

        Args:
            component: The committed antithesis component
            heuristic_similarity: HS value measuring T-A semantic relatedness

        Returns:
            Self for chaining
        """
        if not component.is_committed:
            raise ValueError("Antithesis component must be committed before setting on Polarity")
        self._a_hash = component.hash
        self._a_ref = component
        self._a_hs = heuristic_similarity
        return self

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Polarity.

        Parts: sorted hashes of T and A components.
        Sorting makes the hash order-independent (T-A vs A-T produces same hash).

        Returns:
            List of strings: [hash1, hash2] (sorted)

        Raises:
            ValueError: If T or A is not set
        """
        hashes = []

        # Get T hash - prefer stored hash, fall back to relationship
        t_hash = self._t_hash
        if not t_hash:
            result = self.t.get()
            if result:
                comp, _ = result
                if not comp.is_committed:
                    raise ValueError("T component must be committed before computing Polarity hash")
                t_hash = comp.hash
        if t_hash:
            hashes.append(t_hash)

        # Get A hash - prefer stored hash, fall back to relationship
        a_hash = self._a_hash
        if not a_hash:
            result = self.a.get()
            if result:
                comp, _ = result
                if not comp.is_committed:
                    raise ValueError("A component must be committed before computing Polarity hash")
                a_hash = comp.hash
        if a_hash:
            hashes.append(a_hash)

        # Require both T and A for a meaningful hash
        if len(hashes) < 2:
            raise ValueError(
                "Polarity requires both T and A to be set before commit. "
                "Use set_t() and set_a()."
            )

        # Sort for order-independence: Polarity(T=X, A=Y) == Polarity(T=Y, A=X)
        hashes.sort()
        return hashes

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db],
    ) -> Self:
        """
        Commit this polarity: save, create relationships, compute hash.

        If T/A were set via set_t()/set_a(), relationships are created
        atomically during commit. The hash includes both component hashes.

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
            ValueError: If T or A is not set
        """
        if self.is_committed:
            from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
            raise ImmutableNodeError(
                f"Polarity already committed with hash {self.hash[:7]}..."
            )

        # Validate both T and A are set
        if not self._t_hash or not self._a_hash:
            raise ValueError(
                "Polarity requires both T and A to be set before commit. "
                "Use set_t() and set_a()."
            )

        # T and A must be different Statements (a polarity requires genuine opposition)
        if self._t_hash == self._a_hash:
            raise ValueError(
                "Polarity requires T and A to be different Statements. "
                f"Both point to the same hash: {self._t_hash[:7]}..."
            )

        # Save node (get _id) before connecting relationships
        if self._id is None:
            result = graph_db.save_node(self)
            if result is not None and result._id is not None:
                self._id = result._id

        # Connect structural relationships BEFORE computing hash
        if self._t_ref:
            self.t.connect(
                self._t_ref,
                relationship=TRelationship(
                    alias=POSITION_T,
                    heuristic_similarity=self._t_hs,
                ),
            )
            self._t_ref = None  # Clear transient ref

        if self._a_ref:
            self.a.connect(
                self._a_ref,
                relationship=ARelationship(
                    alias=POSITION_A,
                    heuristic_similarity=self._a_hs,
                ),
            )
            self._a_ref = None  # Clear transient ref

        # Set committed_at BEFORE computing hash (it's part of the hash)
        self.committed_at = time.time()
        self.hash = self.compute_hash()

        # Update in DB with hash
        graph_db.save_node(self)

        return self

    @property
    def heuristic_similarity(self) -> float | None:
        """
        Get the heuristic similarity (HS) for this T-A pair.

        HS is stored on the ARelationship edge. It measures how semantically
        similar/related the thesis and antithesis are.

        Returns:
            The HS value (0.0-1.0), or None if A is not connected
        """
        # If not yet committed, return stored value
        if self._a_hs is not None and not self.is_committed:
            return self._a_hs

        a_result = self.a.get()
        if a_result:
            _, rel = a_result
            if isinstance(rel, ARelationship):
                return rel.heuristic_similarity
        return None

    def get_t_component(self) -> Statement | None:
        """Get the thesis component, or None if not connected."""
        result = self.t.get()
        return result[0] if result else None

    def get_a_component(self) -> Statement | None:
        """Get the antithesis component, or None if not connected."""
        result = self.a.get()
        return result[0] if result else None

    def __repr__(self) -> str:
        """String representation of the polarity."""
        hash_str = self.short_hash if self.is_committed else "uncommitted"
        t_comp = self.get_t_component()
        a_comp = self.get_a_component()
        t_preview = t_comp.text[:20] + "..." if t_comp and len(t_comp.text) > 20 else (t_comp.text if t_comp else "None")
        a_preview = a_comp.text[:20] + "..." if a_comp and len(a_comp.text) > 20 else (a_comp.text if a_comp else "None")
        return f"Polarity({hash_str}, T='{t_preview}', A='{a_preview}')"

    def __str__(self) -> str:
        """Human-readable string representation."""
        t_comp = self.get_t_component()
        a_comp = self.get_a_component()
        t_str = (t_comp.display_text or t_comp.text) if t_comp else "?"
        a_str = (a_comp.display_text or a_comp.text) if a_comp else "?"
        hs = self.heuristic_similarity
        hs_str = f", HS={hs:.2f}" if hs is not None else ""
        return f"T: {t_str} ↔ A: {a_str}{hs_str}"
