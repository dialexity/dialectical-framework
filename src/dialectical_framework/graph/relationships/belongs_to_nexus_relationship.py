"""Relationship model for WisdomUnit membership in a Nexus."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import ContainerMembership


class BelongsToNexusRelationship(ContainerMembership, type="BELONGS_TO_NEXUS"):
    """
    Links a WisdomUnit to the Nexus pool it belongs to.

    Part of the structural layer - defines the Nexus's composition.
    The Nexus hash includes its WisdomUnits via _get_committed_children().
    """

    pass
