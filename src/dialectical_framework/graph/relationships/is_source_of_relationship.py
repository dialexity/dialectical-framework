"""Relationship model for Transition source component."""
from __future__ import annotations

from gqlalchemy import Relationship


class IsSourceOfRelationship(Relationship, type="IS_SOURCE_OF"):
    """Links a DialecticalComponent as the source of a Transition."""

    pass
