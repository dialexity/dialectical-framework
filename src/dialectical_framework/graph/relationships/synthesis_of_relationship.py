"""Relationship model for linking Synthesis to its target (Transformation or Spiral)."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class SynthesisOfRelationship(AnalyticalStructure, type="SYNTHESIS_OF"):
    """
    Links a Synthesis to its source (Transformation or Spiral).

    Part of the analytical layer - connects emergent insights to
    the analytical process that produced them.
    """

    pass
