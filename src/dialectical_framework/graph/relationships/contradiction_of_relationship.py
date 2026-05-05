"""
Relationship model for statement contradiction.

This module provides the ContradictionOfRelationship class for representing
mutually exclusive/contradicting statements.
"""

from __future__ import annotations

from gqlalchemy import Relationship


class ContradictionOfRelationship(Relationship, type="CONTRADICTION_OF"):
    """
    Relationship representing contradiction between statements.

    This is a symmetric relationship for mutually exclusive statements:
    - T+ vs A- (positive thesis contradicts negative antithesis)
    - A+ vs T- (positive antithesis contradicts negative thesis)

    Unlike OPPOSITE_OF (T vs A dialectical opposition), CONTRADICTION_OF
    captures logical incompatibility between polarized aspects.
    """

