"""Relationship model for Cycle having a Wheel."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class HasWheelRelationship(AnalyticalStructure, type="HAS_WHEEL"):
    """
    Links a Cycle to its detailed Wheel view.

    Analytical relationship - Wheels are derived artifacts that don't
    affect the Cycle's structural hash. A committed Cycle can have
    new Wheels attached.
    """

