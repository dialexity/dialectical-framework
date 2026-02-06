"""Relationship model for Input to Ideas connection."""
from __future__ import annotations

from gqlalchemy import Relationship


class DistilledToRelationship(Relationship, type="DISTILLED_TO"):
    """
    Links an Input to Ideas derived from it.

    Not a BackboneStructure - created after Input is committed to track derivation.
    """

    pass
