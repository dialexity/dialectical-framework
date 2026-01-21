"""
Base node class for all graph entities in the dialectical framework.

This module provides the foundational node class that all other graph nodes inherit from.
"""

from __future__ import annotations

from typing import Optional, Union
from uuid import uuid4

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j, Node
from pydantic.v1 import Field

from dialectical_framework.enums.di import DI


class BaseNode(Node):
    """
    Base class for all nodes in the dialectical graph.

    All nodes in the system inherit from this class and automatically
    get a unique identifier (uid).

    Attributes:
        uid: Auto-generated unique identifier (UUID)
        handle: Optional user-friendly identifier (slug, readable name).
                Use instead of uid for human-facing references.
    """

    uid: str = Field(default_factory=lambda: str(uuid4()))
    handle: Optional[str] = None

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
        graph_db.save_node(self)
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
