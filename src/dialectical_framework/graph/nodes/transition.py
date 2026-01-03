"""
Transition node for the dialectical framework.

This module provides the Transition class which represents relationships
between dialectical components (causal, convergence, transformation).
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.spiral import Spiral
    from dialectical_framework.graph.nodes.transformation import Transformation


class Transition(AssessableEntity):
    """
    Represents a transition (relationship) between dialectical components.

    Transitions capture different types of relationships between components:
    - CAUSES: Causal transitions organized in Cycles
    - CONSTRUCTIVELY_CONVERGES_TO: Synthesis convergence organized in Spirals
    - TRANSFORMS_TO: Dialectical transformations organized in Transformations

    The semantic type of transition is implicit from its container:
    - Transitions in Cycle → CAUSES
    - Transitions in Spiral → CONSTRUCTIVELY_CONVERGES_TO
    - Transitions in Transformation → TRANSFORMS_TO

    Transitions are nodes (not edges) in the graph because they:
    1. Can be assessed/scored
    2. Have their own rationales
    3. Can have estimations (probability of transition)
    4. Are organized into Cycles, Spirals, and Transformations

    Relationships:
    - source: The representative component from the source wheel segment (1:1)
    - target: The representative component from the target wheel segment (1:1)
    - cycle: The container (Cycle, Spiral, or Transformation) this transition belongs to (0:1)

    Note: Default probability fallback is handled by the scorer (TaroRank.default_transition_probability)
    from settings, not stored on individual transition nodes.
    """

    source: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        "IS_SOURCE_OF",
        cardinality=(1, 1)
    )

    target: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "IS_TARGET_OF",
        cardinality=(1, 1)
    )

    cycle: ClassVar[RelationshipManager[Cycle | Spiral | Transformation]] = RelationshipTo(
        ("Cycle", "Spiral", "Transformation"),
        "BELONGS_TO_CYCLE",
        cardinality=(0, 1)
    )

    derived_statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "HAS_STATEMENT",
        cardinality=(0, None)
    )

    def __repr__(self) -> str:
        """String representation of the transition."""
        return f"Transition(uid={self.uid})"
