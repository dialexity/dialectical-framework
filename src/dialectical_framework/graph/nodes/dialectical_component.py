"""
DialecticalComponent node with declarative relationships.

This version uses the RelationshipManager layer for clean, neomodel-like syntax.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, Union, TYPE_CHECKING

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
    from dialectical_framework.graph.growth.input import Input
    from dialectical_framework.graph.nodes.rationale import Rationale


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

    # Reverse relationship - find the source node that created this statement
    # HAS_STATEMENT can come from different node types:
    # - Input: statement extracted from external source
    # - Transition: statement derived from dialectical transition
    # - Rationale: key point extracted from rationale
    # Each statement has at most one source (same text in different sources = different nodes)
    input: ClassVar[RelationshipManager[Union[Input, Transition, Rationale]]] = RelationshipFrom(
        ("Input", "Transition", "Rationale"),  # Match any of these node types
        "HAS_STATEMENT",
        cardinality=(0, 1),  # Zero (self-originated) or one source
    )

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
        [mode][:width]

        Mode (optional):
            "short" - Just the statement (no explanation)
            "long"  - Statement + explanation from the best rationale (default)
            ""      - Empty spec defaults to "long"

        Width (optional, only for "short" mode):
            :N - Truncate statement to N characters and add "..." if truncated
            Example: "short:30" - Statement truncated to 30 chars

        Examples:
        ---------
        f"{comp}"          - Long format (statement + explanation)
        f"{comp:long}"     - Long format (explicit)
        f"{comp:short}"    - Short format (statement only)
        f"{comp:short:30}" - Short format, truncated to 30 chars with "..."

        Usage with label:
        -----------------
        f"{label} = {comp:long}"     - "T = Democracy\nExplanation: Representative system"
        f"{label} = {comp:short}"    - "T = Democracy"
        f"{label} = {comp:short:30}" - "T = Democracy"

        Returns:
            Formatted string
        """
        # Parse format spec: [mode][:width]
        if ":" in format_spec:
            mode, width_str = format_spec.split(":", 1)
            try:
                width = int(width_str)
            except ValueError:
                width = None
        else:
            mode = format_spec
            width = None

        # Default to "long" if no mode provided
        if not mode:
            mode = "long"

        # Start with statement
        result = self.statement

        # Apply width truncation for short mode
        if mode == "short" and width is not None:
            if len(result) > width:
                result = result[:width] + "..."

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

    def get_alias(self, wisdom_unit: WisdomUnit) -> str:
        """
        Get the alias of this component within a specific WisdomUnit's context.

        This method searches all relationship managers on the WisdomUnit (6 core positions)
        and the optional Synthesis node (S+, S-) to find where this component is connected
        and returns the alias from the edge properties. If no custom alias is set, returns
        the position constant as the default alias.

        Args:
            wisdom_unit: The WisdomUnit to look up the alias in

        Returns:
            The alias string (e.g., "T1", "A2+") or position constant (e.g., "T", "T+", "A-")

        Raises:
            ValueError: If component is not connected to the wisdom unit

        Example:
            from dialectical_framework.graph.relationships.polarity_relationship import TRelationship
            comp = DialecticalComponent(statement="Democracy")
            wu = WisdomUnit(...)
            wu.t.connect(comp, relationship=TRelationship(alias='T1'))

            alias = comp.get_alias(wu)  # Returns "T1"

            # If alias not set on relationship:
            wu2.t.connect(comp2, relationship=TRelationship(alias=None))
            alias2 = comp2.get_alias(wu2)  # Returns "T" (position constant)
        """
        # Get position first to use as fallback
        position = self.get_position(wisdom_unit)
        if not position:
            raise ValueError(f"Component {self.uid} is not connected to WisdomUnit {wisdom_unit.uid}")

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
                        # Return custom alias if set, otherwise position constant
                        return rel.alias if rel.alias else position
                    return position  # Non-polarity relationship, use position

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
                            # Return custom alias if set, otherwise position constant
                            return rel.alias if rel.alias else position
                        return position  # Non-polarity relationship, use position

        # Should not reach here since get_position() already validated connection
        return position

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
