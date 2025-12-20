"""
Cycle node for the dialectical framework.

This module provides the Cycle class which represents causal cycles
composed of transitions between dialectical components.
"""

from __future__ import annotations

from typing import ClassVar, Optional

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipManager


class Cycle(AssessableEntity):
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

    causality_type: Optional[str] = None

    # Declarative relationships
    transitions: ClassVar[RelationshipManager] = RelationshipFrom(
        "Transition",
        "BELONGS_TO_CYCLE",
        cardinality=(2, None)  # At least two transitions to form a cycle
    )

    # Note: Wheel relationship is defined on Wheel side (t_cycle, ta_cycle)
    # Use get_wheel() method to query which wheel this cycle belongs to

    def get_wheel(self, db=None):
        """
        Get the wheel this cycle belongs to and its role (T or TA).

        Args:
            db: Database connection (uses get_db() if not provided)

        Returns:
            Tuple of (wheel, role) where role is "T" or "TA", or None if not assigned

        Example:
            wheel, role = cycle.get_wheel(db)
            if role == "T":
                print("This is the T-cycle (thesis components only)")
            elif role == "TA":
                print("This is the TA-cycle (thesis + antithesis, includes blindspots)")
        """
        if self._id is None:
            return None

        if db is None:
            from dialectical_framework.graph import get_db
            db = get_db()

        query = """
        MATCH (c:Cycle)-[r:IS_T_CYCLE_OF|IS_TA_CYCLE_OF]->(w:Wheel)
        WHERE id(c) = $cycle_id
        RETURN w, type(r) as role
        """
        result = list(db.execute_and_fetch(query, {"cycle_id": self._id}))
        if result:
            wheel = result[0]["w"]
            role = "T" if result[0]["role"] == "IS_T_CYCLE_OF" else "TA"
            return (wheel, role)
        return None

    def __repr__(self) -> str:
        """String representation of the cycle."""
        return f"Cycle(uid={self.uid}, type={self.causality_type})"
