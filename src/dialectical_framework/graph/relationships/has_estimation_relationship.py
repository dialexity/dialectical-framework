"""Relationship model for P/R estimations on AssessableEntity."""
from __future__ import annotations

from gqlalchemy import Relationship


class HasEstimationRelationship(Relationship, type="HAS_ESTIMATION"):
    """Links an AssessableEntity to its P/R estimation values."""

    pass
