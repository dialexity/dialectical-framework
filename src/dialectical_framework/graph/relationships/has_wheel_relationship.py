"""Relationship model for Cycle having a Wheel."""
from __future__ import annotations

from gqlalchemy import Relationship


class HasWheelRelationship(Relationship, type="HAS_WHEEL"):
    """Links a Cycle to its detailed Wheel view."""

    pass
