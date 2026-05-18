"""Relationship model for Ideas → Input provenance link."""
from __future__ import annotations

from gqlalchemy import Relationship


class DistilledFromRelationship(Relationship, type="DISTILLED_FROM"):
    """
    Ideas -[:DISTILLED_FROM]-> Input: marks which Input(s) an Ideas was derived from.

    Not a BackboneStructure - created after Input is committed to track derivation.
    """

