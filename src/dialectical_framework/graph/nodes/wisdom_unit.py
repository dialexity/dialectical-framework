"""
WisdomUnit with declarative relationships and cardinality constraints.

This version uses the enhanced RelationshipManager with cardinality support
for automatic validation and enforcement.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager, BoundRelationshipManager
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
    TRelationship,
    TPlusRelationship,
    TMinusRelationship,
    ARelationship,
    APlusRelationship,
    AMinusRelationship,
)
from dialectical_framework.graph.relationships.belongs_to_nexus_relationship import (
    BelongsToNexusRelationship,
)
from dialectical_framework.graph.relationships.changed_to_relationship import (
    ChangedToRelationship,
)
from dialectical_framework.graph.relationships.is_spiral_of_relationship import (
    IsSpiralOfRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.wheel_segment import WheelSegment

# Position constants - module level to avoid GQLAlchemy metaclass interference
# Note: S+ and S- constants are in synthesis.py (Synthesis now belongs to Transformation/Spiral)
POSITION_T = "T"
POSITION_T_PLUS = "T+"
POSITION_T_MINUS = "T-"
POSITION_A = "A"
POSITION_A_PLUS = "A+"
POSITION_A_MINUS = "A-"


class WisdomUnit(IntentMixin, AssessableEntity, label="WisdomUnit"):
    """
    Represents ONE coherent dialectical analysis with enforced cardinality.

    A WisdomUnit contains exactly ONE component per polarity position:
    - Thesis side (T-side): 1 T, 1 T+, 1 T-
    - Antithesis side (A-side): 1 A, 1 A+, 1 A-

    Total: 6 core positions forming a complete dialectical analysis.

    Each WisdomUnit represents ONE dialectical exploration. To explore multiple
    consequences or alternative perspectives on the same thesis, create multiple
    WisdomUnits that share the same T component node (component reuse pattern).

    Note: Synthesis (S+, S-) emerges from Transformation, not directly from WisdomUnit.
    Access synthesis via: wu.transformation.get()[0].synthesis.all()

    The cardinality constraints are enforced at the RelationshipManager level,
    providing automatic validation and runtime checks.

    The intent field (from IntentMixin) captures the guiding question for this analysis.
    """

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._cached_segment_t: Optional[WheelSegment] = None
        self._cached_segment_a: Optional[WheelSegment] = None

    # Declarative relationships with specific polarity relationship types
    # The alias is stored on the relationship edge, making component positions contextual
    # Each polarity has its own relationship type for fine-grained querying

    # T-side (exactly one neutral thesis)
    t: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # T+ side (exactly one positive thesis)
    t_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TPlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # T- side (exactly one negative thesis)
    t_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=TMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A-side (exactly one neutral antithesis)
    a: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=ARelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A+ side (exactly one positive antithesis)
    a_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=APlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A- side (exactly one negative antithesis)
    a_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=AMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # Relationship to Nexus (pool of WisdomUnits)
    # WisdomUnits can belong to multiple Nexuses for different analytical perspectives.
    # Child→parent: WU belongs to Nexus
    nexus: ClassVar[RelationshipManager[Nexus]] = RelationshipTo(
        "Nexus",
        model=BelongsToNexusRelationship,
        cardinality=(0, None)  # Zero or more Nexuses
    )

    # Evolution relationships (direct, no intermediate nodes)
    # WU → CHANGED_TO → WU (evolved version)
    changed_to: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        model=ChangedToRelationship,
        cardinality=(0, None)
    )

    # Reverse: WU ← CHANGED_TO ← WU (source of evolution)
    # Single lineage: a WU can only evolve from one predecessor
    changed_from: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipFrom(
        "WisdomUnit",
        model=ChangedToRelationship,
        cardinality=(0, 1)
    )

    # Internal transformation spiral (T- → A+, A- → T+)
    transformation: ClassVar[RelationshipManager[Transformation]] = RelationshipFrom(
        "Transformation",
        model=IsSpiralOfRelationship,
        cardinality=(0, 1)  # Zero or one internal transformation spiral
    )

    # Note: Transformation.ac_re points to action-reflection WisdomUnit.
    # No inverse defined here - a WU can be the ac_re for unlimited transformations.
    # No inverse = implicit (0, None) cardinality.

    def __repr__(self) -> str:
        """String representation of the wisdom unit."""
        return f"WisdomUnit(uid={self.uid}, intent={self.intent})"

    def is_complete(self) -> bool:
        """
        Check if this wisdom unit has all required components.

        A WisdomUnit is complete when it has:
        - Required: t, a, t_plus, t_minus, a_plus, a_minus (at least one each)
        - Optional: s_plus, s_minus (don't affect completeness)

        Returns:
            True if all required components are present
        """
        return (
            self.t.count() >= 1
            and self.t_plus.count() >= 1
            and self.t_minus.count() >= 1
            and self.a.count() >= 1
            and self.a_plus.count() >= 1
            and self.a_minus.count() >= 1
        )

    @property
    def segment_t(self) -> WheelSegment:
        """
        Get the T-side segment as a WheelSegment window.
        """
        if self._cached_segment_t is None:
            from dialectical_framework.graph.wheel_segment import WheelSegment
            self._cached_segment_t = WheelSegment(self, 'T')
        return self._cached_segment_t

    @property
    def segment_a(self) -> WheelSegment:
        """
        Get the A-side segment as a WheelSegment window.
        """
        if self._cached_segment_a is None:
            from dialectical_framework.graph.wheel_segment import WheelSegment
            self._cached_segment_a = WheelSegment(self, 'A')
        return self._cached_segment_a

    @staticmethod
    def get_relationship_class_for_position(position: str) -> type[PolarityRelationship]:
        """
        Get the correct PolarityRelationship subclass for a given position.

        This mapping is used when creating relationships to ensure the correct
        relationship type is used for querying (e.g., TRelationship for position T).

        Args:
            position: Position name (e.g., 'T', 'A', 'T+', 'T-', 'A+', 'A-')

        Returns:
            The relationship class for that position

        Raises:
            ValueError: If position is not recognized

        Example:
            rel_class = WisdomUnit.get_relationship_class_for_position(POSITION_T)
            # rel_class is TRelationship
            wu.t.connect(component, relationship=rel_class(alias='T1'))
        """
        position_to_rel_class = {
            POSITION_T: TRelationship,
            POSITION_T_PLUS: TPlusRelationship,
            POSITION_T_MINUS: TMinusRelationship,
            POSITION_A: ARelationship,
            POSITION_A_PLUS: APlusRelationship,
            POSITION_A_MINUS: AMinusRelationship,
        }

        rel_class = position_to_rel_class.get(position)
        if rel_class is None:
            raise ValueError(
                f"Unknown position: {position}. "
                f"Valid positions: T, A, T+, T-, A+, A-"
            )
        return rel_class

    def get_relationship_manager_by_position(self, position: str) -> BoundRelationshipManager[DialecticalComponent]:
        """
        Get the bound relationship manager for a given position name.

        Args:
            position: Position name (e.g., 'T', 'A', 'T+', 'T-', 'A+', 'A-')

        Returns:
            The corresponding BoundRelationshipManager (bound to this WU instance)

        Raises:
            ValueError: If position is not recognized (including S+/S- which are on Synthesis node)

        Note:
            Position is NOT the same as alias!
            - Position: Structural role ('T', 'A+') - which relationship manager
            - Alias: Display label stored on edge ('T1', 'Democracy', 'A3+') - can be anything
        """
        position_map = {
            # Position constants
            POSITION_T: self.t,
            POSITION_A: self.a,
            POSITION_T_PLUS: self.t_plus,
            POSITION_T_MINUS: self.t_minus,
            POSITION_A_PLUS: self.a_plus,
            POSITION_A_MINUS: self.a_minus,
            # Attribute format (lowercase, underscore) for backward compatibility
            't': self.t,
            'a': self.a,
            't_plus': self.t_plus,
            't_minus': self.t_minus,
            'a_plus': self.a_plus,
            'a_minus': self.a_minus,
        }
        if position not in position_map:
            raise ValueError(f"Unknown position: {position}. Note: S+/S- are on the Synthesis node, not WisdomUnit.")
        return position_map[position]

    def is_set(self, position: str) -> bool:
        """
        Check if a component is connected at the given position.

        Args:
            position: Position name (e.g., 'T', 'A', 'T+')

        Returns:
            True if at least one component is connected at this position
        """
        try:
            manager = self.get_relationship_manager_by_position(position)
            return manager.count() > 0
        except ValueError:
            return False

    def get_component(self, alias: str) -> Optional[DialecticalComponent]:
        """
        Get the component with a given alias by searching all positions.

        Alias can be anything: 'T', 'T1', 'A3+', 'Democracy', etc.
        This method searches all relationship managers to find which component
        has this alias stored on its edge.

        Args:
            alias: Component alias to search for (any string)

        Returns:
            The component if found, None otherwise

        Example:
            wu.get_component('T1')  # Finds component with alias='T1'
            wu.get_component('Democracy')  # Finds component with alias='Democracy'
        """
        # Search all 6 core positions
        for manager in [self.t, self.t_plus, self.t_minus, self.a, self.a_plus, self.a_minus]:
            for component, rel in manager.all():
                # Use isinstance for type-safe property access
                if isinstance(rel, PolarityRelationship) and rel.alias == alias:
                    return component
        return None

    @property
    def core_positions(self) -> list[str]:
        """
        Get list of all 6 core position names.

        Returns:
            List of position names that can be used with get_relationship_manager_by_position()

        Note: S+/S- are NOT included - they are on the Synthesis node
        """
        return [
            POSITION_T,
            POSITION_A,
            POSITION_T_PLUS,
            POSITION_T_MINUS,
            POSITION_A_PLUS,
            POSITION_A_MINUS,
        ]

    def get_human_friendly_index(self) -> int:
        """
        Extract the human-friendly index from component aliases in this WU.

        Looks at the T component's alias and extracts the numeric index.
        If no index exists, returns 0.

        Returns:
            The numeric index (e.g., T3 → 3, T → 0)

        Example:
            wu.set_human_friendly_index(3)  # T → T3
            wu.get_human_friendly_index()   # Returns 3
        """
        import re

        # Get T component alias as representative
        t_result = self.t.get()
        if not t_result:
            return 0

        _, rel = t_result

        # WisdomUnit.t relationship is always PolarityRelationship
        assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for T, got {type(rel)}"
        alias = rel.alias  # Direct access, fully typed and validated

        # Find the last sequence of digits in the alias
        match = re.search(r"(\d+)(?!.*\d)", alias)
        return int(match.group(1)) if match else 0

    def set_human_friendly_index(self, human_friendly_index: int) -> None:
        """
        Updates the alias of all components in this WU by setting the numeric index.

        If the index is 0, removes any existing digits entirely.
        If no digits exist and index > 0, inserts the index before any trailing signs.

        Format: T3+, A1-, T2 (NOT T+3, A-1)

        Args:
            human_friendly_index: The integer index (0 = strip numbers, >0 = add/replace)

        Example:
            wu.set_human_friendly_index(3)
            # T → T3, A+ → A3+, T- → T3-, etc.
        """
        import re

        # Map managers to their relationship types
        manager_to_rel_type = {
            id(self.t): (self.t, TRelationship),
            id(self.t_plus): (self.t_plus, TPlusRelationship),
            id(self.t_minus): (self.t_minus, TMinusRelationship),
            id(self.a): (self.a, ARelationship),
            id(self.a_plus): (self.a_plus, APlusRelationship),
            id(self.a_minus): (self.a_minus, AMinusRelationship),
        }

        for manager_id, (manager, rel_class) in manager_to_rel_type.items():
            for component, rel in manager.all():
                # Skip non-polarity relationships
                if not isinstance(rel, PolarityRelationship):
                    continue

                # alias is guaranteed to be non-empty by PolarityRelationship validation
                old_alias = rel.alias  # Direct access, fully typed

                # Apply same logic as legacy DialecticalComponent.set_human_friendly_index
                if human_friendly_index == 0:
                    # Remove the last sequence of digits entirely
                    new_alias = re.sub(r"(\d+)(?!.*\d)", "", old_alias)
                else:
                    # Try to replace existing digits first
                    if re.search(r"\d", old_alias):
                        # Replace the last sequence of digits with the new index
                        new_alias = re.sub(r"(\d+)(?!.*\d)", str(human_friendly_index), old_alias)
                    else:
                        # No digits exist, insert before any trailing signs
                        match = re.search(r"([+-]+)$", old_alias)
                        if match:
                            # Has trailing signs (+ or -), insert index before them
                            # Example: T+ → T3+, A- → A3-
                            base = old_alias[: match.start()]
                            signs = match.group(1)
                            new_alias = f"{base}{human_friendly_index}{signs}"
                        else:
                            # No trailing signs, just append the index
                            # Example: T → T3, A → A3
                            new_alias = f"{old_alias}{human_friendly_index}"

                # Update the edge property if changed
                if new_alias != old_alias:
                    # Update relationship property in place (no disconnect/reconnect needed)
                    manager.update_properties(component, {'alias': new_alias})

    def __format__(self, format_spec: str) -> str:
        """
        Format this WisdomUnit using Python's format string protocol.

        Format Specifications:
        ----------------------

        Format: [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored, core positions only
            "positions" - Uses canonical positions (T, T+, T-, A, A+, A-)
            "strip_index" - Strips numeric indexes: "T1" → "T", "Foo2+" → "Foo+"
            "full" - Synthesis + WisdomUnit + Transformation (vertical)
            "full:compact" - Synthesis + WisdomUnit/Transformation side-by-side (tabular, no explanations)

        Newlines (optional):
            Default: 2 newlines between components (if not specified)
            :0 - Comma separation (compact single line, NO explanations)
            :1 - Single newline between components (compact)
            :2 - Double newline between components (spacious, default)

        Examples:
        ---------
        ""              - Core positions, 2 newlines, with explanations
        "positions"     - Canonical positions, 2 newlines, with explanations
        ":0"            - Core positions, comma separated, NO explanations
        "positions:0"   - Canonical positions, comma separated, NO explanations
        "full"          - Synthesis, WisdomUnit, Transformation (vertical)
        "full:compact"  - Synthesis, WisdomUnit/Transformation tabular (no explanations)

        Returns:
            Formatted string
        """
        from dialectical_framework.graph.wheel_segment_polar_pair import WheelSegmentPolarPair

        # Create a normal polarity pair and delegate formatting to it
        pair = WheelSegmentPolarPair(self, "normal")
        return pair.__format__(format_spec)

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")
