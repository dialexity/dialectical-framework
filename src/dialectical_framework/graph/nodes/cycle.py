"""
Cycle node for the dialectical framework.

This module provides the Cycle class which represents causal cycles
composed of transitions between dialectical components.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.has_cycle_relationship import (
    HasCycleRelationship,
)
from dialectical_framework.graph.relationships.has_wheel_relationship import (
    HasWheelRelationship,
)
from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.nexus import Nexus


class Cycle(IntentMixin, CircularTopologyMixin, AssessableEntity, label="Cycle"):
    """
    Represents a causal arrangement of WisdomUnits from a Nexus.

    A Cycle is an analytical interpretation - a directed graph of transitions
    between components that forms a closed loop. Cycles capture causal
    relationships and feedback loops discovered in the dialectical system.

    The intent field captures the dynamics/causality type of this cycle
    (e.g., "preset:realistic", "preset:desirable", "preset:feasible", "preset:balanced").

    Cycles always flow clockwise through the components.

    Hierarchy:
        Nexus (pool of WUs) → Cycle (arrangement) → Wheel (detailed implementation)

    Relationships:
    - Cycle belongs to exactly one Nexus (source of WisdomUnits)
    - Cycle can have multiple Wheels (different detailed arrangements)
    - Use get_nexus() to find the source Nexus
    - Use wheels.all() to find associated Wheels
    """

    # Note: transitions relationship is inherited from CircularTopologyMixin as _transitions
    # Access via .transitions property which returns ordered list

    # Source Nexus (where WUs come from)
    # Parent→child: Nexus has this Cycle
    nexus: ClassVar[RelationshipManager[Nexus]] = RelationshipFrom(
        "Nexus",
        model=HasCycleRelationship,
        cardinality=(1, 1)  # Exactly one source Nexus
    )

    # Wheels that implement this cycle's arrangement
    # Parent→child: Cycle has Wheels
    wheels: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        model=HasWheelRelationship,
        cardinality=(1, None)  # At least one wheel per cycle
    )

    def get_nexus(self) -> Nexus | None:
        """
        Get the source Nexus for this cycle.

        Returns:
            Nexus instance or None if not connected

        Example:
            nexus = cycle.get_nexus()
            if nexus:
                print(f"Cycle derived from nexus with {nexus.wisdom_units.count()} WUs")
        """
        result = self.nexus.get()
        if result:
            return result[0]
        return None

    def __format__(self, format_spec: str) -> str:
        """
        Format this Cycle using Python's format string protocol.

        Extends CircularTopologyMixin with a "verbose" mode that shows intent and rationales.

        Format Specifications:
        ----------------------
        "" or "aliases"   - Chains aliases like "T1 → T2 → T3 → T1..." (inherited from mixin)
        "statements"      - Uses component statements instead of aliases (inherited from mixin)
        "explicit"        - Combines both: "T1 (statement) → T2 (statement) → ..." (inherited from mixin)
        "verbose"         - Shows intent, sequence, and rationales

        Examples:
        ---------
        f"{cycle}"              - Default aliases: "T1 → A1 → T2 → T1..."
        f"{cycle:explicit}"     - Explicit: "T1 (Democracy) → A1 (Fear) → T2 (Courage) → T1..."
        f"{cycle:verbose}"      - Verbose: "REALISTIC: T1 → A1 → T2 → T1...\nRationale: ..."

        Returns:
            Formatted string representing the cycle
        """
        if format_spec == "verbose":
            # Verbose mode: show intent + sequence + rationales
            result = ""

            # Add intent if present
            if self.intent:
                result = f"{self.intent} cycle: "
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
        return f"Cycle(uid={self.uid}, intent={self.intent})"
