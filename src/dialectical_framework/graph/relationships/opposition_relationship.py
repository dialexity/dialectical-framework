"""
Relationship model for dialectical component opposition.

This module provides the OppositionRelationship class for representing
semantic opposition between dialectical components.
"""

from __future__ import annotations

from typing import Optional

from gqlalchemy import Relationship


class OppositionRelationship(Relationship, type="OPPOSITE_OF"):
    """
    Relationship representing semantic opposition between components.

    This relationship captures the degree and type of opposition between
    two dialectical components, useful for semantic analysis and validation.

    Example:
        Component("Peace") -[strength=0.9, type="semantic"]-> Component("War")
    """

    strength: float = 1.0
    type: Optional[str] = None

    def __repr__(self) -> str:
        """String representation of the relationship."""
        return f"OppositionRelationship(strength={self.strength}, type={self.type})"
