"""Relationship model for Nexus producing a Cycle."""
from __future__ import annotations

from gqlalchemy import Relationship


class HasCycleRelationship(Relationship, type="HAS_CYCLE"):
    """Links a Nexus to a Cycle derived from it."""

    pass
