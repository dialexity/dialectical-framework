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
from dialectical_framework.graph.mixins.sequence_topology_mixin import SequenceTopologyMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel


class Cycle(SequenceTopologyMixin, AssessableEntity):
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

    def __repr__(self) -> str:
        """String representation of the cycle."""
        return f"Cycle(uid={self.uid}, type={self.causality_type})"
