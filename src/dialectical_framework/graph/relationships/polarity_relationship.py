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
    - complementarity: Average of K_T and K_A (calculated property)

    Scale:
    - 0.0 = Actively undermines or contradicts
    - 0.5 = Neutral, neither helps nor hurts
    - 1.0 = Strongly supports and enhances
    """

    complementarity_t: Optional[float]
    complementarity_a: Optional[float]

    @property
    def complementarity_s(self) -> Optional[float]:
        """Average complementarity: (K_T + K_A) / 2."""
        if self.complementarity_t is None or self.complementarity_a is None:
            return None
        return (self.complementarity_t + self.complementarity_a) / 2


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


# Transition pole relationships for Transformation (Action-Reflection structure)
# These are about insight and proactiveness, not complementarity
class TransitionPoleRelationship(PolarityRelationship):
    """
    Base for Ac/Re transition relationships with insight and proactiveness scores.

    Transition poles represent navigation paths through the dialectical tension:
    - insight: How much understanding/clarity the transition provides (0.0-1.0)
    - proactiveness: How actionable/practical the transition is (0.0-1.0)

    Scale:
    - 0.0 = No insight/proactiveness
    - 0.5 = Moderate
    - 1.0 = High insight/proactiveness
    """

    insight: Optional[float]
    proactiveness: Optional[float]


# Neutral positions (reference points - no insight/proactiveness)
class AcRelationship(PolarityRelationship, type="AC"):
    """Action relationship: T → A transition. Reference point, no scoring properties."""
    pass


class ReRelationship(PolarityRelationship, type="RE"):
    """Reflection relationship: A → T transition. Reference point, no scoring properties."""
    pass


# Ac/Re pole positions (have insight/proactiveness)
class AcPlusRelationship(TransitionPoleRelationship, type="AC_PLUS"):
    """Positive action relationship: T- → A+ transition."""
    pass


class AcMinusRelationship(TransitionPoleRelationship, type="AC_MINUS"):
    """Negative action relationship: T+ → A- transition."""
    pass


class RePlusRelationship(TransitionPoleRelationship, type="RE_PLUS"):
    """Positive reflection relationship: A- → T+ transition."""
    pass


class ReMinusRelationship(TransitionPoleRelationship, type="RE_MINUS"):
    """Negative reflection relationship: A+ → T- transition."""
    pass
