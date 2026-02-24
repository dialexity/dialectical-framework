"""
Polarity relationships for connecting DialecticalComponents to WisdomUnits.

Each polarity position has its own relationship type for fine-grained querying,
but all store the contextual alias property.
"""

from __future__ import annotations

from typing import Optional

from dialectical_framework.graph.relationships.immutable_structure import IdentityRelationship


# Base class for all polarity relationships
class PolarityRelationship(IdentityRelationship):
    """
    Base for all polarity relationships with alias property.

    The alias stores the component's contextual position (e.g., "T1", "A2+").
    Same component can have different aliases in different WisdomUnits.

    Use isinstance checks to safely access .alias:
        if isinstance(rel, PolarityRelationship):
            alias = rel.alias  # Direct access, fully typed

    The alias property is validated to ensure it's always a non-empty,
    non-whitespace string.
    """

    alias: str

    def __init__(self, **data):
        """Initialize and validate alias property."""
        # Validate alias before calling parent __init__
        alias_value = data.get('alias')
        if not alias_value or not str(alias_value).strip():
            raise ValueError("alias must be a non-empty, non-whitespace string")
        super().__init__(**data)


# T-side relationships
class TRelationship(PolarityRelationship, type="T"):
    """Neutral thesis relationship."""
    pass


class TPlusRelationship(PolarityRelationship, type="T_PLUS"):
    """Positive thesis relationship."""
    pass


class TMinusRelationship(PolarityRelationship, type="T_MINUS"):
    """Negative thesis relationship."""
    pass


# A-side relationships
class ARelationship(PolarityRelationship, type="A"):
    """Neutral antithesis relationship."""
    heuristic_similarity: Optional[float]


class APlusRelationship(PolarityRelationship, type="A_PLUS"):
    """Positive antithesis relationship."""
    pass


class AMinusRelationship(PolarityRelationship, type="A_MINUS"):
    """Negative antithesis relationship."""
    pass


# S-side relationships
class SPlusRelationship(PolarityRelationship, type="S_PLUS"):
    """Positive synthesis relationship."""
    pass


class SMinusRelationship(PolarityRelationship, type="S_MINUS"):
    """Negative synthesis relationship."""
    pass
