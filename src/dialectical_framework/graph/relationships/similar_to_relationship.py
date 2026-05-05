"""Relationship model for semantic similarity between statements."""
from __future__ import annotations

from typing import Optional

from gqlalchemy import Relationship


class SimilarToRelationship(Relationship, type="SIMILAR_TO"):
    """Links semantically similar statements.

    This relationship captures similarity between statements,
    complementing the OppositeOfRelationship for opposition.

    Example:
        Statement("Democracy") -[strength=0.8]-> Statement("Republic")
    """

    strength: float = 1.0
    type: Optional[str] = None
