"""Relationship model for Input → Ideas provenance link."""
from __future__ import annotations

from gqlalchemy import Relationship


class DistilledToRelationship(Relationship, type="DISTILLED_TO"):
    """
    Input -[:DISTILLED_TO]-> Ideas: marks which Ideas were derived from this Input.

    Not a BackboneStructure - created after Input is committed to track derivation.
    """

