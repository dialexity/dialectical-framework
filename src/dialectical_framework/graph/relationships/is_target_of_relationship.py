"""Relationship model for Transition target component."""
from __future__ import annotations

from gqlalchemy import Relationship


class IsTargetOfRelationship(Relationship, type="IS_TARGET_OF"):
    """Links a Transition to its target DialecticalComponent."""

    pass
