"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents the Action-Reflection
dialectical structure within a WisdomUnit. A Transformation IS a full 6-position
dialectical structure (Ac, Re, Ac+, Ac-, Re+, Re-), not just transitions.
"""

from __future__ import annotations

import re
from typing import ClassVar, Optional, TYPE_CHECKING, Union, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager, BoundRelationshipManager
from dialectical_framework.graph.relationships.is_spiral_of_relationship import (
    IsSpiralOfRelationship,
)
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
    AcRelationship,
    ReRelationship,
    AcPlusRelationship,
    AcMinusRelationship,
    RePlusRelationship,
    ReMinusRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.transition import Transition


# Position constants for Ac/Re structure
POSITION_AC = "Ac"
POSITION_RE = "Re"
POSITION_AC_PLUS = "Ac+"
POSITION_AC_MINUS = "Ac-"
POSITION_RE_PLUS = "Re+"
POSITION_RE_MINUS = "Re-"


class Transformation(IncrementalBuildMixin, IntentMixin, AssessableEntity, label="Transformation"):
    """
    Action-Reflection dialectical structure within a WisdomUnit.

    A Transformation represents a full 6-position dialectical structure capturing
    how the WisdomUnit's tension can be navigated through action and reflection.
    Each position is a Transition (source → target):

    - Ac (Action): T → A (transforms Thesis into Antithesis)
    - Ac+ (Positive Action): T- → A+ (transforms negative Thesis into positive Antithesis)
    - Ac- (Negative Action): T+ → A- (transforms positive Thesis into negative Antithesis)
    - Re (Reflection): A → T (transforms Antithesis into Thesis)
    - Re+ (Positive Reflection): A- → T+ (transforms negative Antithesis into positive Thesis)
    - Re- (Negative Reflection): A+ → T- (transforms positive Antithesis into negative Thesis)

    Diagonal contradictions:
    - Re+ contradicts Ac-
    - Re- contradicts Ac+

    A WisdomUnit can have multiple Transformations representing different paths
    through the same tension. Synthesis emerges from the WisdomUnit level, not
    from individual Transformation paths.

    Lifecycle (IncrementalBuildMixin pattern):
        1. Create: transformation = Transformation()
        2. Set parent: transformation.set_wisdom_unit(wu)
        3. Save (HEAD state): transformation.save()
        4. Add transitions: transformation.ac.connect(transition), etc.
        5. Commit (immutable): transformation.commit()

    Relationships:
    - Transformations are internal to WisdomUnit (accessed via wu.transformations)
    - They contain 6 Transition positions (Ac, Re, Ac+, Ac-, Re+, Re-)
    - They do NOT directly connect to Wheel (accessed via their WisdomUnit)
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

    # The containing WisdomUnit (this transformation is internal to it)
    wisdom_unit: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        model=IsSpiralOfRelationship,
        cardinality=(1, 1)  # Required - transformation belongs to one wisdom unit
    )

    # 6 transition position relationships (Ac-Re structure)
    # Each position is a Transition (source → target) representing a transformation path
    # All positions are optional (0, 1) - in practice often only Ac+ and Re+ are populated
    # Neutral positions (reference points)
    ac: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=AcRelationship,
        cardinality=(0, 1)  # Optional: T → A
    )

    re: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=ReRelationship,
        cardinality=(0, 1)  # Optional: A → T
    )

    # Pole positions (have complementarity)
    # Ac+ and Re+ are REQUIRED - the core transformation path
    ac_plus: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=AcPlusRelationship,
        cardinality=(1, 1)  # Required: T- → A+
    )

    ac_minus: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=AcMinusRelationship,
        cardinality=(0, 1)  # Optional: T+ → A-
    )

    re_plus: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=RePlusRelationship,
        cardinality=(1, 1)  # Required: A- → T+
    )

    re_minus: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=ReMinusRelationship,
        cardinality=(0, 1)  # Optional: A+ → T-
    )

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
        nexus_result = wisdom_unit.nexus.get()
        if nexus_result:
            return nexus_result[0]

        return None

    def _get_commit_dependents(self):
        """
        Get all 6 transitions for hash computation.

        Required by IncrementalBuildMixin for commit() validation.

        Yields:
            Transition nodes from all 6 positions
        """
        for manager in [self.ac, self.re, self.ac_plus, self.ac_minus, self.re_plus, self.re_minus]:
            result = manager.get()
            if result:
                trans, _ = result
                yield trans

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Transformation.

        Parts: WisdomUnit hash, hashes of all 6 transition positions.
        The WU hash ensures uniqueness across different WisdomUnits.

        Returns:
            List of strings: [wu_hash, ac_hash, re_hash, ac+_hash, ac-_hash, re+_hash, re-_hash]

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

        # Get hashes for all 6 transition positions in order
        for manager in [self.ac, self.re, self.ac_plus, self.ac_minus, self.re_plus, self.re_minus]:
            result = manager.get()
            if result:
                trans, _ = result
                if not trans.is_committed:
                    raise ValueError(
                        "Transition must be committed before computing "
                        "Transformation structure hash"
                    )
                parts.append(trans.hash)
            else:
                parts.append("")  # Empty placeholder for missing positions

        return parts

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Self:
        """
        Commit this transformation: save (if needed), compute hash, persist, and create relationships.

        Lifecycle:
        1. Create transformation and set_wisdom_unit()
        2. (Optional) save() and add components explicitly
        3. commit() - auto-saves if needed, computes hash from components, makes immutable

        If wisdom_unit was set via set_wisdom_unit(), the relationship is
        automatically created after the node is committed.

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
            ValueError: If any child component is not committed
        """
        # Auto-save if not already saved (allows calling commit() directly)
        if self._id is None:
            result = graph_db.save_node(self)
            if result is not None and result._id is not None:
                self._id = result._id

        # Auto-connect wisdom_unit BEFORE commit (so cardinality validation passes)
        if self._wisdom_unit_ref and self.wisdom_unit.count() == 0:
            self.wisdom_unit.connect(self._wisdom_unit_ref)
            self._wisdom_unit_ref = None  # Clear transient ref

        # Call IncrementalBuildMixin.commit() which validates children and computes hash
        super().commit()

        return self

    @staticmethod
    def get_relationship_class_for_position(position: str) -> type[PolarityRelationship]:
        """
        Get the correct PolarityRelationship subclass for a given position.

        This mapping is used when creating relationships to ensure the correct
        relationship type is used for querying.

        Args:
            position: Position name (e.g., 'Ac', 'Re', 'Ac+', 'Ac-', 'Re+', 'Re-')

        Returns:
            The relationship class for that position

        Raises:
            ValueError: If position is not recognized

        Example:
            rel_class = Transformation.get_relationship_class_for_position(POSITION_AC)
            # rel_class is AcRelationship
            transformation.ac.connect(component, relationship=rel_class(alias='Ac'))
        """
        position_to_rel_class = {
            POSITION_AC: AcRelationship,
            POSITION_RE: ReRelationship,
            POSITION_AC_PLUS: AcPlusRelationship,
            POSITION_AC_MINUS: AcMinusRelationship,
            POSITION_RE_PLUS: RePlusRelationship,
            POSITION_RE_MINUS: ReMinusRelationship,
        }

        rel_class = position_to_rel_class.get(position)
        if rel_class is None:
            raise ValueError(
                f"Unknown position: {position}. "
                f"Valid positions: Ac, Re, Ac+, Ac-, Re+, Re-"
            )
        return rel_class

    def get_relationship_manager_by_position(self, position: str) -> BoundRelationshipManager[Transition]:
        """
        Get the bound relationship manager for a given position name.

        Args:
            position: Position name (e.g., 'Ac', 'Re', 'Ac+', 'Ac-', 'Re+', 'Re-')

        Returns:
            The corresponding BoundRelationshipManager (bound to this Transformation instance)

        Raises:
            ValueError: If position is not recognized

        Note:
            Position is NOT the same as alias!
            - Position: Structural role ('Ac', 'Re+') - which relationship manager
            - Alias: Display label stored on edge ('Ac1', 'Action', 'Re3+') - can be anything
        """
        position_map = {
            # Position constants
            POSITION_AC: self.ac,
            POSITION_RE: self.re,
            POSITION_AC_PLUS: self.ac_plus,
            POSITION_AC_MINUS: self.ac_minus,
            POSITION_RE_PLUS: self.re_plus,
            POSITION_RE_MINUS: self.re_minus,
            # Attribute format (lowercase, underscore) for convenience
            'ac': self.ac,
            're': self.re,
            'ac_plus': self.ac_plus,
            'ac_minus': self.ac_minus,
            're_plus': self.re_plus,
            're_minus': self.re_minus,
        }
        if position not in position_map:
            raise ValueError(f"Unknown position: {position}. Valid positions: Ac, Re, Ac+, Ac-, Re+, Re-")
        return position_map[position]

    @property
    def core_positions(self) -> list[str]:
        """
        Get list of all 6 core position names.

        Returns:
            List of position names that can be used with get_relationship_manager_by_position()
        """
        return [
            POSITION_AC,
            POSITION_RE,
            POSITION_AC_PLUS,
            POSITION_AC_MINUS,
            POSITION_RE_PLUS,
            POSITION_RE_MINUS,
        ]

    def get_human_friendly_index(self) -> int:
        """
        Get the human-friendly index from the containing WisdomUnit.

        Delegates to wisdom_unit.get_human_friendly_index().

        Returns:
            The numeric index (e.g., 3 if WU components have T3, A3+, etc.), or 0 if not set
        """
        wu_result = self.wisdom_unit.get()
        if not wu_result:
            return 0
        wu, _ = wu_result
        return wu.get_human_friendly_index()

    def __format__(self, format_spec: str) -> str:
        """
        Format this Transformation by displaying its Ac-Re structure.

        Format Specifications:
        ----------------------
        [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored
            "positions" - Uses canonical positions (Ac, Ac+, Ac-, Re, Re+, Re-)
            "strip_index" - Strips numeric indexes

        Newlines (optional):
            :0 - Comma separation (compact single line)
            :1 - Single newline between transitions (compact)
            :2 - Double newline between transitions (spacious, default)

        Examples:
        ---------
        f"{transformation}"           - Default format
        f"{transformation:positions}" - Canonical positions
        f"{transformation::1}"        - Compact (1 newline)
        f"{transformation:positions:0}" - Canonical positions, comma separated

        Returns:
            Formatted string of the Ac-Re structure with transitions
        """
        # Parse format spec: [mode][:newlines]
        if ":" in format_spec:
            mode, newlines_str = format_spec.split(":", 1)
            try:
                newlines = int(newlines_str)
            except ValueError:
                newlines = 2  # Default on parse error
        else:
            mode = format_spec
            newlines = 2  # Default: double newline

        # Validate newlines
        if newlines < 0:
            newlines = 0

        formatted_transitions = []

        # Define position order and canonical names
        positions = [
            (self.ac, POSITION_AC),
            (self.ac_plus, POSITION_AC_PLUS),
            (self.ac_minus, POSITION_AC_MINUS),
            (self.re, POSITION_RE),
            (self.re_plus, POSITION_RE_PLUS),
            (self.re_minus, POSITION_RE_MINUS),
        ]

        for manager, canonical_position in positions:
            result = manager.get()
            if result:
                transition, rel = result
                assert isinstance(rel, PolarityRelationship)
                alias = rel.alias

                # Apply mode formatting
                if mode == "positions":
                    alias = canonical_position
                elif mode == "strip_index":
                    alias = re.sub(r"(\d+)(?!.*\d)", "", alias)
                # else: empty mode - use alias as-is

                formatted_transitions.append(f"{alias} = {transition}")

        # Join with specified separator
        if newlines < 1:
            separator = ", "
        else:
            separator = "\n" * newlines
        return separator.join(formatted_transitions)

    def __str__(self) -> str:
        """Human-readable string representation (defaults to Ac-Re structure format)."""
        return self.__format__("")

    def __repr__(self) -> str:
        """String representation of the transformation."""
        hash_str = self.short_hash if self.is_committed else "uncommitted"
        return f"Transformation({hash_str})"
