"""Relationship model for Rationale critique chains."""
from __future__ import annotations

from gqlalchemy import Relationship


class CritiquesRelationship(Relationship, type="CRITIQUES"):
    """Links a Rationale to another Rationale it critiques."""

    pass
