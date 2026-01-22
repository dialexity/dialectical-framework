"""Relationship model for negative side derivation."""
from __future__ import annotations

from gqlalchemy import Relationship


class NegativeSideOfRelationship(Relationship, type="NEGATIVE_SIDE_OF"):
    """Links a negative aspect component to its neutral parent."""

    pass
