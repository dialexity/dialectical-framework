"""Relationship model for Spiral/Transformation linkage."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class IsSpiralOfRelationship(AnalyticalStructure, type="IS_SPIRAL_OF"):
    """
    Links a Spiral to its Wheel, or a Transformation to its WisdomUnit.

    Part of the analytical layer - connects analytical artifacts to
    their structural context. Can evolve without affecting structure.
    """

    pass
