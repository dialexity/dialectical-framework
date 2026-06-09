"""
Nexus node for the dialectical framework.

This module provides the Nexus class which represents an exploration container
for Perspectives. A Nexus groups PPs with a specific intent for exploration,
enabling systematic combination into Cycles and Wheels.
"""

from __future__ import annotations

from typing import ClassVar, Union, TYPE_CHECKING, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.causality_preset import CausalityPreset
from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipManager,
)
from dialectical_framework.graph.relationships.belongs_to_nexus_relationship import (
    BelongsToNexusRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.perspective import Perspective


class Nexus(IntentMixin, BaseNode, label="Nexus"):
    """
    Exploration container for Perspectives.

    A Nexus provides required exploration context for combining Perspectives
    into Cycles and Wheels. It groups PPs with a specific intent for exploration,
    enabling layer-by-layer combination:

    - Layer 1: Single PP Cycles/Wheels
    - Layer 2: Pairs of PPs -> multiple T-cycle orderings -> multiple TA-wheel arrangements
    - Layer 3: Triplets -> more orderings -> more wheel arrangements
    - etc.

    Two separate concerns:
    - intent: Free-form exploration purpose (e.g., "deep meaning of love").
      From IntentMixin. Describes what the user wants to understand.
    - preset: Prompt strategy for causality estimation (e.g., "preset:balanced").
      Selects which estimator class estimates Cycles/Wheels.

    Identity is hash-based (Merkle): hash = sha256(preset + intent + committed_at).

    Other key properties:
    - sid: Inherited from BaseNode - the Case's sid (required, links to parent)

    Relationships:
    - perspectives: Perspectives in this exploration (RelationshipFrom)

    Note: Cycles are derived from the PPs in this Nexus, not stored as a relationship.

    Example:
        case = Case()
        case.commit()

        nexus = Nexus(
            sid=case.sid,
            intent="I want to understand the deep meaning of love",
            preset=CausalityPreset.BALANCED,
        )
        nexus.commit()

        pp1.nexus.connect(nexus)
        pp2.nexus.connect(nexus)
    """

    # Prompt strategy for causality estimation (preset selector)
    preset: str = CausalityPreset.BALANCED

    # Display title (not part of hash — purely metadata).
    # NOTE: Cannot use Optional[str] here due to GQLAlchemy metaclass + future annotations.
    title: str = None

    # Perspectives in this exploration
    # PP→Nexus: Perspective belongs to this Nexus
    perspectives: ClassVar[RelationshipManager[Perspective]] = RelationshipFrom(
        "Perspective",
        model=BelongsToNexusRelationship,
        cardinality=(0, None),  # Zero or more PPs
    )

    # NOTE: Cycles are derived from PPs, not stored as relationship.

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect the parts that make up this Nexus's structure hash.

        Nexus identity is based on its preset. Intent is added by
        compute_hash() via IntentMixin, and committed_at ensures uniqueness.
        """
        return [self.preset]

    @inject
    def commit(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]) -> Self:
        """
        Commit this Nexus to the database.

        Computes hash from preset + intent + committed_at and persists.

        Returns:
            Self for chaining

        Raises:
            ValueError: If sid is not set
        """
        if not self.sid:
            raise ValueError("Nexus must have sid set before commit (use Case's sid)")

        return super().commit(graph_db=graph_db)

    def __repr__(self) -> str:
        """Debug representation of the Nexus."""
        id_str = self.short_hash or "uncommitted"
        pp_count = self.perspectives.count()
        title_str = f", title={self.title}" if self.title else ""
        return f"Nexus({id_str}{title_str}, pps={pp_count}, preset={self.preset}, intent={self.intent})"

    def __str__(self) -> str:
        """String representation of the Nexus."""
        id_str = self.short_hash or "uncommitted"
        parts = [f"hash={id_str}", f"preset={self.preset}"]
        if self.title:
            parts.append(f"title={self.title}")
        if self.intent:
            parts.append(f"intent={self.intent}")
        return f"Nexus({', '.join(parts)})"
