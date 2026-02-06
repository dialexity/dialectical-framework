"""Relationship model for Transition ownership in structural containers."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import ContainerMembership


class BelongsToCycleRelationship(ContainerMembership, type="BELONGS_TO_CYCLE"):
    """
    Links a Transition to structural containers (Cycle, Wheel).

    Part of the structural layer - defines which Transitions make up
    the Cycle/Wheel reasoning pathway. The container's hash includes
    its transitions via _get_committed_children().

    Note: Transitions can also belong to analytical containers
    (Spiral, Transformation) via separate relationships.
    """

    pass
