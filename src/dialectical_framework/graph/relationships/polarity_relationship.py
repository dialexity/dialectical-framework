"""
Polarity relationships for connecting DialecticalComponents to WisdomUnits.

Each polarity position has its own relationship type for fine-grained querying,
but all store the contextual alias property.
"""

from __future__ import annotations

from gqlalchemy import Relationship


# Base class for all polarity relationships
class BasePolarityRelationship(Relationship):
    """
    Base for all polarity relationships with alias property.

    The alias stores the component's contextual position (e.g., "T1", "A2+").
    Same component can have different aliases in different WisdomUnits.
    """

    alias: str


# T-side relationships
class TRelationship(BasePolarityRelationship, type="T"):
    """Neutral thesis relationship."""
    pass


class TPlusRelationship(BasePolarityRelationship, type="T_PLUS"):
    """Positive thesis relationship."""
    pass


class TMinusRelationship(BasePolarityRelationship, type="T_MINUS"):
    """Negative thesis relationship."""
    pass


# A-side relationships
class ARelationship(BasePolarityRelationship, type="A"):
    """Neutral antithesis relationship."""
    pass


class APlusRelationship(BasePolarityRelationship, type="A_PLUS"):
    """Positive antithesis relationship."""
    pass


class AMinusRelationship(BasePolarityRelationship, type="A_MINUS"):
    """Negative antithesis relationship."""
    pass


# S-side relationships
class SPlusRelationship(BasePolarityRelationship, type="S_PLUS"):
    """Positive synthesis relationship."""
    pass


class SMinusRelationship(BasePolarityRelationship, type="S_MINUS"):
    """Negative synthesis relationship."""
    pass
