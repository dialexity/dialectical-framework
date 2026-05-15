"""
Perspective with declarative relationships and cardinality constraints.

This version uses the enhanced RelationshipManager with cardinality support
for automatic validation and enforcement.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager, BoundRelationshipManager
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
    AspectRelationship,
    TRelationship,
    TPlusRelationship,
    TMinusRelationship,
    ARelationship,
    APlusRelationship,
    AMinusRelationship,
    HasPolarityRelationship,
)
from dialectical_framework.graph.relationships.belongs_to_nexus_relationship import (
    BelongsToNexusRelationship,
)
from dialectical_framework.graph.relationships.changed_to_relationship import (
    ChangedToRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.graph.nodes.nexus import Nexus

# Import Polarity and its position constants (T and A belong to Polarity)
from dialectical_framework.graph.nodes.polarity import Polarity, POSITION_T, POSITION_A

# Position constants for aspects - module level to avoid GQLAlchemy metaclass interference
# Note: POSITION_T and POSITION_A are in polarity.py (T/A belong to Polarity)
POSITION_T_PLUS = "T+"
POSITION_T_MINUS = "T-"
POSITION_A_PLUS = "A+"
POSITION_A_MINUS = "A-"


class Perspective(IncrementalBuildMixin, IntentMixin, AssessableEntity, label="Perspective"):
    """
    Represents ONE coherent dialectical analysis with enforced cardinality.

    A Perspective references a Polarity (T-A pair) and adds four aspects:
    - Polarity: contains T and A (the fundamental tension)
    - Aspects: T+, T-, A+, A- (healthy/problematic forms of each side)

    Structure:
        Polarity(T, A) + Aspects(T+, T-, A+, A-) = Perspective

    Each Perspective represents ONE dialectical exploration. To explore multiple
    consequences or alternative perspectives on the same T-A pair, create multiple
    Perspectives that share the same Polarity (different tetrad interpretations).

    Synthesis (S+, S-) is a wheel-level phenomenon — it emerges from the complete
    circular causality system, not from individual Perspectives.
    Access synthesis via: wheel.synthesis.all()

    The cardinality constraints are enforced at the RelationshipManager level,
    providing automatic validation and runtime checks.

    The intent field (from IntentMixin) captures the guiding question for this analysis.

    Lifecycle:
        1. Create or find a committed Polarity (T-A pair)
        2. pp = Perspective()
        3. pp.save()
        4. pp.polarity.connect(polarity)
        5. pp.t_plus.connect(t_plus_comp, relationship=TPlusRelationship(...))
        6. pp.t_minus.connect(t_minus_comp, relationship=TMinusRelationship(...))
        7. pp.a_plus.connect(a_plus_comp, relationship=APlusRelationship(...))
        8. pp.a_minus.connect(a_minus_comp, relationship=AMinusRelationship(...))
        9. pp.commit()
    """

    # Rejection marker — does not affect hash (metadata-only)
    rejected: Optional[str] = None

    def __init__(self, **data: Any):
        super().__init__(**data)
        self._cached_segment_t: Optional[WheelSegment] = None
        self._cached_segment_a: Optional[WheelSegment] = None

    # Reference to Polarity (T-A pair) - exactly one
    polarity: ClassVar[RelationshipManager[Polarity]] = RelationshipTo(
        "Polarity",
        model=HasPolarityRelationship,
        cardinality=(1, 1)  # Exactly one Polarity
    )

    # Four aspect positions (each exactly one)
    # T+ side (exactly one positive thesis aspect)
    t_plus: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=TPlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # T- side (exactly one negative thesis aspect)
    t_minus: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=TMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A+ side (exactly one positive antithesis aspect)
    a_plus: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=APlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # A- side (exactly one negative antithesis aspect)
    a_minus: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=AMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # Convenience properties to access T and A through Polarity
    @property
    def t(self) -> BoundRelationshipManager[Statement]:
        """
        Access T component through Polarity.

        Returns a BoundRelationshipManager that delegates to the Polarity's T manager.
        This provides backward compatibility for code that accesses pp.t directly.

        Raises:
            ValueError: If no Polarity is connected
        """
        polarity_result = self.polarity.get()
        if not polarity_result:
            raise ValueError("Perspective has no Polarity connected - cannot access T")
        pol, _ = polarity_result
        return pol.t

    @property
    def a(self) -> BoundRelationshipManager[Statement]:
        """
        Access A component through Polarity.

        Returns a BoundRelationshipManager that delegates to the Polarity's A manager.
        This provides backward compatibility for code that accesses pp.a directly.

        Raises:
            ValueError: If no Polarity is connected
        """
        polarity_result = self.polarity.get()
        if not polarity_result:
            raise ValueError("Perspective has no Polarity connected - cannot access A")
        pol, _ = polarity_result
        return pol.a

    # Exploration context: Nexuses this PP belongs to
    # PP→Nexus: PP can belong to multiple exploration contexts
    nexus: ClassVar[RelationshipManager[Nexus]] = RelationshipTo(
        "Nexus",
        model=BelongsToNexusRelationship,
        cardinality=(0, None)  # Zero or more nexuses (explored in different contexts)
    )

    # Lineage: what this PP evolved into (old→new direction)
    changed_to: ClassVar[RelationshipManager[Perspective]] = RelationshipTo(
        "Perspective",
        model=ChangedToRelationship,
        cardinality=(0, None)  # Can evolve into multiple variants
    )

    # Lineage: what this PP was derived from (new←old direction)
    derived_from: ClassVar[RelationshipManager[Perspective]] = RelationshipFrom(
        "Perspective",
        model=ChangedToRelationship,
        cardinality=(0, 1)  # At most one source (single parent)
    )

    def _get_commit_dependents(self):
        """
        Get all committed children for hash computation.

        For Perspective, yields the Polarity and all 4 aspect components.

        Yields:
            Polarity node and Component nodes (aspects)
        """
        # Yield Polarity
        polarity_result = self.polarity.get()
        if polarity_result:
            pol, _ = polarity_result
            yield pol

        # Yield 4 aspects
        for manager in [self.t_plus, self.t_minus, self.a_plus, self.a_minus]:
            result = manager.get()
            if result:
                comp, _ = result
                yield comp

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Perspective.

        Parts: Polarity hash + hashes of 4 aspect components (t+, t-, a+, a-).

        Returns:
            List of strings: [polarity_hash, t+_hash, t-_hash, a+_hash, a-_hash]

        Note:
            Polarity and all connected components must be committed.
        """
        parts = []

        # Get Polarity hash first
        polarity_result = self.polarity.get()
        if polarity_result:
            pol, _ = polarity_result
            if not pol.is_committed:
                raise ValueError(
                    "Polarity must be committed before computing "
                    "Perspective structure hash"
                )
            parts.append(pol.hash)
        else:
            parts.append("")  # Empty placeholder

        # Get hashes for all 4 aspect positions in order
        for manager in [self.t_plus, self.t_minus, self.a_plus, self.a_minus]:
            result = manager.get()
            if result:
                comp, _ = result
                if not comp.is_committed:
                    raise ValueError(
                        "Component must be committed before computing "
                        "Perspective structure hash"
                    )
                parts.append(comp.hash)
            else:
                parts.append("")  # Empty placeholder for missing positions

        return parts

    def __repr__(self) -> str:
        """String representation of the perspective."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Perspective({hash_str}, intent={self.intent})"

    def is_complete(self) -> bool:
        """
        Check if this perspective has all required components.

        A Perspective is complete when it has:
        - Required: polarity (with T and A), t_plus, t_minus, a_plus, a_minus
        - Optional: s_plus, s_minus (don't affect completeness)

        Returns:
            True if all required components are present
        """
        return (
            self.polarity.count() >= 1
            and self.t_plus.count() >= 1
            and self.t_minus.count() >= 1
            and self.a_plus.count() >= 1
            and self.a_minus.count() >= 1
        )

    def is_same(self, other: Perspective) -> bool:
        """
        Check if this Perspective has the same components as another.

        Compares by component hashes, not PP hashes (which include timestamps).
        Handles T-A symmetry: two PPs are the same if their T and A sides match,
        even if T and A are swapped between them.

        Args:
            other: Another Perspective to compare with

        Returns:
            True if both PPs have the same 6 components (possibly swapped)

        Example:
            # Same orientation
            pp1: T=X, A=Y → pp2: T=X, A=Y → is_same = True

            # Swapped orientation (still the same tension)
            pp1: T=X, A=Y → pp2: T=Y, A=X → is_same = True
        """
        if self is other:
            return True
        if not isinstance(other, Perspective):
            return False

        # Check normal orientation: T↔T, A↔A
        if (
            self.segment_t.is_same(other.segment_t)
            and self.segment_a.is_same(other.segment_a)
        ):
            return True

        # Check swapped orientation: T↔A, A↔T
        if (
            self.segment_t.is_same(other.segment_a)
            and self.segment_a.is_same(other.segment_t)
        ):
            return True

        return False

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

    def _get_aspect_ks(self, manager) -> Optional[float]:
        """Get complementarity_s (KS) for an aspect relationship manager."""
        result = manager.get()
        if not result:
            return None
        _, rel = result
        if isinstance(rel, AspectRelationship):
            return rel.complementarity_s
        return None

    @property
    def diff_t(self) -> Optional[float]:
        """
        Quality gap on the T-side: KS(T+) - KS(T-).

        Measures how much better the healthy form of T is compared to the problematic form.
        This differential indicates how well-differentiated the T aspects are.

        Formula:
            diff_t = KS(T+) - KS(T-)

        Where KS = complementarity_s = (complementarity_t + complementarity_a) / 2

        Interpretation:
            High diff_t (e.g., 0.30) → Clear distinction between healthy T+ and problematic T-
            Low diff_t  (e.g., 0.05) → Aspects are poorly differentiated, may need refinement

        Example (Love/Indifference tetrad):
            T+ (Bonding)      KS = 0.55  ─┐
                                          ├─ diff_t = 0.55 - 0.25 = 0.30
            T- (Enmeshment)   KS = 0.25  ─┘

        Returns:
            The differential value, or None if T+ or T- complementarity data is missing.
        """
        ks_t_plus = self._get_aspect_ks(self.t_plus)
        ks_t_minus = self._get_aspect_ks(self.t_minus)

        if ks_t_plus is None or ks_t_minus is None:
            return None

        return ks_t_plus - ks_t_minus

    @property
    def diff_a(self) -> Optional[float]:
        """
        Quality gap on the A-side: KS(A+) - KS(A-).

        Measures how much better the healthy form of A is compared to the problematic form.
        This differential indicates how well-differentiated the A aspects are.

        Formula:
            diff_a = KS(A+) - KS(A-)

        Where KS = complementarity_s = (complementarity_t + complementarity_a) / 2

        Interpretation:
            High diff_a (e.g., 0.60) → Clear distinction between healthy A+ and problematic A-
            Low diff_a  (e.g., 0.05) → Aspects are poorly differentiated, may need refinement

        Example (Love/Indifference tetrad):
            A+ (Autonomy)     KS = 0.80  ─┐
                                          ├─ diff_a = 0.80 - 0.20 = 0.60
            A- (Alienation)   KS = 0.20  ─┘

        Returns:
            The differential value, or None if A+ or A- complementarity data is missing.
        """
        ks_a_plus = self._get_aspect_ks(self.a_plus)
        ks_a_minus = self._get_aspect_ks(self.a_minus)

        if ks_a_plus is None or ks_a_minus is None:
            return None

        return ks_a_plus - ks_a_minus

    @property
    def rectangularity(self) -> Optional[float]:
        """
        Measures symmetry between T-side and A-side aspects. Lower is better.

        Formula:
            rectangularity = (KS(T+) - KS(A+))² + (KS(T-) - KS(A-))²

        Where KS = complementarity_s = (complementarity_t + complementarity_a) / 2

        Interpretation:
            Low rectangularity  (e.g., 0.002) → Balanced tetrad, like-signed aspects have similar KS
            High rectangularity (e.g., 0.090) → Skewed tetrad, one side dominates

        Visual intuition - a rectangular tetrad forms a proper rectangle when plotting KS:

            Balanced (low rectangularity):
            KS
             ↑
             │   T+ ●━━━━━━━━━● A+     ← similar KS (0.55, 0.58)
             │      ┃         ┃
             │   T- ●━━━━━━━━━● A-     ← similar KS (0.22, 0.25)
             └─────────────────→
                    T-side   A-side

            Unbalanced (high rectangularity):
            KS
             ↑
             │   T+ ●                  ← KS = 0.75
             │        ╲
             │          ● A+           ← KS = 0.45  (big gap!)
             │   T- ●━━━━● A-          ← similar (0.20, 0.22)
             └─────────────────→

        Use case:
            When selecting among sibling Perspectives (same T-A, different tetrads),
            prefer the one with lower rectangularity for a more balanced structure.

        Example scores:
            ┌─────────┬─────────┬─────────┬─────────┬────────────────┐
            │ KS(T+)  │ KS(A+)  │ KS(T-)  │ KS(A-)  │ Rectangularity │
            ├─────────┼─────────┼─────────┼─────────┼────────────────┤
            │ 0.55    │ 0.58    │ 0.22    │ 0.25    │ 0.002 ✓        │
            │ 0.60    │ 0.50    │ 0.25    │ 0.20    │ 0.012 ✓        │
            │ 0.75    │ 0.45    │ 0.20    │ 0.22    │ 0.090 ✗        │
            └─────────┴─────────┴─────────┴─────────┴────────────────┘

        Returns:
            The rectangularity score (lower is better), or None if data is missing.
        """
        ks_t_plus = self._get_aspect_ks(self.t_plus)
        ks_t_minus = self._get_aspect_ks(self.t_minus)
        ks_a_plus = self._get_aspect_ks(self.a_plus)
        ks_a_minus = self._get_aspect_ks(self.a_minus)

        if any(ks is None for ks in [ks_t_plus, ks_t_minus, ks_a_plus, ks_a_minus]):
            return None

        return (ks_t_plus - ks_a_plus) ** 2 + (ks_t_minus - ks_a_minus) ** 2

    @property
    def area(self) -> Optional[float]:
        """
        Total spread between positive and negative aspects. Higher is better.

        Formula:
            area = KS(T+) + KS(A+) - KS(T-) - KS(A-)
                 = (sum of positive aspects) - (sum of negative aspects)
                 = diff_t + diff_a

        Where KS = complementarity_s = (complementarity_t + complementarity_a) / 2

        Interpretation:
            High area (e.g., 1.00) → Strong differentiation between healthy and problematic aspects
            Low area  (e.g., 0.30) → Weak distinction, aspects are "mushed together"

        Visual intuition:

            High Area (good):
            KS
             ↑
             │   T+ ●━━━━━━━━━● A+     ← HIGH (0.70, 0.75)
             │      ┃         ┃
             │      ┃  AREA   ┃        ← Big gap = lots of area
             │      ┃         ┃
             │   T- ●━━━━━━━━━● A-     ← LOW (0.20, 0.25)
             └─────────────────→
            Area = 1.45 - 0.45 = 1.00 ✓

            Low Area (poor):
            KS
             ↑
             │   T+ ●━━━━━━━━━● A+     ← MID (0.50, 0.55)
             │      ┃  area   ┃        ← Small gap
             │   T- ●━━━━━━━━━● A-     ← MID (0.35, 0.40)
             └─────────────────→
            Area = 1.05 - 0.75 = 0.30 ✗

        Example scores:
            ┌─────────┬─────────┬─────────┬─────────┬──────┐
            │ KS(T+)  │ KS(A+)  │ KS(T-)  │ KS(A-)  │ Area │
            ├─────────┼─────────┼─────────┼─────────┼──────┤
            │ 0.70    │ 0.75    │ 0.20    │ 0.25    │ 1.00 │
            │ 0.60    │ 0.65    │ 0.25    │ 0.30    │ 0.70 │
            │ 0.50    │ 0.55    │ 0.35    │ 0.40    │ 0.30 │
            └─────────┴─────────┴─────────┴─────────┴──────┘

        Returns:
            The area score (higher is better), or None if data is missing.
        """
        diff_t = self.diff_t
        diff_a = self.diff_a

        if diff_t is None or diff_a is None:
            return None

        return diff_t + diff_a

    @property
    def area_normalized(self) -> Optional[float]:
        """
        Area normalized to approximately 0-1 range.

        Formula:
            area_normalized = area / 2

        The maximum theoretical area is 2.0 (when positive aspects = 1.0 and negative aspects = 0.0),
        so dividing by 2 normalizes to a 0-1 range.

        Interpretation:
            ~0.5 → Excellent differentiation
            ~0.35 → Good differentiation
            ~0.15 → Poor differentiation

        Returns:
            The normalized area score (0-1, higher is better), or None if data is missing.
        """
        area = self.area
        if area is None:
            return None

        return area / 2

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
            rel_class = Perspective.get_relationship_class_for_position(POSITION_T)
            # rel_class is TRelationship
            pp.t.connect(component, relationship=rel_class(alias='T1'))
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

    def get_relationship_manager_by_position(self, position: str) -> BoundRelationshipManager[Statement]:
        """
        Get the bound relationship manager for a given position name.

        Args:
            position: Position name (e.g., 'T', 'A', 'T+', 'T-', 'A+', 'A-')

        Returns:
            The corresponding BoundRelationshipManager (bound to this PP instance)

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
            raise ValueError(f"Unknown position: {position}. Note: S+/S- are on the Synthesis node, not Perspective.")
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

    def get_component(self, alias: str) -> Optional[Statement]:
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
            pp.get_component('T1')  # Finds component with alias='T1'
            pp.get_component('Democracy')  # Finds component with alias='Democracy'
        """
        # Search all 6 core positions (t/a go through Polarity, may not be available)
        managers = []
        try:
            managers.append(self.t)
        except ValueError:
            pass
        managers.extend([self.t_plus, self.t_minus])
        try:
            managers.append(self.a)
        except ValueError:
            pass
        managers.extend([self.a_plus, self.a_minus])

        for manager in managers:
            for component, rel in manager.all():
                if isinstance(rel, PolarityRelationship) and rel.alias == alias:
                    return component
        return None

    def has_component(self, component: Statement) -> bool:
        """
        Check if this Perspective contains the given component.

        Searches all 6 positions (T, A, T+, T-, A+, A-) by hash match.

        Args:
            component: The component to check

        Returns:
            True if the component is in any position of this PP
        """
        if not component.is_committed:
            return False

        target_hash = component.hash
        managers = []
        try:
            managers.append(self.t)
        except ValueError:
            pass
        managers.extend([self.t_plus, self.t_minus])
        try:
            managers.append(self.a)
        except ValueError:
            pass
        managers.extend([self.a_plus, self.a_minus])

        for manager in managers:
            for comp, _ in manager.all():
                if comp.hash == target_hash:
                    return True
        return False

    @property
    def core_positions(self) -> list[str]:
        """
        Get list of all 6 core position names.

        Returns:
            List of position names that can be used with get_relationship_manager_by_position()

        Note:
            - T and A are accessed through the Polarity node
            - S+/S- are on the Synthesis node, not Perspective
        """
        return [
            POSITION_T,
            POSITION_A,
            POSITION_T_PLUS,
            POSITION_T_MINUS,
            POSITION_A_PLUS,
            POSITION_A_MINUS,
        ]

    @property
    def aspect_positions(self) -> list[str]:
        """
        Get list of the 4 aspect position names (excluding T and A).

        These are the positions directly on Perspective (not on Polarity).

        Returns:
            List of aspect position names: [T+, T-, A+, A-]
        """
        return [
            POSITION_T_PLUS,
            POSITION_T_MINUS,
            POSITION_A_PLUS,
            POSITION_A_MINUS,
        ]

    def get_human_friendly_index(self) -> int:
        """
        Extract the human-friendly index from component aliases in this PP.

        Looks at the T component's alias and extracts the numeric index.
        If no index exists, returns 0.

        Returns:
            The numeric index (e.g., T3 → 3, T → 0)

        Example:
            pp.set_human_friendly_index(3)  # T → T3
            pp.get_human_friendly_index()   # Returns 3
        """
        import re

        # Get T component alias as representative
        t_result = self.t.get()
        if not t_result:
            return 0

        _, rel = t_result

        # Perspective.t relationship is always PolarityRelationship
        assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for T, got {type(rel)}"
        alias = rel.alias  # Direct access, fully typed and validated

        # Find the last sequence of digits in the alias
        match = re.search(r"(\d+)(?!.*\d)", alias)
        return int(match.group(1)) if match else 0

    def set_human_friendly_index(self, human_friendly_index: int) -> None:
        """
        Updates the alias of all components in this PP by setting the numeric index.

        If the index is 0, removes any existing digits entirely.
        If no digits exist and index > 0, inserts the index before any trailing signs.

        Format: T3+, A1-, T2 (NOT T+3, A-1)

        Args:
            human_friendly_index: The integer index (0 = strip numbers, >0 = add/replace)

        Note:
            T and A aliases are stored on the Polarity's edges. If multiple Perspectives
            share the same Polarity, updating these aliases affects all of them.
            The 4 aspect aliases (T+, T-, A+, A-) are Perspective-specific.

        Example:
            pp.set_human_friendly_index(3)
            # T → T3, A+ → A3+, T- → T3-, etc.
        """
        import re

        # Build list of (manager, rel_class) tuples
        # Note: T and A managers come from Polarity, aspects from this Perspective
        managers_and_types: list[tuple[BoundRelationshipManager, type]] = [
            (self.t, TRelationship),
            (self.t_plus, TPlusRelationship),
            (self.t_minus, TMinusRelationship),
            (self.a, ARelationship),
            (self.a_plus, APlusRelationship),
            (self.a_minus, AMinusRelationship),
        ]

        for manager, rel_class in managers_and_types:
            for component, rel in manager.all():
                # Skip non-polarity relationships
                if not isinstance(rel, PolarityRelationship):
                    continue

                # alias is guaranteed to be non-empty by PolarityRelationship validation
                old_alias = rel.alias  # Direct access, fully typed

                # Apply same logic as legacy Statement.set_human_friendly_index
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
        Format this Perspective using Python's format string protocol.

        Format Specifications:
        ----------------------

        Format: [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored, core positions only
            "positions" - Uses canonical positions (T, T+, T-, A, A+, A-)
            "strip_index" - Strips numeric indexes: "T1" → "T", "Foo2+" → "Foo+"
            "full" - Perspective + Transformation (vertical)
            "full:compact" - Perspective/Transformation side-by-side (tabular, no explanations)

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
        "full"          - Perspective + Transformation (vertical)
        "full:compact"  - Perspective/Transformation tabular (no explanations)

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
