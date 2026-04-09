"""
Cycle node for the dialectical framework.

This module provides the Cycle class which represents the T-cycle:
an ordered sequence of WisdomUnits defining abstract thesis causality.

A Cycle captures the order in which theses relate causally (T1 → T2 → T3).
Multiple Wheels can share the same T-cycle with different flip configurations.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.forkable_mixin import ForkableMixin
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.has_wheel_relationship import (
    HasWheelRelationship,
)
from dialectical_framework.graph.relationships.evolved_to_relationship import (
    EvolvedToRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class Cycle(ForkableMixin, IntentMixin, AssessableEntity, label="Cycle"):
    """
    Represents the T-cycle: an ordered sequence of WisdomUnits.

    A Cycle defines abstract thesis causality - the order in which theses
    relate to each other (T1 → T2 → T3). This is the "pool" of WisdomUnits
    in a specific causal arrangement.

    The intent field captures the dynamics/causality type of this cycle
    (e.g., "preset:realistic", "preset:desirable", "preset:feasible", "preset:balanced").

    Multiple Wheels can implement the same Cycle with different flip configurations,
    where each WU can have its T and A sides swapped.

    Hierarchy:
        WisdomUnit → Cycle (ordered pool + intent) → Wheel (flips + transitions)

    Relationships:
    - Cycle contains ordered WU hashes (stored as field, not relationships)
    - Cycle can have multiple Wheels (different flip configurations)
    - Use wisdom_units property to get WU instances
    - Use wheels.all() to find associated Wheels

    Example:
        # Create WUs
        wu1.commit()
        wu2.commit()
        wu3.commit()

        # Create cycle with ordered WUs
        cycle = Cycle(intent="preset:balanced")
        cycle.set_wisdom_units([wu1, wu2, wu3])  # Order matters
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

    # Ordered list of WisdomUnit hashes - defines the T-cycle order
    wisdom_unit_hashes: list[str] = []

    # Transient refs for setting WUs before commit (not persisted)
    _wu_refs: Optional[list[WisdomUnit]] = None

    # Wheels that implement this cycle's arrangement
    # Parent→child: Cycle has Wheels
    wheels: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        model=HasWheelRelationship,
        cardinality=(0, None)  # Zero or more wheels can implement this cycle
    )

    # Evolution lineage: Cycles that evolved from this one (added WU)
    # Parent→children: This Cycle evolved to child Cycles
    evolutions: ClassVar[RelationshipManager[Cycle]] = RelationshipTo(
        "Cycle",
        model=EvolvedToRelationship,
        cardinality=(0, None)  # Zero or more child cycles
    )

    # Reverse lookup: The parent Cycle this one evolved from
    evolved_from: ClassVar[RelationshipManager[Cycle]] = RelationshipFrom(
        "Cycle",
        model=EvolvedToRelationship,
        cardinality=(0, 1)  # At most one parent
    )

    def set_wisdom_units(self, wisdom_units: list[WisdomUnit]) -> Cycle:
        """
        Set the ordered list of WisdomUnits for this cycle.

        Must be called before commit(). All WUs must be committed.
        Order determines the T-cycle: T1 → T2 → T3 → T1...

        Args:
            wisdom_units: Ordered list of committed WisdomUnits

        Returns:
            Self for chaining

        Raises:
            ValueError: If any WU is not committed
        """
        hashes = []
        for wu in wisdom_units:
            if not wu.is_committed:
                raise ValueError(
                    "WisdomUnit must be committed before adding to Cycle"
                )
            hashes.append(wu.hash)

        self.wisdom_unit_hashes = hashes
        self._wu_refs = wisdom_units  # Keep refs for potential use
        return self

    @property
    def wisdom_units(self) -> list[WisdomUnit]:
        """
        Get the WisdomUnits in cycle order.

        Returns WU instances by looking up their hashes.

        Returns:
            List of WisdomUnit instances in T-cycle order
        """
        if not self.wisdom_unit_hashes:
            return []

        from dialectical_framework.graph.repositories.node_repository import NodeRepository
        repo = NodeRepository()

        result = []
        for wu_hash in self.wisdom_unit_hashes:
            wu = repo.find_by_hash(wu_hash)
            if wu:
                result.append(wu)
        return result

    @property
    def wisdom_unit_count(self) -> int:
        """Number of WisdomUnits in this cycle."""
        return len(self.wisdom_unit_hashes)

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Cycle.

        Parts: ordered WU hashes (NOT sorted - order matters for T-cycle).
        The intent is added separately by BaseNode.compute_hash().

        Returns:
            List of strings: [wu_hash1, wu_hash2, wu_hash3, ...]

        Raises:
            ValueError: If no WisdomUnits are set
        """
        if not self.wisdom_unit_hashes:
            raise ValueError(
                "Cycle must have WisdomUnits set before computing structure hash. "
                "Use set_wisdom_units()."
            )

        # Return hashes in order (NOT sorted - order defines the T-cycle)
        return list(self.wisdom_unit_hashes)

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
        # Build T-cycle sequence from WU order
        wus = self.wisdom_units
        if not wus:
            sequence = "[no WisdomUnits]"
        else:
            # T-cycle shows thesis positions: T1 → T2 → T3 → T1...
            labels = [f"T{i+1}" for i in range(len(wus))]
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
        wu_count = len(self.wisdom_unit_hashes)
        return f"Cycle({hash_str}, wu_count={wu_count}, intent={self.intent})"

    def get_effective_intent(self, default: str = "preset:balanced") -> str:
        """
        Get the effective intent, inheriting from parent if None.

        Traverses the evolved_from chain until an explicit intent is found,
        or returns the default if no intent is set in the lineage.

        Args:
            default: Default intent if none found in lineage

        Returns:
            The effective intent string
        """
        if self.intent:
            return self.intent

        parent_result = self.evolved_from.get()
        if parent_result:
            parent, _ = parent_result
            return parent.get_effective_intent(default)

        return default
