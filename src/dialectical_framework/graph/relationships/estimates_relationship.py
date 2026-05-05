"""Relationship model for Estimation → AssessableEntity."""
from __future__ import annotations

from dialectical_framework.graph.relationships.immutable_structure import AnalyticalStructure


class EstimatesRelationship(AnalyticalStructure, type="ESTIMATES"):
    """
    Links an Estimation to the AssessableEntity it estimates.

    Part of the analytical layer - connects scoring artifacts to entities.
    Target stored in Estimation's target_hash field.
    """

