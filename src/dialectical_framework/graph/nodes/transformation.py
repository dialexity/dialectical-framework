"""
Transformation node for the dialectical framework.

This module provides the Transformation class which represents the Action-Reflection
dialectical structure. A Transformation IS a full 6-position dialectical structure
(Ac, Re, Ac+, Ac-, Re+, Re-) and belongs to an edge (Transition) in a Wheel.

A wheel's edges define the causality sequence. Each edge can have multiple
Transformation alternatives at different insight/proactiveness levels.
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
from dialectical_framework.graph.relationships.action_reflection_relationship import (
    ActionReflectionRelationship,
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
    Action-Reflection dialectical structure belonging to a wheel edge.

    A Transformation represents a full 6-position dialectical structure capturing
    how tension(s) can be navigated through action and reflection. Transformations
    belong to an edge (a Transition in the wheel's causality sequence) and represent
    one alternative way to navigate that edge.

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

    Multiple Transformations can exist for the same edge, representing different
    alternatives at various insight/proactiveness levels (see Fig. 8 in paper).

    Lifecycle (IncrementalBuildMixin pattern):
        1. Create: transformation = Transformation()
        2. Set edge: transformation.set_on_edge(wheel_edge)
        3. Save (HEAD state): transformation.save()
        4. Add transitions: transformation.ac_plus.connect(transition), etc.
        5. Commit (immutable): transformation.commit()

    Relationships:
    - Transformations belong to an edge (wheel Transition) via ACTION_REFLECTION
    - Access via: transformation.edge.get() to get the (Transition, rel) tuple
    - They contain 6 Transition positions (Ac, Re, Ac+, Ac-, Re+, Re-)
    """

    # Hash inputs - set before save() to include in hash
    _edge_hash: Optional[str] = None
    # Transient ref for auto-connecting after save
    _edge_ref: Optional[Transition] = None

    def set_on_edge(self, edge: Transition) -> Transformation:
        """
        Set the edge (wheel transition) for this transformation.

        This stores the reference for hash computation and auto-connection after save.
        The Transition must already be committed.

        Args:
            edge: The committed wheel Transition this transformation is an alternative for

        Returns:
            Self for chaining

        Raises:
            ValueError: If Transition is not committed
        """
        if not edge.is_committed:
            raise ValueError(
                "Edge (Transition) must be committed before setting on transformation."
            )
        self._edge_hash = edge.hash
        self._edge_ref = edge
        return self

    # The edge this transformation is an alternative for
    # Uses ACTION_REFLECTION relationship: Transformation --ACTION_REFLECTION--> Transition
    edge: ClassVar[RelationshipManager[Transition]] = RelationshipTo(
        "Transition",
        model=ActionReflectionRelationship,
        cardinality=(1, 1)  # Required - transformation belongs to one edge
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

    # Aspect positions (have complementarity)
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
        Get the Wheel this transformation belongs to (via edge).

        Returns:
            Wheel instance or None if not connected
        """
        edge_result = self.edge.get()
        if edge_result:
            edge_transition, _ = edge_result
            # Edge is a wheel transition, find its wheel
            for wheel, _ in edge_transition.cycle.all():
                # cycle relationship returns Cycle/Wheel containers
                from dialectical_framework.graph.nodes.wheel import Wheel
                if isinstance(wheel, Wheel):
                    return wheel
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

        Parts: edge (Transition) hash, hashes of all 6 transition positions.
        Source/target segments are derivable from transitions (no need to store indices).

        Returns:
            List of strings for hash computation

        Raises:
            ValueError: If edge is not set
        """
        parts = []

        # Get edge hash
        step_hash = self._edge_hash
        if not step_hash:
            edge_result = self.edge.get()
            if edge_result:
                edge_transition, _ = edge_result
                if edge_transition.is_committed:
                    step_hash = edge_transition.hash

        if not step_hash:
            raise ValueError(
                "Transformation must have an edge set before computing hash. "
                "Use set_on_edge() first."
            )

        parts.append(step_hash)

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
        1. Create transformation and set_on_edge()
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

        # Auto-connect edge BEFORE commit
        if self._edge_ref and self.edge.count() == 0:
            self.edge.connect(self._edge_ref)
            self._edge_ref = None  # Clear transient ref

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
            if pair.perspective.has_component(source):
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
            if pair.perspective.has_component(target):
                return pair
        return None

    def get_human_friendly_index(self) -> int:
        """
        Get the human-friendly index from the source polar segment.

        Returns:
            The numeric index (e.g., 3 if PP components have T3, A3+, etc.), or 0 if not set
        """
        segment = self.get_source_polar_segment()
        if not segment:
            return 0
        return segment.perspective.get_human_friendly_index()

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
