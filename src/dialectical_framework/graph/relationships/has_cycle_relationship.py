"""Relationship model for Nexus producing a Cycle."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import ContainerMembership


class HasCycleRelationship(ContainerMembership, type="HAS_CYCLE"):
    """
    Links a Nexus to a Cycle derived from it.

    Part of the structural layer - connects Nexus to its Cycles.
    A Nexus can have multiple Cycles with different intents.
    """

    pass
