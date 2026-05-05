"""
Relationship model for dialectical opposition.

This module provides the OppositeOfRelationship class for representing
dialectical opposition between T (thesis) and A (antithesis) statements.
"""

from __future__ import annotations

from gqlalchemy import Relationship


class OppositeOfRelationship(Relationship, type="OPPOSITE_OF"):
    """
    Relationship representing dialectical opposition between T and A components.

    This is a symmetric relationship: if T opposes A, then A opposes T.
    Used exclusively for thesis-antithesis pairs.
    """

