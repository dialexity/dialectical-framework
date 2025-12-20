"""
Spiral node for the dialectical framework.

This module provides the Spiral class which represents transformational
spirals composed of transformation transitions.
"""

from __future__ import annotations

from typing import ClassVar

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager


class Spiral(AssessableEntity):
    """
    Represents a transformational spiral in the dialectical framework.

    A Spiral is an analytical interpretation - a directed graph of transitions
    that captures dialectical evolution and synthesis pathways. Spirals are
    "drawn on" a wheel to show transformational relationships that lead to synthesis.

    Unlike Cycles which track causal relationships between components, Spirals
    track transformational relationships that represent upward movement in
    dialectical reasoning, where thesis and antithesis are transformed through
    synthesis into higher-order understanding.

    Relationship to Wheel:
    - A wheel can have one primary/canonical spiral (wheel.spiral)
    - Alternative spiral interpretations can also reference the same wheel
    - Spirals can exist independently or be created after the wheel
    """

    transitions: ClassVar[RelationshipManager] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, None)  # At least two transitions to form a spiral
    )

    wheel: ClassVar[RelationshipManager] = RelationshipTo(
        "Wheel",
        "IS_SPIRAL_OF",
        cardinality=(0, 1)  # Optional - spiral may analyze a wheel
    )

    def __repr__(self) -> str:
        """String representation of the spiral."""
        return f"Spiral(uid={self.uid})"
