"""
Nexus node for the dialectical framework.

A Nexus is a pool of WisdomUnits where collective insights emerge.
It serves as a staging area before formal cycle arrangement.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
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
from dialectical_framework.graph.relationships.shrunk_to_relationship import (
    ShrunkToRelationship,
)
from dialectical_framework.graph.relationships.expanded_to_relationship import (
    ExpandedToRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.cycle import Cycle


class Nexus(IntentMixin, AssessableEntity, label="Nexus"):
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

        # Evolve the Nexus
        nexus2 = Nexus()
        nexus2.save()
        nexus.shrunk_to.connect(nexus2)  # Reduced version
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

    # Evolution relationships (direct, no intermediate nodes)
    # Nexus → SHRUNK_TO → Nexus (reduced version)
    shrunk_to: ClassVar[RelationshipManager[Nexus]] = RelationshipTo(
        "Nexus",
        model=ShrunkToRelationship,
        cardinality=(0, None)
    )

    # Nexus → EXPANDED_TO → Nexus (expanded version)
    expanded_to: ClassVar[RelationshipManager[Nexus]] = RelationshipTo(
        "Nexus",
        model=ExpandedToRelationship,
        cardinality=(0, None)
    )

    # Reverse relationships for evolution tracking
    # A Nexus can have at most one parent per evolution type
    shrunk_from: ClassVar[RelationshipManager[Nexus]] = RelationshipFrom(
        "Nexus",
        model=ShrunkToRelationship,
        cardinality=(0, 1)
    )

    expanded_from: ClassVar[RelationshipManager[Nexus]] = RelationshipFrom(
        "Nexus",
        model=ExpandedToRelationship,
        cardinality=(0, 1)
    )

    def __repr__(self) -> str:
        """String representation of the nexus."""
        wu_count = self.wisdom_units.count()
        return f"Nexus(uid={self.uid}, wisdom_units={wu_count})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        wu_count = self.wisdom_units.count()
        cycle_count = self.cycles.count()
        return f"Nexus with {wu_count} WisdomUnits, {cycle_count} Cycles"
