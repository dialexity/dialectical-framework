"""Relationship model for Nexus evolution (growth)."""
from __future__ import annotations

from gqlalchemy import Relationship


class ExpandedToRelationship(Relationship, type="EXPANDED_TO"):
    """Links a Nexus to an expanded version of itself."""

    pass
