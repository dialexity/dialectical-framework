"""Relationship model for Rationale providing an Estimation."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class ProvidesRelationship(AnalyticalStructure, type="PROVIDES"):
    """
    Links a Rationale to an Estimation it provides.

    Part of the analytical layer - connects rationales to the
    estimations they justify.
    """

    pass
