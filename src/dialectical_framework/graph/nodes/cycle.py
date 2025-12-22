"""
Cycle node for the dialectical framework.

This module provides the Cycle class which represents causal cycles
composed of transitions between dialectical components.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING, Union

from dependency_injector.wiring import inject, Provide

from dialectical_framework.enums.di import DI
from dialectical_framework.enums.causality_type import CausalityType
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager
from dialectical_framework.graph.mixins.sequence_topology_mixin import SequenceTopologyMixin
from dialectical_framework.graph.utils.order_transitions import order_transitions

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from gqlalchemy import Memgraph
    from neo4j import Neo4j


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

    # Note: Wheel relationship is defined on Wheel side (t_cycle, ta_cycle)
    # Use get_wheel() method to query which wheel this cycle belongs to

    @property
    def transitions_ordered(self) -> list[Transition]:
        """
        Get transitions in cycle order by following source->target chain.

        Returns:
            List of Transition nodes in cycle order, or empty list if no transitions
        """
        all_transitions = [trans for trans, _ in self.transitions.all()]
        return order_transitions(all_transitions)

    @inject
    def get_wheel(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Wheel | None:
        """
        Get the wheel this cycle belongs to.

        Args:
            graph_db: Database connection (injected via DI)

        Returns:
            Wheel instance or None if not assigned to a wheel

        Example:
            wheel = cycle.get_wheel()
            if wheel:
                print(f"Cycle belongs to wheel {wheel.uid}")
        """
        if self._id is None:
            return None

        query = """
        MATCH (c:Cycle)-[r:IS_T_CYCLE_OF|IS_TA_CYCLE_OF]->(w:Wheel)
        WHERE id(c) = $cycle_id
        RETURN w
        """
        result = list(graph_db.execute_and_fetch(query, {"cycle_id": self._id}))
        if result:
            return result[0]["w"]
        return None

    def __repr__(self) -> str:
        """String representation of the cycle."""
        return f"Cycle(uid={self.uid}, type={self.causality_type})"
