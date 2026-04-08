"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents the Action-Reflection
dialectical structure. A Transformation IS a full 6-position dialectical structure
(Ac, Re, Ac+, Ac-, Re+, Re-) and belongs to a Wheel (not a WisdomUnit).

Transformations can span multiple WisdomUnits in a Wheel, with recursive
decomposition for multi-step transformations.
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
from dialectical_framework.graph.relationships.has_transformation_relationship import (
    HasTransformationRelationship,
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
    from dialectical_framework.graph.nodes.wheel import Wheel, WheelSegmentPolarPair
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
    Action-Reflection dialectical structure belonging to a Wheel.

    A Transformation represents a full 6-position dialectical structure capturing
    how tension(s) can be navigated through action and reflection. Transformations
    belong to a Wheel and can span multiple WisdomUnits.

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

    Single vs Multi-segment:
    - Single-segment: All transitions stay within one polar segment
    - Multi-segment: Transitions cross segment boundaries (X- → Y+)

    Lifecycle (IncrementalBuildMixin pattern):
        1. Create: transformation = Transformation()
        2. Set parent wheel: transformation.set_wheel(wheel)
        3. Save (HEAD state): transformation.save()
        4. Add transitions: transformation.ac_plus.connect(transition), etc.
        5. Commit (immutable): transformation.commit()

    Relationships:
    - Transformations belong to Wheel (accessed via wheel.transformations)
    - They contain 6 Transition positions (Ac, Re, Ac+, Ac-, Re+, Re-)
    """

    # Hash inputs - set before save() to include in hash
    _wheel_hash: Optional[str] = None
    # Transient ref for auto-connecting after save
    _wheel_ref: Optional[Wheel] = None

    def set_wheel(self, wheel: Wheel) -> Transformation:
        """
        Set the containing Wheel for this transformation (before save).

        This stores the reference for hash computation and auto-connection after save.
        The Wheel must already be saved (have _id).

        Args:
            wheel: The saved Wheel this transformation belongs to

        Returns:
            Self for chaining

        Raises:
            ValueError: If Wheel is not saved
        """
        if wheel._id is None:
            raise ValueError(
                "Wheel must be saved before setting on transformation. "
                "Call wheel.save() first."
            )
        if wheel.is_committed:
            self._wheel_hash = wheel.hash
        self._wheel_ref = wheel
        return self

    # The containing Wheel (required)
    wheel: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        model=HasTransformationRelationship,
        cardinality=(1, 1)  # Required - transformation belongs to one wheel
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

    def get_wheel(self) -> Wheel | None:
        """
        Get the Wheel this transformation belongs to.

        Returns:
            Wheel instance or None if not connected
        """
        wheel_result = self.wheel.get()
        if wheel_result:
            return wheel_result[0]
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

        Parts: Wheel hash, hashes of all 6 transition positions.
        Source/target WUs are derivable from transitions (no need to store indices).

        Returns:
            List of strings for hash computation

        Raises:
            ValueError: If Wheel is not set
        """
        parts = []

        # Get Wheel hash
        wheel_hash = self._wheel_hash
        if not wheel_hash:
            wheel_result = self.wheel.get()
            if wheel_result:
                wheel, _ = wheel_result
                if wheel.is_committed:
                    wheel_hash = wheel.hash

        if not wheel_hash:
            raise ValueError(
                "Transformation must have a Wheel set before computing hash. "
                "Use set_wheel() first."
            )

        parts.append(wheel_hash)

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
        1. Create transformation and set_wheel()
        2. (Optional) save() and add transitions explicitly
        3. commit() - auto-saves if needed, computes hash from components, makes immutable

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

        # Auto-connect wheel BEFORE commit
        if self._wheel_ref and self.wheel.count() == 0:
            self.wheel.connect(self._wheel_ref)
            self._wheel_ref = None  # Clear transient ref

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

    def get_source_polar_segment(self) -> WheelSegmentPolarPair | None:
        """
        Get the source polar segment (derives from ac_plus source component).

        The Ac+ transition goes from the "minus side" of one segment to
        the "plus side" of another. This returns the segment containing
        the source (minus side).

        Returns:
            WheelSegmentPolarPair containing the ac_plus source, or None
        """
        ac_plus_result = self.ac_plus.get()
        if not ac_plus_result:
            return None

        trans, _ = ac_plus_result
        source = trans.get_source()
        if not source:
            return None

        wheel = self.get_wheel()
        if not wheel:
            return None

        for pair in wheel.polar_segments:
            if pair.wisdom_unit.has_component(source):
                return pair
        return None

    def get_target_polar_segment(self) -> WheelSegmentPolarPair | None:
        """
        Get the target polar segment (derives from ac_plus target component).

        The Ac+ transition goes from the "minus side" of one segment to
        the "plus side" of another. This returns the segment containing
        the target (plus side).

        Returns:
            WheelSegmentPolarPair containing the ac_plus target, or None
        """
        ac_plus_result = self.ac_plus.get()
        if not ac_plus_result:
            return None

        trans, _ = ac_plus_result
        target = trans.get_target()
        if not target:
            return None

        wheel = self.get_wheel()
        if not wheel:
            return None

        for pair in wheel.polar_segments:
            if pair.wisdom_unit.has_component(target):
                return pair
        return None

    def get_human_friendly_index(self) -> int:
        """
        Get the human-friendly index from the source polar segment.

        Returns:
            The numeric index (e.g., 3 if WU components have T3, A3+, etc.), or 0 if not set
        """
        segment = self.get_source_polar_segment()
        if not segment:
            return 0
        return segment.wisdom_unit.get_human_friendly_index()

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
