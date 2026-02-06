"""Relationship model for Cycle having a Wheel."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import ContainerMembership


class HasWheelRelationship(ContainerMembership, type="HAS_WHEEL"):
    """
    Links a Cycle to its detailed Wheel view.

    Part of the structural layer - connects Cycle to its detailed Wheel.
    """

    pass
