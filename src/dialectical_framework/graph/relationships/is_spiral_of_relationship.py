"""Relationship model for Spiral/Transformation linkage."""
from __future__ import annotations

from gqlalchemy import Relationship


class IsSpiralOfRelationship(Relationship, type="IS_SPIRAL_OF"):
    """Links a Spiral to its Wheel, or a Transformation to its WisdomUnit."""

    pass
