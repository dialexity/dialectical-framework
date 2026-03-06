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
    Base for all polarity relationships with alias and scoring properties.

    The alias stores the component's contextual position (e.g., "T1", "A2+").
    Same component can have different aliases in different WisdomUnits.

    Scoring properties (all Optional[float], 0.0-1.0):
    - heuristic_similarity: How similar the component is to its taxonomy apex
    - complementarity_t: K_T - how well this component complements the thesis
    - complementarity_a: K_A - how well this component complements the antithesis

    Use isinstance checks to safely access properties:
        if isinstance(rel, PolarityRelationship):
            alias = rel.alias  # Direct access, fully typed
            hs = rel.heuristic_similarity

    The alias property is validated to ensure it's always a non-empty,
    non-whitespace string.
    """

    alias: str
    heuristic_similarity: Optional[float]
    complementarity_t: Optional[float]
    complementarity_a: Optional[float]

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
    pass


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
