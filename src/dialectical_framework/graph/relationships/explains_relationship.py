"""Relationship model for Rationale explaining an entity."""
from __future__ import annotations

from gqlalchemy import Relationship


class ExplainsRelationship(Relationship, type="EXPLAINS"):
    """Links a Rationale to the AssessableEntity it explains."""

    pass
