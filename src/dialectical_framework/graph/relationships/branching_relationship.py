"""
Branching relationship for wheel/cycle/rationale/transition evolution.
"""

from __future__ import annotations

from gqlalchemy import Relationship


class BranchingRelationship(Relationship, type="BRANCHES"):
    """
    Represents a branching relationship in the dialectical evolution tree.

    Used when:
    - Wheel branches to Increment/Decrement/Refinement
    - Cycle branches to Reconsideration
    - Rationale branches to Sprout
    - Transition branches to Sprout

    The target is always an Input subclass that can have HAS_STATEMENT
    relationships to new DialecticalComponents.
    """

    pass
