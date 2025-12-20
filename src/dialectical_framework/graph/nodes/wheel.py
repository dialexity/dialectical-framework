"""
Wheel node for the dialectical framework.

This module provides the Wheel class which represents the top-level container
for a complete dialectical system.
"""

from __future__ import annotations

from typing import ClassVar

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager


class Wheel(AssessableEntity):
    """
    Represents a complete dialectical system (wheel metaphor).

    A Wheel is fundamentally a structured collection of WisdomUnits arranged
    in a specific configuration. The wheel represents the "raw dialectical material."

    Cycles and spirals are analytical interpretations created on top of the wheel:
    - They can be discovered/created after the wheel exists
    - A wheel can have canonical (primary) cycles/spirals
    - Alternative analyses can also reference the same wheel

    The wheel metaphor represents the circular, iterative nature of
    dialectical reasoning where thesis and antithesis are arranged in segments.

    Properties:
    - order: Number of wisdom units (computed from relationships)
    - degree: Total segments = order × 2 (computed)
    """

    # Declarative relationships
    wisdom_units: ClassVar[RelationshipManager] = RelationshipFrom(
        "WisdomUnit",
        "BELONGS_TO_WHEEL",
        cardinality=(1, None)  # One or more wisdom units
    )

    # Canonical/primary analytical structures (optional)
    # These represent the "authoritative" interpretation when one exists
    t_cycle: ClassVar[RelationshipManager] = RelationshipFrom(
        "Cycle",
        "IS_T_CYCLE_OF",
        cardinality=(0, 1)  # Zero or one (can be analyzed later)
    )

    ta_cycle: ClassVar[RelationshipManager] = RelationshipFrom(
        "Cycle",
        "IS_TA_CYCLE_OF",
        cardinality=(0, 1)  # Zero or one (can be analyzed later)
    )

    spirals: ClassVar[RelationshipManager] = RelationshipFrom(
        "Spiral",
        "IS_SPIRAL_OF",
        cardinality=(0, None)  # Zero or more (includes Transformations)
    )

    def __repr__(self) -> str:
        """String representation of the wheel."""
        return f"Wheel(uid={self.uid})"
