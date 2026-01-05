"""
Cycle node for the dialectical framework.

This module provides the Cycle class which represents causal cycles
composed of transitions between dialectical components.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel


class Cycle(CircularTopologyMixin, AssessableEntity):
    """
    Represents a causal cycle in the dialectical framework.

    A Cycle is an analytical interpretation - a directed graph of transitions
    between components that forms a closed loop. Cycles capture causal
    relationships and feedback loops discovered in the dialectical system.

    Cycles are "drawn on" a wheel to show different causal patterns:

    Types of cycles:
    - T-cycle: Causal loop through thesis components only
    - TA-cycle: Causal loop including both thesis and antithesis (with blindspots)
    - REALISTIC: Current/actual state of affairs
    - DESIRABLE: Ideal/preferred outcomes
    - FEASIBLE: Achievable intermediate states
    - BALANCED: Optimized balance of concerns

    Cycles always flow clockwise through the components.

    Relationship to Wheel:
    - A wheel can have primary/canonical cycles (wheel.t_cycle, wheel.ta_cycle)
    - Alternative cycle interpretations can also analyze the same wheel
    - Use get_wheel() to find which wheel this cycle analyzes
    """

    causality_type: Optional[CausalityType] = None

    # Declarative relationships - ClassVar required for GQLAlchemy metaclass
    transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, None)  # At least two transitions to form a cycle
    )

    # Reverse relationships to Wheel (private - use get_wheel() instead)
    # Cycle can be either t_cycle or ta_cycle of a wheel
    _wheel_as_t: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        "IS_T_CYCLE_OF",
        cardinality=(0, 1)
    )

    _wheel_as_ta: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        "IS_TA_CYCLE_OF",
        cardinality=(0, 1)
    )

    def get_wheel(self) -> Wheel | None:
        """
        Get the wheel this cycle belongs to.

        Returns:
            Wheel instance or None if not assigned to a wheel

        Example:
            wheel = cycle.get_wheel()
            if wheel:
                print(f"Cycle belongs to wheel {wheel.uid}")
        """
        # Check if this is a t_cycle
        t_result = self._wheel_as_t.get()
        if t_result:
            return t_result[0]

        # Check if this is a ta_cycle
        ta_result = self._wheel_as_ta.get()
        if ta_result:
            return ta_result[0]

        return None

    def __format__(self, format_spec: str) -> str:
        """
        Format this Cycle using Python's format string protocol.

        Extends CircularTopologyMixin with a "verbose" mode that shows causality type and rationales.

        Format Specifications:
        ----------------------
        "" or "aliases"   - Chains aliases like "T1 → T2 → T3 → T1..." (inherited from mixin)
        "statements"      - Uses component statements instead of aliases (inherited from mixin)
        "explicit"        - Combines both: "T1 (statement) → T2 (statement) → ..." (inherited from mixin)
        "verbose"         - Shows causality type, sequence, and rationales

        Examples:
        ---------
        f"{cycle}"              - Default aliases: "T1 → A1 → T2 → T1..."
        f"{cycle:explicit}"     - Explicit: "T1 (Democracy) → A1 (Fear) → T2 (Courage) → T1..."
        f"{cycle:verbose}"      - Verbose: "REALISTIC: T1 → A1 → T2 → T1...\nRationale: ..."

        Returns:
            Formatted string representing the cycle
        """
        if format_spec == "verbose":
            # Verbose mode: show causality_type + sequence + rationales
            result = ""

            # Add causality type if present
            if self.causality_type:
                result = f"{self.causality_type.name} cycle: "
            else:
                result = "Cycle: "

            # Add sequence using aliases mode from parent
            sequence = super().__format__("aliases")
            result += sequence
            result = f"{result}\n{super().__format__('explicit')}"

            # Add rationales
            rationales = list(self.rationales.all())
            if rationales:
                # Multiple rationales - number them
                if len(rationales) > 1:
                    explanations = []
                    for idx, (rationale, _) in enumerate(rationales, 1):
                        if rationale.text:
                            explanations.append(f"Rationale {idx}: {rationale.text}")
                    if explanations:
                        result = f"{result}\n" + "\n".join(explanations)
                # Single rationale - no number
                else:
                    rationale, _ = rationales[0]
                    if rationale.text:
                        result = f"{result}\nRationale: {rationale.text}"
            else:
                # No rationales
                result = f"{result}\nRationale: N/A"

            return result
        else:
            # All other modes: delegate to parent CircularTopologyMixin
            return super().__format__(format_spec)

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def __repr__(self) -> str:
        """Debug representation of the cycle."""
        return f"Cycle(uid={self.uid}, type={self.causality_type})"
