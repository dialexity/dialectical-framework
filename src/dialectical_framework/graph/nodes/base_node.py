"""
Base node class for all graph entities in the dialectical framework.

This module provides the foundational node class that all other graph nodes inherit from.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Union
from uuid import uuid4

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j
from pydantic.v1 import BaseModel, Field

from dialectical_framework.enums.di import DI


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class BaseNode(BaseModel):
    """
    Base class for all nodes in the dialectical graph.

    All nodes in the system inherit from this class and automatically
    get a unique identifier (uid).

    Attributes:
        uid: Auto-generated unique identifier (UUID)
        handle: Optional user-friendly identifier (slug, readable name).
                Use instead of uid for human-facing references.
        created_at: ISO 8601 UTC timestamp of node creation.
        updated_at: ISO 8601 UTC timestamp of last save.
    """

    uid: str = Field(default_factory=lambda: str(uuid4()))
    handle: Optional[str] = None
    created_at: str = Field(default_factory=_utc_now_iso)
    updated_at: str = Field(default_factory=_utc_now_iso)

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
        result = graph_db.save_node(self)
        # GQLAlchemy returns a new node object with _id set - capture it
        if result is not None and result._id is not None:
            self._id = result._id
        return self

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
