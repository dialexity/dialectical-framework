"""Relationship model for Wheel having a Transformation."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class HasTransformationRelationship(AnalyticalStructure, type="HAS_TRANSFORMATION"):
    """
    Links a Wheel to its Transformations.

    Analytical relationship - Transformations are derived artifacts that don't
    affect the Wheel's structural hash. A committed Wheel can have
    new Transformations attached.

    Transformations belong to Wheel and can span multiple WUs. The source/target
    WUs are derived from the Ac+ transition's source/target components.
    """

    pass
