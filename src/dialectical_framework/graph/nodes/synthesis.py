"""
Synthesis node for dialectical framework.

Synthesis represents emergent properties from thesis-antithesis dialectic:
- S+ (Positive Synthesis): Complementary harmony where 1+1>2
- S- (Negative Synthesis): Reinforcing uniformity where 1+1<2
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
    SPlusRelationship,
    SMinusRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.wisdom_unit import WisdomUnit


class Synthesis(AssessableEntity):
    """
    Represents ONE synthesis interpretation of a dialectical pair.

    Each Synthesis contains a symmetric S+/S- pair representing emergent properties:
    - S+ (exactly one): Positive synthesis - complementary harmony (1+1>2)
    - S- (exactly one): Negative synthesis - reinforcing uniformity (1+1<2)

    A WisdomUnit can have multiple Synthesis nodes to explore alternative
    synthesis interpretations (similar to how multiple WUs explore alternative
    consequences of the same thesis).

    Unlike WisdomUnit's core 6 positions (T, T+, T-, A, A+, A-), synthesis
    is computed later and represents emergent properties of the dialectic.
    """

    # S+ side (exactly one positive synthesis component)
    s_plus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=SPlusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # S- side (exactly one negative synthesis component)
    s_minus: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        model=SMinusRelationship,
        cardinality=(1, 1)  # Exactly one
    )

    # Relationship to WisdomUnit
    wisdom_unit: ClassVar[RelationshipManager[WisdomUnit]] = RelationshipTo(
        "WisdomUnit",
        "SYNTHESIS_OF",
        cardinality=(1, 1)  # Exactly one WU
    )

    def __repr__(self) -> str:
        """String representation of the synthesis."""
        return f"Synthesis(uid={self.uid}, wisdom_unit={self.wisdom_unit})"

    def get_human_friendly_index(self) -> int:
        """
        Extract the human-friendly index from component aliases in this Synthesis.

        Looks at the S+ component's alias and extracts the numeric index.
        If no index exists, returns 0.

        Returns:
            The numeric index (e.g., S3+ → 3, S+ → 0)
        """
        import re

        # Get S+ component alias as representative
        sp_result = self.s_plus.get()
        if not sp_result:
            return 0

        _, rel = sp_result

        # Synthesis.s_plus relationship is always PolarityRelationship
        assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for S+, got {type(rel)}"
        alias = rel.alias  # Direct access, fully typed and validated

        # Find the last sequence of digits in the alias
        match = re.search(r"(\d+)(?!.*\d)", alias)
        return int(match.group(1)) if match else 0

    def set_human_friendly_index(self, human_friendly_index: int) -> None:
        """
        Updates the alias of all components in this Synthesis by setting the numeric index.

        Format: S3+, S1- (NOT S+3, S-1)

        Args:
            human_friendly_index: The integer index (0 = strip numbers, >0 = add/replace)

        Example:
            synth.set_human_friendly_index(3)
            # S+ → S3+, S- → S3-
        """
        import re

        for manager in [self.s_plus, self.s_minus]:
            for component, rel in manager.all():
                # Skip non-polarity relationships
                if not isinstance(rel, PolarityRelationship):
                    continue

                # alias is guaranteed to be non-empty by PolarityRelationship validation
                old_alias = rel.alias  # Direct access, fully typed

                # Apply same logic as WisdomUnit.set_human_friendly_index
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
                            # Example: S+ → S3+, S- → S3-
                            base = old_alias[: match.start()]
                            signs = match.group(1)
                            new_alias = f"{base}{human_friendly_index}{signs}"
                        else:
                            # No trailing signs, just append the index
                            new_alias = f"{old_alias}{human_friendly_index}"

                # Update the edge property if changed
                if new_alias != old_alias:
                    manager.disconnect(component)
                    manager.connect(component, properties={'alias': new_alias})

    def is_same(self, other: Synthesis) -> bool:
        """
        Check if this synthesis is the same as another synthesis.

        Compares by checking if both S+ and S- components match by UID.
        Two syntheses are considered the same if they contain the exact same
        S+/S- component pair, regardless of which WisdomUnit they belong to.

        Args:
            other: Another Synthesis to compare with

        Returns:
            True if both syntheses have the same S+ and S- components

        Example:
            synth1 = Synthesis(...)
            synth1.s_plus.connect(comp_sp)
            synth1.s_minus.connect(comp_sm)

            synth2 = Synthesis(...)
            synth2.s_plus.connect(comp_sp)  # Same component
            synth2.s_minus.connect(comp_sm)  # Same component

            synth1.is_same(synth2)  # Returns True
        """
        if self == other:
            return True
        if not isinstance(other, Synthesis):
            return False

        # Compare S+ components (exactly one each)
        self_sp = self.s_plus.get()
        other_sp = other.s_plus.get()

        if (self_sp is None) != (other_sp is None):
            return False
        if self_sp and other_sp and self_sp[0].uid != other_sp[0].uid:
            return False

        # Compare S- components (exactly one each)
        self_sm = self.s_minus.get()
        other_sm = other.s_minus.get()

        if (self_sm is None) != (other_sm is None):
            return False
        if self_sm and other_sm and self_sm[0].uid != other_sm[0].uid:
            return False

        return True

    def pretty(self) -> str:
        """
        Format this Synthesis for human-readable display.

        Formats both S+ and S- components with their aliases.

        Returns:
            Multi-line formatted string with S+ and S- components

        Example:
            S+ = Balance
            Explanation: Complementary harmony

            S- = Stagnation
            Explanation: Reinforcing uniformity
        """
        formatted_components = []

        # Format S+
        sp_result = self.s_plus.get()
        if sp_result:
            component, rel = sp_result
            # Synthesis relationships are always PolarityRelationship
            assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for S+, got {type(rel)}"
            alias = rel.alias  # Direct access, fully typed and validated
            formatted_components.append(component.pretty(alias))

        # Format S-
        sm_result = self.s_minus.get()
        if sm_result:
            component, rel = sm_result
            # Synthesis relationships are always PolarityRelationship
            assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for S-, got {type(rel)}"
            alias = rel.alias  # Direct access, fully typed and validated
            formatted_components.append(component.pretty(alias))

        return "\n\n".join(formatted_components)

    def __str__(self) -> str:
        """String representation using pretty format."""
        return self.pretty()
