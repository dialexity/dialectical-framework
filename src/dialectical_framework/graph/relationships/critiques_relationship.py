"""Relationship model for Rationale critique chains."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class CritiquesRelationship(AnalyticalStructure, type="CRITIQUES"):
    """
    Links a Rationale to another Rationale it critiques (audit chain).

    Part of the analytical layer - connects critique/audit artifacts
    to form chains of deepening analysis. Target stored in Rationale's data.
    """

    pass
