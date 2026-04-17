"""Relationship model for Perspective → Nexus membership."""

from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import \
    AnalyticalStructure


class BelongsToNexusRelationship(AnalyticalStructure, type="BELONGS_TO_NEXUS"):
    """
    Links a Perspective to its exploration Nexus.

    Direction: Perspective --BELONGS_TO_NEXUS--> Nexus

    A Perspective can belong to multiple Nexuses (explored in different contexts),
    but each exploration (Nexus) groups a specific set of PPs.

    Part of the analytical layer - exploration context can be established after
    PP commit since it tracks exploration relationships, not node identity.
    """

    pass
