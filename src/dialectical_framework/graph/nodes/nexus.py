"""
Nexus node for the dialectical framework.

A Nexus is a pool of WisdomUnits where collective insights emerge.
It serves as a staging area before formal cycle arrangement.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.forkable_mixin import ForkableMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipTo,
    RelationshipManager,
)
from dialectical_framework.graph.relationships.belongs_to_nexus_relationship import (
    BelongsToNexusRelationship,
)
from dialectical_framework.graph.relationships.has_cycle_relationship import (
    HasCycleRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.cycle import Cycle


class Nexus(IncrementalBuildMixin, ForkableMixin, IntentMixin, AssessableEntity, label="Nexus"):
    """
    A pool of WisdomUnits where collective insights emerge.

    Nexus serves as a staging area before formal cycle arrangement.
    It represents the raw dialectical material that can be arranged
    into different causal configurations (cycles/wheels).

    Key Properties:
    - Assessable: Has P, R, Score like other entities
    - Pooling: Contains 1+ WisdomUnits
    - Generative: Can spawn multiple Cycles with different arrangements
    - Evolvable: Can shrink/expand to create new Nexuses

    Hierarchy:
        Input → DialecticalComponent → WisdomUnit → Nexus → Cycle → Wheel

    Example:
        nexus = Nexus()
        nexus.save()

        # Add WisdomUnits to the pool (child→parent: WU connects to Nexus)
        wu1.nexus.connect(nexus)
        wu2.nexus.connect(nexus)

        # Create a Cycle from this Nexus (parent→child: Nexus has Cycle)
        cycle = Cycle(intent="REALISTIC")
        cycle.save()
        nexus.cycles.connect(cycle)

        # Evolve the Nexus via clone:
        nexus2 = nexus.clone()
        # ... modify nexus2 ...
        nexus2.save()  # nexus2.origin_hash == nexus.hash
    """

    # WisdomUnits in this pool (incoming edges from WUs)
    # Child→parent: WU belongs to Nexus
    wisdom_units: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipFrom(
        "WisdomUnit",
        model=BelongsToNexusRelationship,
        cardinality=(1, None)  # At least one WU required
    )

    # Cycles derived from this Nexus
    # Parent→child: Nexus has cycles
    cycles: ClassVar[RelationshipManager[Cycle]] = RelationshipTo(
        "Cycle",
        model=HasCycleRelationship,
        cardinality=(0, None)  # Zero or more cycles can be derived
    )

    # Note: Evolution relationships (SHRUNK_TO, EXPANDED_TO) have been removed.
    # History tracking now uses origin_hash chain (set during clone).

    def _get_commit_dependents(self):
        """
        Get wisdom units for hash computation.

        Yields:
            WisdomUnit nodes
        """
        for wu, _ in self.wisdom_units.all():
            yield wu

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Nexus.

        Parts: sorted hashes of contained WisdomUnits.

        Returns:
            List of WisdomUnit hashes (sorted)

        Note:
            All connected WisdomUnits must be committed.
        """
        wu_hashes = []
        for wu, _ in self.wisdom_units.all():
            if not wu.is_committed:
                raise ValueError(
                    "WisdomUnit must be committed before computing "
                    "Nexus structure hash"
                )
            wu_hashes.append(wu.hash)

        # Sort for deterministic ordering
        wu_hashes.sort()
        return wu_hashes

    def __repr__(self) -> str:
        """String representation of the nexus."""
        wu_count = self.wisdom_units.count()
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Nexus({hash_str}, wisdom_units={wu_count})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        wu_count = self.wisdom_units.count()
        cycle_count = self.cycles.count()
        return f"Nexus with {wu_count} WisdomUnits, {cycle_count} Cycles"
