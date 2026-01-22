"""Relationship model for WisdomUnit evolution."""
from __future__ import annotations

from gqlalchemy import Relationship


class ChangedToRelationship(Relationship, type="CHANGED_TO"):
    """Links a WisdomUnit to its evolved successor."""

    pass
