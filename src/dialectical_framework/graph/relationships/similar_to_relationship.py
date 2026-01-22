"""Relationship model for semantic similarity between components."""
from __future__ import annotations

from typing import Optional

from gqlalchemy import Relationship


class SimilarToRelationship(Relationship, type="SIMILAR_TO"):
    """Links semantically similar dialectical components.

    This relationship captures similarity between components,
    complementing the OppositeOfRelationship for opposition.

    Example:
        Component("Democracy") -[strength=0.8]-> Component("Republic")
    """

    strength: float = 1.0
    type: Optional[str] = None
