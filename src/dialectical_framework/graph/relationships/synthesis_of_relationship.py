"""Relationship model for linking Synthesis to its target (Transformation or Spiral)."""
from __future__ import annotations

from gqlalchemy import Relationship


class SynthesisOfRelationship(Relationship, type="SYNTHESIS_OF"):
    """Links a Synthesis node to its target (Transformation or Spiral)."""

    pass
