"""Relationship model for linking Synthesis to its target WisdomUnit."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class SynthesisOfRelationship(AnalyticalStructure, type="SYNTHESIS_OF"):
    """
    Links a Synthesis to its source WisdomUnit.

    Part of the analytical layer - connects emergent insights to
    the WisdomUnit's T-A tension that produced them.
    """

    pass
