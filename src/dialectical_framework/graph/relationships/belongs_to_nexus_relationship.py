"""Relationship model for WisdomUnit membership in a Nexus."""
from __future__ import annotations

from gqlalchemy import Relationship


class BelongsToNexusRelationship(Relationship, type="BELONGS_TO_NEXUS"):
    """Links a WisdomUnit to the Nexus pool it belongs to."""

    pass
