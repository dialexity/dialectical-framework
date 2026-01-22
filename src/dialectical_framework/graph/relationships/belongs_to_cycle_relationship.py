"""Relationship model for Transition ownership."""
from __future__ import annotations

from gqlalchemy import Relationship


class BelongsToCycleRelationship(Relationship, type="BELONGS_TO_CYCLE"):
    """Links a Transition to its owner (Cycle, Spiral, Transformation, or Wheel)."""

    pass
