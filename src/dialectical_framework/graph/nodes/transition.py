"""
Transition node for the dialectical framework.

This module provides the Transition class which represents relationships
between dialectical components (causal, convergence, transformation).
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.spiral import Spiral


class Transition(AssessableEntity):
    """
    Represents a transition (relationship) between dialectical components.

    Transitions capture different types of relationships between components:
    - CAUSES: Causal relationship (A causes B)
    - CONSTRUCTIVELY_CONVERGES_TO: Synthesis convergence (A + B → S)
    - TRANSFORMS_TO: Dialectical transformation

    Transitions are nodes (not edges) in the graph because they:
    1. Can be assessed/scored
    2. Have their own rationales
    3. Can have estimations (probability of transition)
    4. Are organized into Cycles and Spirals
    """

    default_transition_probability: Optional[float] = None

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

    cycle: ClassVar[RelationshipManager[Cycle | Spiral]] = RelationshipTo(
        ("Cycle", "Spiral"),
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
        prob_str = (
            f"{self.default_transition_probability:.3f}"
            if self.default_transition_probability is not None
            else "None"
        )
        return f"Transition(uid={self.uid}, probability={prob_str})"
