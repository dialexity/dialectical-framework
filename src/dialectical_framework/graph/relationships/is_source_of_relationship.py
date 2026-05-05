"""Relationship model for Transition source component."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import IdentityRelationship


class IsSourceOfRelationship(IdentityRelationship, type="IS_SOURCE_OF"):
    """
    Links a Statement as the source of a Transition.

    Part of the structural layer - defines what the Transition represents.
    """

