"""Relationship model for Rationale explaining an entity."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class ExplainsRelationship(AnalyticalStructure, type="EXPLAINS"):
    """
    Links a Rationale to the AssessableEntity it explains.

    Part of the analytical layer - connects explanatory artifacts
    to the entities they analyze. Target stored in Rationale's data.
    """

    pass
