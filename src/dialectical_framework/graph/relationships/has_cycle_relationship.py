"""Relationship model for Nexus producing a Cycle."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class HasCycleRelationship(AnalyticalStructure, type="HAS_CYCLE"):
    """
    Links a Nexus to a Cycle derived from it.

    Analytical relationship - Cycles are derived artifacts that don't
    affect the Nexus's structural hash. A committed Nexus can have
    new Cycles attached with different intents.
    """

    pass
