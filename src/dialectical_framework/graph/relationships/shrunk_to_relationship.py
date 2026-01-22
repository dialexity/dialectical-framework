"""Relationship model for Nexus evolution (reduction)."""
from __future__ import annotations

from gqlalchemy import Relationship


class ShrunkToRelationship(Relationship, type="SHRUNK_TO"):
    """Links a Nexus to a reduced version of itself."""

    pass
