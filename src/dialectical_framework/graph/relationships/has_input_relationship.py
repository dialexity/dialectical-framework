"""Relationship model for Case to Input connection."""
from __future__ import annotations

from gqlalchemy import Relationship


class HasInputRelationship(Relationship, type="HAS_INPUT"):
    """
    Links a Case to its Input sources.

    Not a BackboneStructure - Case doesn't have immutable structure.
    """

