"""
Cycle node for the dialectical framework.

This module provides the Cycle class which represents the T-cycle:
an ordered sequence of Perspectives defining abstract thesis causality.

A Cycle captures the order in which theses relate causally (T1 → T2 → T3).
Multiple Wheels can share the same T-cycle with different flip configurations.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipBoth, RelationshipManager
from dialectical_framework.graph.relationships.has_wheel_relationship import (
    HasWheelRelationship,
)
from dialectical_framework.graph.relationships.opposite_direction_relationship import (
    OppositeDirectionRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.perspective import Perspective


class Cycle(IntentMixin, AssessableEntity, label="Cycle"):
    """
    Represents the T-cycle: an ordered sequence of Perspectives.

    A Cycle defines abstract thesis causality - the order in which theses
    relate to each other (T1 → T2 → T3). This is the "pool" of Perspectives
    in a specific causal arrangement.

    The intent field captures the dynamics/causality type of this cycle
    (e.g., "preset:realistic", "preset:desirable", "preset:feasible", "preset:balanced").

    Multiple Wheels can implement the same Cycle with different flip configurations,
    where each PP can have its T and A sides swapped.

    Hierarchy:
        Perspective → Cycle (ordered pool + intent) → Wheel (flips + transitions)

    Relationships:
    - Cycle contains ordered PP hashes (stored as field, not relationships)
    - Cycle can have multiple Wheels (different flip configurations)
    - Use perspectives property to get PP instances
    - Use wheels.all() to find associated Wheels

    Example:
        # Create PPs
        pp1.commit()
        pp2.commit()
        pp3.commit()

        # Create cycle with ordered PPs
        cycle = Cycle(intent="preset:balanced")
        cycle.set_perspectives([pp1, pp2, pp3])  # Order matters
        cycle.commit()

        # Create wheel with transitions
        wheel = Wheel()
        cycle.wheels.connect(wheel)
        wheel.save()
        # Add transitions that define the T-A arrangement
        # Polarity (T-first vs A-first) is derived from transitions
        # ... add transitions ...
        wheel.commit()
    """

    # Ordered list of Perspective hashes - defines the T-cycle order
    perspective_hashes: list[str] = []

    # Transient refs for setting PPs before commit (not persisted)
    _pp_refs: Optional[list[Perspective]] = None

    # Wheels that implement this cycle's arrangement
    # Parent→child: Cycle has Wheels
    wheels: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        model=HasWheelRelationship,
        cardinality=(0, None)  # Zero or more wheels can implement this cycle
    )

    # Opposite-direction counterpart (symmetric)
    # Links cycles that are circular reverses of each other
    opposite_direction: ClassVar[RelationshipManager[Cycle]] = RelationshipBoth(
        "Cycle",
        model=OppositeDirectionRelationship,
    )

    def set_perspectives(self, perspectives: list[Perspective]) -> Cycle:
        """
        Set the ordered list of Perspectives for this cycle.

        Must be called before commit(). All PPs must be committed.
        Order determines the T-cycle: T1 → T2 → T3 → T1...

        Args:
            perspectives: Ordered list of committed Perspectives

        Returns:
            Self for chaining

        Raises:
            ValueError: If any PP is not committed
        """
        hashes = []
        for pp in perspectives:
            if not pp.is_committed:
                raise ValueError(
                    "Perspective must be committed before adding to Cycle"
                )
            hashes.append(pp.hash)

        self.perspective_hashes = hashes
        self._pp_refs = perspectives  # Keep refs for potential use
        return self

    @property
    def perspectives(self) -> list[Perspective]:
        """
        Get the Perspectives in cycle order.

        Returns PP instances by looking up their hashes.

        Returns:
            List of Perspective instances in T-cycle order
        """
        if not self.perspective_hashes:
            return []

        from dialectical_framework.graph.repositories.node_repository import NodeRepository
        repo = NodeRepository()

        result = []
        for pp_hash in self.perspective_hashes:
            pp = repo.find_by_hash(pp_hash)
            if pp:
                result.append(pp)
        return result

    @property
    def perspective_count(self) -> int:
        """Number of Perspectives in this cycle."""
        return len(self.perspective_hashes)

    @property
    def dialectical_components(self) -> list:
        """
        Get the dialectical components (T components) for this cycle.

        Returns the thesis components from each Perspective in cycle order.
        Used by CausalitySequencer.estimate() for building estimation prompts.

        Returns:
            List of DialecticalComponent instances (T components in order)
        """
        from dialectical_framework.graph.nodes.dialectical_component import (
            DialecticalComponent,
        )

        components: list[DialecticalComponent] = []
        for pp in self.perspectives:
            t_result = pp.t.get()
            if t_result:
                components.append(t_result[0])
        return components

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Cycle.

        Parts: ordered PP hashes (NOT sorted - order matters for T-cycle).
        The intent is added separately by BaseNode.compute_hash().

        Returns:
            List of strings: [pp_hash1, pp_hash2, pp_hash3, ...]

        Raises:
            ValueError: If no Perspectives are set
        """
        if not self.perspective_hashes:
            raise ValueError(
                "Cycle must have Perspectives set before computing structure hash. "
                "Use set_perspectives()."
            )

        # Return hashes in order (NOT sorted - order defines the T-cycle)
        return list(self.perspective_hashes)

    def __format__(self, format_spec: str) -> str:
        """
        Format this Cycle using Python's format string protocol.

        Format Specifications:
        ----------------------
        "" or "aliases"   - Shows T-cycle: "T1 → T2 → T3 → T1..."
        "verbose"         - Shows intent, sequence, and rationales

        Examples:
        ---------
        f"{cycle}"              - Default: "T1 → T2 → T3 → T1..."
        f"{cycle:verbose}"      - Verbose: "balanced cycle: T1 → T2 → T3...\nRationale: ..."

        Returns:
            Formatted string representing the cycle
        """
        # Build T-cycle sequence from PP order
        pps = self.perspectives
        if not pps:
            sequence = "[no Perspectives]"
        else:
            # T-cycle shows thesis positions: T1 → T2 → T3 → T1...
            labels = [f"T{i+1}" for i in range(len(pps))]
            if len(labels) > 1:
                # Add wrap-around
                sequence = " → ".join(labels) + f" → {labels[0]}..."
            else:
                sequence = labels[0]

        if format_spec == "verbose":
            # Verbose mode: show intent + sequence + rationales
            result = ""

            # Add intent if present
            if self.intent:
                result = f"{self.intent} cycle: "
            else:
                result = "Cycle: "

            result += sequence

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
            # Default: just the sequence
            return sequence

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def __repr__(self) -> str:
        """Debug representation of the cycle."""
        hash_str = self.short_hash if self.is_committed else "uncommitted"
        pp_count = len(self.perspective_hashes)
        return f"Cycle({hash_str}, pp_count={pp_count}, intent={self.intent})"

