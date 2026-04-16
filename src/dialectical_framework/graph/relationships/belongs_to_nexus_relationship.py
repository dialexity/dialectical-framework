"""Relationship model for WisdomUnit → Nexus membership."""

from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import \
    AnalyticalStructure


class BelongsToNexusRelationship(AnalyticalStructure, type="BELONGS_TO_NEXUS"):
    """
    Links a WisdomUnit to its exploration Nexus.

    Direction: WisdomUnit --BELONGS_TO_NEXUS--> Nexus

    A WisdomUnit can belong to multiple Nexuses (explored in different contexts),
    but each exploration (Nexus) groups a specific set of WUs.

    Part of the analytical layer - exploration context can be established after
    WU commit since it tracks exploration relationships, not node identity.
    """

    pass
