"""Relationship model for Transition target component."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import IdentityRelationship


class IsTargetOfRelationship(IdentityRelationship, type="IS_TARGET_OF"):
    """
    Links a Transition to its target Statement.

    Part of the structural layer - defines what the Transition represents.
    """

    pass
