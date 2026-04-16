"""
Relationship model for opposite-direction Cycles and Wheels.

Links a Cycle (or Wheel) to its reverse-direction counterpart.
For example, T1 → T2 → T3 and T1 → T3 → T2 are opposite directions.
"""

from __future__ import annotations

from gqlalchemy import Relationship


class OppositeDirectionRelationship(Relationship, type="OPPOSITE_DIRECTION"):
    """
    Symmetric relationship linking a Cycle or Wheel to its reverse-direction counterpart.

    This is a bidirectional relationship: if A is the opposite direction of B,
    then B is the opposite direction of A.
    """

    pass
