"""Relationship model for Cycle/Wheel evolution lineage."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import IdentityRelationship


class EvolvedToRelationship(IdentityRelationship, type="EVOLVED_TO"):
    """
    Links a parent Cycle/Wheel to its evolved children.

    Direction: Parent --EVOLVED_TO--> Child

    For Cycle: Parent Cycle evolved to Child Cycle by adding a WisdomUnit.
    For Wheel: Parent Wheel evolved to Child Wheel by adding a layer (more WUs from the pool).

    This forms a tree structure for exploration:
    - Cycle tree: growing the WU pool
    - Wheel tree: growing layers within a Cycle's pool

    When computing Transformations, traverse ancestors to find computation context.
    Respect intent matching during traversal (inherit if None).

    Part of the structural layer - evolution lineage is immutable once committed.
    """

    pass
