"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents transformational
patterns within a WisdomUnit with action-reflection components.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.belongs_to_cycle_relationship import (
    BelongsToCycleRelationship,
)
from dialectical_framework.graph.relationships.is_spiral_of_relationship import (
    IsSpiralOfRelationship,
)
from dialectical_framework.graph.relationships.action_reflection_relationship import (
    ActionReflectionRelationship,
)
from dialectical_framework.graph.relationships.synthesis_of_relationship import (
    SynthesisOfRelationship,
)
from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.synthesis import Synthesis


class Transformation(IncrementalBuildMixin, IntentMixin, CircularTopologyMixin, AssessableEntity, label="Transformation"):
    """
    Internal transformation within a WisdomUnit.

    A Transformation represents the internal dialectical transformation within
    a single wisdom unit. It captures the action-reflection cycle: T- → A+, A- → T+.

    Unlike Spiral (which exists at the Wheel level), Transformation is internal
    to a WisdomUnit and does not directly relate to Wheels.

    A transformation always has exactly 2 transitions:
    - T- to A+ (thesis negative to antithesis positive)
    - A- to T+ (antithesis negative to thesis positive)

    Lifecycle (IncrementalBuildMixin pattern):
        1. Create: transformation = Transformation()
        2. Set parent: transformation.set_wisdom_unit(wu)
        3. Save (HEAD state): transformation.save()
        4. Add children: transition.cycle.connect(transformation)
        5. Commit (immutable): transformation.commit()

    Relationships:
    - Transformations are internal to WisdomUnit (accessed via wisdom_unit.transformation)
    - They reference an action-reflection WisdomUnit via ac_re
    - They do NOT directly connect to Wheel (accessed via their WisdomUnit)
    - The ac_re WisdomUnit may or may not be part of the wheel's wisdom_units

    Note: Transformation and Spiral are siblings (both inherit from AssessableEntity),
    not parent-child. This prevents Transformation from inheriting Spiral's
    Wheel relationship, which would be semantically incorrect.
    """

    # Hash inputs - set before save() to include in hash
    _wisdom_unit_hash: Optional[str] = None
    # Transient ref for auto-connecting after save
    _wisdom_unit_ref: Optional[WisdomUnit] = None

    def set_wisdom_unit(self, wu: WisdomUnit) -> Transformation:
        """
        Set the containing WisdomUnit for this transformation (before save).

        This stores the reference for hash computation and auto-connection after save.
        The WisdomUnit must already be committed (have hash).

        Args:
            wu: The committed WisdomUnit this transformation belongs to

        Returns:
            Self for chaining

        Raises:
            ValueError: If WisdomUnit is not committed
        """
        if not wu.is_committed:
            raise ValueError(
                "WisdomUnit must be committed before setting on transformation. "
                "Call wu.commit() first."
            )
        self._wisdom_unit_hash = wu.hash
        self._wisdom_unit_ref = wu
        return self

    # Override _transitions from CircularTopologyMixin with exact cardinality
    # Exactly two transitions for internal transformation: T- → A+, A- → T+
    _transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=BelongsToCycleRelationship,
        cardinality=(2, 2)  # Exactly two transitions
    )

    # The containing WisdomUnit (this transformation is internal to it)
    wisdom_unit: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        model=IsSpiralOfRelationship,
        cardinality=(1, 1)  # Required - transformation (spiral) belongs to one wisdom unit
    )

    # The action-reflection context WisdomUnit (what this transformation is about)
    ac_re: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        model=ActionReflectionRelationship,
        cardinality=(1, 1)  # Required action-reflection wisdom unit
    )

    # Synthesis alternatives (S+/S- pairs) derived from this transformation
    synthesis: ClassVar[RelationshipManager[Synthesis]] = RelationshipFrom(
        "Synthesis",
        model=SynthesisOfRelationship,
        cardinality=(0, None)  # Zero or more synthesis alternatives
    )

    # Note: Transformation does not directly connect to Wheel
    # It's accessed via its containing WisdomUnit (wisdom_unit field)

    def get_nexus(self) -> Nexus | None:
        """
        Get the nexus this transformation belongs to via its WisdomUnit.

        Transformation is internal to a WisdomUnit, so this method:
        1. Gets the containing WisdomUnit
        2. Gets the first Nexus from that WisdomUnit

        Returns:
            Nexus instance or None if not connected

        Example:
            nexus = transformation.get_nexus()
            if nexus:
                print(f"Transformation's source nexus has {nexus.wisdom_units.count()} WUs")
        """
        # Get the containing WisdomUnit
        wu_result = self.wisdom_unit.get()
        if not wu_result:
            return None

        wisdom_unit = wu_result[0]

        # Get the first Nexus from the WisdomUnit.
        # It's fine to take any Nexus since aliases are stored on WU-Component edges,
        # not on Nexus relationships - all Nexuses containing this WU see the same aliases.
        nexus_result = wisdom_unit.nexus.get()
        if nexus_result:
            return nexus_result[0]

        return None

    def _get_commit_dependents(self):
        """
        Get transitions for hash computation.

        Required by IncrementalBuildMixin for commit() validation.

        Yields:
            Transition nodes
        """
        for trans in self.transitions:
            yield trans

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Transformation.

        Parts: WisdomUnit hash, ordered transition hashes.
        The WU hash ensures uniqueness since each WU has at most one transformation.

        Returns:
            List of strings: [wu_hash, trans_hash1, trans_hash2, ...]

        Raises:
            ValueError: If WisdomUnit not set or not committed
        """
        parts = []

        # Get containing WisdomUnit hash - prefer stored hash, fall back to relationship
        wu_hash = self._wisdom_unit_hash
        if not wu_hash:
            wu_result = self.wisdom_unit.get()
            if wu_result:
                wu, _ = wu_result
                if not wu.is_committed:
                    raise ValueError(
                        "WisdomUnit must be committed before computing Transformation structure hash"
                    )
                wu_hash = wu.hash

        if not wu_hash:
            raise ValueError(
                "Transformation must have a WisdomUnit set before computing hash. "
                "Use set_wisdom_unit() first."
            )
        parts.append(wu_hash)

        # Get transition hashes in order (may be empty for new transformations)
        for trans in self.transitions:
            if not trans.is_committed:
                raise ValueError(
                    "Transition must be committed before computing "
                    "Transformation structure hash"
                )
            parts.append(trans.hash)

        return parts

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Transformation:
        """
        Commit this transformation: save (if needed), compute hash, persist, and create relationships.

        Lifecycle:
        1. Create transformation and set_wisdom_unit()
        2. (Optional) save() and add transitions explicitly
        3. commit() - auto-saves if needed, computes hash from transitions, makes immutable

        If wisdom_unit was set via set_wisdom_unit(), the relationship is
        automatically created after the node is committed.

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
            ValueError: If any child transition is not committed
        """
        # Auto-save if not already saved (allows calling commit() directly)
        if self._id is None:
            result = graph_db.save_node(self)
            if result is not None and result._id is not None:
                self._id = result._id

        # Call IncrementalBuildMixin.commit() which validates children and computes hash
        super().commit()

        # Auto-connect wisdom_unit if ref was stored AND not already connected
        if self._wisdom_unit_ref and self.wisdom_unit.count() == 0:
            self.wisdom_unit.connect(self._wisdom_unit_ref)
            self._wisdom_unit_ref = None  # Clear transient ref

        return self

    def __format__(self, format_spec: str) -> str:
        """
        Format this Transformation by displaying its ac_re WisdomUnit.

        Format specifications are passed through to the ac_re WisdomUnit's __format__ method.
        See WisdomUnit.__format__ for available format specifications.

        Format Specifications:
        ----------------------
        [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored
            "positions" - Uses canonical positions (T, T+, T-, A, A+, A-)
            "strip_index" - Strips numeric indexes

        Newlines (optional):
            :0 - Comma separation (compact single line)
            :1 - Single newline between components (compact)
            :2 - Double newline between components (spacious, default)

        Examples:
        ---------
        f"{transformation}"           - Default format
        f"{transformation:positions}" - Canonical positions
        f"{transformation::1}"        - Compact (1 newline)
        f"{transformation:positions:0}" - Canonical positions, comma separated

        Returns:
            Formatted string of the ac_re WisdomUnit, or empty string if ac_re not set
        """
        ac_re_result = self.ac_re.get()
        if not ac_re_result:
            return ""

        ac_re_wu, _ = ac_re_result
        return f"{ac_re_wu:{format_spec}}"

    def __str__(self) -> str:
        """Human-readable string representation (defaults to ac_re WisdomUnit format)."""
        return self.__format__("")

    def __repr__(self) -> str:
        """String representation of the transformation."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Transformation({hash_str})"
