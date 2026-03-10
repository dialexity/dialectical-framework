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
    Base for all polarity relationships with alias and heuristic similarity.

    The alias stores the component's contextual position (e.g., "T1", "A2+").
    Same component can have different aliases in different WisdomUnits.

    Scoring properties:
    - heuristic_similarity: How similar the component is to its taxonomy apex (0.0-1.0)

    The alias property is validated to ensure it's always a non-empty,
    non-whitespace string.
    """

    alias: str
    heuristic_similarity: Optional[float]

    def __init__(self, **data):
        """Initialize and validate alias property."""
        # Validate alias before calling parent __init__
        alias_value = data.get('alias')
        if not alias_value or not str(alias_value).strip():
            raise ValueError("alias must be a non-empty, non-whitespace string")
        super().__init__(**data)


# T and A relationships (reference points - no complementarity)
class TRelationship(PolarityRelationship, type="T"):
    """Neutral thesis relationship. T is the reference point, no complementarity."""
    pass


class ARelationship(PolarityRelationship, type="A"):
    """Neutral antithesis relationship. A is the reference point, no complementarity."""
    pass


# Pole relationships (have complementarity to T and A)
class PoleRelationship(PolarityRelationship):
    """
    Base for pole relationships with complementarity scores.

    Poles (T+, T-, A+, A-) complement the thesis and antithesis:
    - complementarity_t: K_T - how well this pole complements/supports the thesis (0.0-1.0)
    - complementarity_a: K_A - how well this pole complements/supports the antithesis (0.0-1.0)

    Scale:
    - 0.0 = Actively undermines or contradicts
    - 0.5 = Neutral, neither helps nor hurts
    - 1.0 = Strongly supports and enhances
    """

    complementarity_t: Optional[float]
    complementarity_a: Optional[float]


class TPlusRelationship(PoleRelationship, type="T_PLUS"):
    """Positive thesis pole relationship."""
    pass


class TMinusRelationship(PoleRelationship, type="T_MINUS"):
    """Negative thesis pole relationship."""
    pass


class APlusRelationship(PoleRelationship, type="A_PLUS"):
    """Positive antithesis pole relationship."""
    pass


class AMinusRelationship(PoleRelationship, type="A_MINUS"):
    """Negative antithesis pole relationship."""
    pass


# S-side relationships
class SPlusRelationship(PolarityRelationship, type="S_PLUS"):
    """Positive synthesis relationship."""
    pass


class SMinusRelationship(PolarityRelationship, type="S_MINUS"):
    """Negative synthesis relationship."""
    pass
