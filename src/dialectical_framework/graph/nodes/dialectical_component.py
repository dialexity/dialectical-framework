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
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
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

    def __format__(self, format_spec: str) -> str:
        """
        Format this component using Python's format string protocol.

        Format Specifications:
        ----------------------
        "short" - Just the statement (no explanation)
        "long"  - Statement + explanation from best rationale (default)
        ""      - Empty spec defaults to "long"

        Examples:
        ---------
        f"{comp}"        - Long format (statement + explanation)
        f"{comp:long}"   - Long format (explicit)
        f"{comp:short}"  - Short format (statement only)

        Usage with label:
        -----------------
        f"{label} = {comp:long}"   - "T = Democracy\nExplanation: Representative system"
        f"{label} = {comp:short}"  - "T = Democracy"

        Returns:
            Formatted string
        """
        # Default to "long" if no spec provided
        mode = format_spec if format_spec else "long"

        # Start with statement
        result = self.statement

        # Add explanation if in long mode
        if mode == "long":
            rationales = list(self.rationales.all())
            if rationales:
                # Multiple rationales - number them
                if len(rationales) > 1:
                    explanations = []
                    for idx, (rationale, _) in enumerate(rationales, 1):
                        if rationale.text:
                            explanations.append(f"Explanation {idx}: {rationale.text}")
                    if explanations:
                        result = f"{result}\n" + "\n".join(explanations)
                # Single rationale - no number
                else:
                    rationale, _ = rationales[0]
                    if rationale.text:
                        result = f"{result}\nExplanation: {rationale.text}"
            else:
                # No rationales
                result = f"{result}\nExplanation: N/A"

        return result

    def __str__(self) -> str:
        """Human-readable string representation (defaults to long format)."""
        return self.__format__("")

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
            from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
            comp = DialecticalComponent(statement="Democracy")
            wu = WisdomUnit(...)
            wu.t.connect(comp, relationship=TRelationship(alias='T1'))

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
            components = manager.all()  # Returns [(node, rel)]

            for comp, rel in components:
                # Check if this is the component we're looking for
                if comp.uid == self.uid:
                    # Use isinstance for type-safe property access
                    if isinstance(rel, PolarityRelationship):
                        return rel.alias  # Direct access, fully typed
                    return None  # Non-polarity relationship

        # Also check synthesis if present
        synth_result = wisdom_unit.synthesis.get()
        if synth_result:
            synthesis = synth_result[0]
            # Check S+ and S- on the Synthesis node
            for manager in [synthesis.s_plus, synthesis.s_minus]:
                components = manager.all()
                for comp, rel in components:
                    if comp.uid == self.uid:
                        # Use isinstance for type-safe property access
                        if isinstance(rel, PolarityRelationship):
                            return rel.alias  # Direct access, fully typed
                        return None  # Non-polarity relationship

        return None

    def get_position(self, wisdom_unit: WisdomUnit) -> Optional[str]:
        """
        Get the position name of this component within a specific WisdomUnit's context.

        This method searches all relationship managers on the WisdomUnit (6 core positions)
        and the optional Synthesis node (S+, S-) to find where this component is connected
        and returns the position constant.

        Args:
            wisdom_unit: The WisdomUnit to look up the position in

        Returns:
            The position constant (e.g., "T", "T+", "A-", "S+", "S-") or None if not connected

        Example:
            from dialectical_framework.graph.nodes.wisdom_unit import POSITION_T, POSITION_T_PLUS
            comp = DialecticalComponent(statement="Democracy")
            wu = WisdomUnit(...)
            wu.t.connect(comp, relationship=TRelationship(alias='T1'))

            position = comp.get_position(wu)  # Returns "T" (POSITION_T)

            comp2 = DialecticalComponent(statement="Trust")
            wu.t_plus.connect(comp2, relationship=TPlusRelationship(alias='T1+'))
            position2 = comp2.get_position(wu)  # Returns "T+" (POSITION_T_PLUS)
        """
        from dialectical_framework.graph.nodes.wisdom_unit import (
            POSITION_T, POSITION_T_PLUS, POSITION_T_MINUS,
            POSITION_A, POSITION_A_PLUS, POSITION_A_MINUS,
            POSITION_S_PLUS, POSITION_S_MINUS
        )

        # Search through all 6 core position relationship managers on the wisdom unit
        positions = [
            (POSITION_T, wisdom_unit.t),
            (POSITION_T_PLUS, wisdom_unit.t_plus),
            (POSITION_T_MINUS, wisdom_unit.t_minus),
            (POSITION_A, wisdom_unit.a),
            (POSITION_A_PLUS, wisdom_unit.a_plus),
            (POSITION_A_MINUS, wisdom_unit.a_minus),
        ]

        for position_name, manager in positions:
            components = manager.all()  # Returns [(node, rel)]

            for comp, rel in components:
                # Check if this is the component we're looking for
                if comp.uid == self.uid:
                    return position_name

        # Also check synthesis if present
        synth_result = wisdom_unit.synthesis.get()
        if synth_result:
            synthesis = synth_result[0]
            # Check S+ and S- on the Synthesis node
            synth_positions = [
                (POSITION_S_PLUS, synthesis.s_plus),
                (POSITION_S_MINUS, synthesis.s_minus),
            ]
            for position_name, manager in synth_positions:
                components = manager.all()
                for comp, rel in components:
                    if comp.uid == self.uid:
                        return position_name

        return None
