"""
Base node class for all graph entities in the dialectical framework.

This module provides the foundational node class that all other graph nodes inherit from.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional, Union
from uuid import uuid4

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j, Node
from pydantic.v1 import Field

from dialectical_framework.enums.di import DI


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BaseNode(Node, label="Node"):
    """
    Base class for all nodes in the dialectical graph.

    All nodes in the system inherit from this class and automatically
    get a unique identifier (uid).

    Attributes:
        uid: Auto-generated unique identifier (UUID4)
        sid: Scope identifier - the uid of the root Brainstorm this node belongs to.
             For Brainstorm nodes, sid == uid. For all descendants, sid is inherited.
        origin_uid: Lineage identifier - preserved across clones for provenance tracking.
                    For new nodes, origin_uid == uid. For cloned nodes, traces back to original.
        nid: Portable address - computed as <sid>:<uid>, or just <sid> for Brainstorm.
             This is the primary queryable identifier for external references.
        handle: Optional user-friendly identifier (slug, readable name).
                Use instead of uid for human-facing references.
        created_at: ISO 8601 UTC timestamp of node creation.
        updated_at: ISO 8601 UTC timestamp of last save.
    """

    uid: str = Field(default_factory=lambda: str(uuid4()))
    sid: Optional[str] = None
    origin_uid: Optional[str] = None
    nid: Optional[str] = None
    handle: Optional[str] = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)

    def __init__(self, **data: Any) -> None:
        """
        Initialize a node with auto-populated identifier fields.

        Auto-population:
        - sid: If not provided, attempts to get from ScopeContext (via DI).
               If DI not configured or no scope set, remains None.
        - origin_uid: Set to uid after super().__init__ for new nodes.
                      For cloned nodes, should be explicitly provided.

        Args:
            **data: Field values for the node
        """
        # Auto-populate sid from context if not provided
        if "sid" not in data or data["sid"] is None:
            try:
                from dialectical_framework.graph.scope_context import di_scope_context
                data["sid"] = di_scope_context().get_current_scope()
            except Exception:
                # DI not configured (e.g., in some tests) - leave as None
                pass

        super().__init__(**data)

        # Set origin_uid = uid for new nodes (must happen after super().__init__)
        if self.origin_uid is None:
            self.origin_uid = self.uid

    def _compute_nid(self) -> str:
        """
        Compute the portable address (nid) from sid and uid.

        Returns:
            - For orphan nodes (sid is None): just uid
            - For scope root (Brainstorm, sid == uid): just sid
            - For all other nodes: <sid>:<uid>
        """
        if self.sid is None:
            return self.uid  # Orphan node fallback
        if self.sid == self.uid:
            return self.sid  # Brainstorm: nid = sid
        return f"{self.sid}:{self.uid}"

    @inject
    def save(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> "BaseNode":
        """
        Save this node to the graph database.

        Uses dependency injection to get the database connection.
        Tests can override the graph_db provider to use TestMemgraph/TestNeo4j.

        Returns:
            Self for chaining
        """
        self.updated_at = _utc_now_iso()
        # Compute nid before save (ensures it's always current)
        self.nid = self._compute_nid()
        result = graph_db.save_node(self)
        # GQLAlchemy returns a new node object with _id set - capture it
        if result is not None and result._id is not None:
            self._id = result._id
        return self

    def clone(self, destination_sid: str) -> BaseNode:
        """
        Clone this node into a new scope.

        Clone semantics (from portability.md):
        - Generate new uid (automatic via Field default_factory)
        - Set sid = destination_sid
        - Preserve origin_uid (traces lineage back to original)
        - nid is recomputed on save

        The cloned node is NOT saved automatically - call .save() after cloning.

        Args:
            destination_sid: The scope ID of the destination (new Brainstorm's uid)

        Returns:
            New node instance of the same class (not saved)

        Example:
            # Clone a component to a new scope
            new_brainstorm = Brainstorm()
            new_brainstorm.save()

            cloned = original_component.clone(destination_sid=new_brainstorm.uid)
            cloned.save()

            # cloned.uid is new (different from original)
            # cloned.sid == new_brainstorm.uid
            # cloned.origin_uid == original.origin_uid (traces lineage)
        """
        # Collect field values, excluding identity fields
        data: dict[str, Any] = {}
        excluded_fields = {'uid', 'sid', 'nid', '_id', 'created_at', 'updated_at'}

        for field_name in self.__fields__:
            if field_name not in excluded_fields:
                data[field_name] = getattr(self, field_name)

        # Preserve lineage: use source's origin_uid (or uid if missing)
        data['origin_uid'] = self.origin_uid or self.uid
        # Set new scope
        data['sid'] = destination_sid

        # Create new instance of the same class
        # uid, created_at, updated_at will be auto-generated
        # nid will be computed on save
        return self.__class__(**data)

    def __repr__(self) -> str:
        """String representation of the node."""
        return f"{self.__class__.__name__}(uid={self.uid})"

    def __hash__(self) -> int:
        """Hash based on uid for use in sets and dict keys."""
        return hash(self.uid)

    def __eq__(self, other: object) -> bool:
        """Equality based on uid."""
        if not isinstance(other, BaseNode):
            return NotImplemented
        return self.uid == other.uid
