"""
Base node class for all graph entities in the dialectical framework.

This module provides the foundational node class that all other graph nodes inherit from.
"""

from __future__ import annotations

from typing import Union
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
    """

    uid: str = Field(default_factory=lambda: str(uuid4()))

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
