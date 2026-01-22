"""Relationship model for positive side derivation."""
from __future__ import annotations

from gqlalchemy import Relationship


class PositiveSideOfRelationship(Relationship, type="POSITIVE_SIDE_OF"):
    """Links a positive aspect component to its neutral parent."""

    pass
