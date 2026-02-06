"""Relationship model for Brainstorm to Input connection."""
from __future__ import annotations

from gqlalchemy import Relationship


class HasInputRelationship(Relationship, type="HAS_INPUT"):
    """
    Links a Brainstorm to its Input sources.

    Not a BackboneStructure - Brainstorm doesn't have immutable structure.
    """

    pass
