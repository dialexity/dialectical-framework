"""Relationship model for statement provenance."""
from __future__ import annotations

from gqlalchemy import Relationship


class HasStatementRelationship(Relationship, type="HAS_STATEMENT"):
    """Links an Input, Transition, or Rationale to derived DialecticalComponents."""

    pass
