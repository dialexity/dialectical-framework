"""
DialecticalComponent node with declarative relationships.

This version uses the RelationshipManager layer for clean, neomodel-like syntax.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.opposition_relationship import (
    OppositionRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.transition import Transition


class DialecticalComponent(AssessableEntity):
    """
    Represents an atomic dialectical statement or concept.

    Components are the building blocks of the dialectical framework.
    They can play different roles in different contexts:

    Core WisdomUnit positions (6):
    - T (neutral thesis), T+ (positive thesis), T- (negative thesis)
    - A (neutral antithesis), A+ (positive antithesis), A- (negative antithesis)

    Synthesis positions (on separate Synthesis node):
    - S+ (positive synthesis), S- (negative synthesis)

    Components are connected via PolarityRelationship, which stores
    the contextual alias (e.g., "T1+", "A2-") on the relationship edge.
    This allows the same component to have different positions in different contexts.
    """

    statement: str

    oppositions: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        model=OppositionRelationship,
        cardinality=(1, None)
    )

    source_of: ClassVar[RelationshipManager[Transition]] = RelationshipTo("Transition", "IS_SOURCE_OF")
    target_of: ClassVar[RelationshipManager[Transition]] = RelationshipFrom("Transition", "IS_TARGET_OF")

    def __repr__(self) -> str:
        """String representation of the component."""
        statement_preview = (
            self.statement[:47] + "..." if len(self.statement) > 50 else self.statement
        )
        return f"DialecticalComponent(uid={self.uid}, statement='{statement_preview}')"

    def __str__(self) -> str:
        """Human-readable string representation."""
        return self.statement

    def pretty(
        self, dialectical_component_label: Optional[str] = None, *, skip_explanation: bool = False
    ) -> str:
        """
        Format this component for human-readable display.

        Args:
            dialectical_component_label: Optional label to use instead of searching for alias.
                                         If not provided, will show just the statement.
            skip_explanation: If True, omit the rationale explanation even if present

        Returns:
            Formatted string like "T = Democracy\nExplanation: Representative system"

        Example:
            comp = DialecticalComponent(statement="Democracy")
            # Within WisdomUnit context
            print(comp.pretty("T1"))  # "T1 = Democracy\nExplanation: ..."
            # Standalone
            print(comp.pretty())  # "Democracy"
        """
        if dialectical_component_label:
            result = f"{dialectical_component_label} = {self.statement}"
        else:
            result = self.statement

        # Add explanation from best rationale if present and not skipped
        if not skip_explanation:
            rationales = list(self.rationales.all())
            if rationales:
                # Get first rationale (could be enhanced to select "best" by rating)
                rationale, _ = rationales[0]
                if rationale.text:
                    result = f"{result}\nExplanation: {rationale.text}"

        return result

    def get_alias(self, wisdom_unit: WisdomUnit) -> Optional[str]:
        """
        Get the alias of this component within a specific WisdomUnit's context.

        This method searches all relationship managers on the WisdomUnit (6 core positions)
        and the optional Synthesis node (S+, S-) to find where this component is connected
        and returns the alias from the edge properties.

        Args:
            wisdom_unit: The WisdomUnit to look up the alias in

        Returns:
            The alias string (e.g., "T", "T+", "A-", "S+", "S-") or None if not connected

        Example:
            comp = DialecticalComponent(statement="Democracy")
            wu = WisdomUnit(...)
            wu.t.connect(comp, properties={'alias': 'T1'})

            alias = comp.get_alias(wu)  # Returns "T1"
        """
        # Search through all 6 core position relationship managers on the wisdom unit
        rel_managers = [
            wisdom_unit.t,
            wisdom_unit.t_plus,
            wisdom_unit.t_minus,
            wisdom_unit.a,
            wisdom_unit.a_plus,
            wisdom_unit.a_minus,
        ]

        for manager in rel_managers:
            components = manager.all()  # Returns [(node, props)]

            for comp, props in components:
                # Check if this is the component we're looking for
                if comp.uid == self.uid:
                    return props.get('alias')

        # Also check synthesis if present
        synth_result = wisdom_unit.synthesis.get()
        if synth_result:
            synthesis = synth_result[0]
            # Check S+ and S- on the Synthesis node
            for manager in [synthesis.s_plus, synthesis.s_minus]:
                components = manager.all()
                for comp, props in components:
                    if comp.uid == self.uid:
                        return props.get('alias')

        return None
