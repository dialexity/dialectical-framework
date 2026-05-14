"""Relationship model for linking Synthesis to its target Wheel."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class SynthesisOfRelationship(AnalyticalStructure, type="SYNTHESIS_OF"):
    """
    Links a Synthesis to its source Wheel.

    Part of the analytical layer - connects emergent insights to
    the Wheel's circular causality system that produced them.
    """

