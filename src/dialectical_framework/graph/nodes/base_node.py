"""
Base node class for all graph entities in the dialectical framework.

This module provides the foundational node class that all other graph nodes inherit from.
"""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from gqlalchemy import Node
from pydantic.v1 import Field


class BaseNode(Node):
    """
    Base class for all nodes in the dialectical graph.

    All nodes in the system inherit from this class and automatically
    get a unique identifier (uid).
    """

    uid: str = Field(default_factory=lambda: str(uuid4()))

    def __repr__(self) -> str:
        """String representation of the node."""
        return f"{self.__class__.__name__}(uid={self.uid})"
