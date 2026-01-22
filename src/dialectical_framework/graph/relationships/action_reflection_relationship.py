"""Relationship model for Transformation action-reflection context."""
from __future__ import annotations

from gqlalchemy import Relationship


class ActionReflectionRelationship(Relationship, type="ACTION_REFLECTION"):
    """Links a Transformation to its action-reflection WisdomUnit context."""

    pass
