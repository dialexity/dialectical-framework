"""Relationship model for linking Synthesis to its target Perspective."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class SynthesisOfRelationship(AnalyticalStructure, type="SYNTHESIS_OF"):
    """
    Links a Synthesis to its source Perspective.

    Part of the analytical layer - connects emergent insights to
    the Perspective's T-A tension that produced them.
    """

    pass
