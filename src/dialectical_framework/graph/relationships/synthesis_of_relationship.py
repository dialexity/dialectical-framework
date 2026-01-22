"""Relationship model for linking Synthesis to its parent WisdomUnit."""
from __future__ import annotations

from gqlalchemy import Relationship


class SynthesisOfRelationship(Relationship, type="SYNTHESIS_OF"):
    """Links a Synthesis node to the WisdomUnit it synthesizes."""

    pass
