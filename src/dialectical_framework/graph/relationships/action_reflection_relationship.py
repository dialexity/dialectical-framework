"""Relationship model for Transformation action-reflection context."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class ActionReflectionRelationship(AnalyticalStructure, type="ACTION_REFLECTION"):
    """
    Links a Transformation to its action-reflection WisdomUnit context.

    Part of the analytical layer - defines the dialectical context
    (action WU and reflection WU) for the Transformation.
    """

    pass
