"""
Synthesis node for dialectical framework.

Synthesis represents emergent properties from thesis-antithesis dialectic:
- S+ (Positive Synthesis): Complementary harmony where 1+1>2
- S- (Negative Synthesis): Reinforcing uniformity where 1+1<2
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.polarity_relationship import (
    PolarityRelationship,
    SPlusRelationship,
    SMinusRelationship,
)
from dialectical_framework.graph.relationships.synthesis_of_relationship import (
    SynthesisOfRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.perspective import Perspective

# Position constants for S+/S- (canonical names)
POSITION_S_PLUS = "S+"
POSITION_S_MINUS = "S-"


class Synthesis(IncrementalBuildMixin, IntentMixin, AssessableEntity, label="Synthesis"):
    """
    Represents ONE synthesis interpretation of a dialectical tension.

    Each Synthesis contains a symmetric S+/S- pair representing emergent properties:
    - S+ (exactly one): Positive synthesis - complementary harmony (1+1>2)
    - S- (exactly one): Negative synthesis - reinforcing uniformity (1+1<2)

    Synthesis emerges from Perspective: The T-A tension itself
    (many transformation paths → ONE synthesis).

    A Perspective can have multiple Synthesis nodes to explore
    alternative synthesis interpretations.
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

    # Target relationship (Perspective only)
    # Synthesis emerges from PP-level tension (many Ac-Re paths → ONE synthesis)
    target: ClassVar[RelationshipManager[Perspective]] = RelationshipTo(
        "Perspective",
        model=SynthesisOfRelationship,
        cardinality=(1, 1)  # Exactly one target
    )

    @property
    def target_type(self) -> str:
        """
        Return type of target: 'perspective' or 'none'.

        Returns:
            Lowercase name of the target class, or 'none' if not connected.
        """
        result = self.target.get()
        if result:
            return type(result[0]).__name__.lower()
        return "none"

    def _get_commit_dependents(self):
        """
        Yield committed S+ and S- components for IncrementalBuildMixin.

        Required by IncrementalBuildMixin to verify all children are committed
        before computing hash.
        """
        sp_result = self.s_plus.get()
        if sp_result:
            yield sp_result[0]

        sm_result = self.s_minus.get()
        if sm_result:
            yield sm_result[0]

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Synthesis.

        Parts: S+ component hash, S- component hash.

        Returns:
            List of strings: [s+_hash, s-_hash]

        Note:
            Target (Perspective/Transformation) and S+/S- components must be committed.
        """
        # Verify target is committed - Synthesis only makes sense for finalized structures
        target_result = self.target.get()
        if target_result:
            target_node, _ = target_result
            if not target_node.is_committed:
                raise ValueError(
                    f"Target {target_node.__class__.__name__} must be committed before "
                    "computing Synthesis structure hash. Commit the target first."
                )
        else:
            raise ValueError(
                "Synthesis must be connected to a target Perspective "
                "before computing structure hash."
            )

        parts = []

        # Get S+ hash
        sp_result = self.s_plus.get()
        if sp_result:
            comp, _ = sp_result
            if not comp.is_committed:
                raise ValueError(
                    "S+ component must be committed before computing Synthesis structure hash"
                )
            parts.append(comp.hash)

        # Get S- hash
        sm_result = self.s_minus.get()
        if sm_result:
            comp, _ = sm_result
            if not comp.is_committed:
                raise ValueError(
                    "S- component must be committed before computing Synthesis structure hash"
                )
            parts.append(comp.hash)

        return parts

    def __repr__(self) -> str:
        """String representation of the synthesis."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Synthesis({hash_str}, target_type={self.target_type})"

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

        # Map managers to their relationship types
        manager_to_rel_type = {
            id(self.s_plus): (self.s_plus, SPlusRelationship),
            id(self.s_minus): (self.s_minus, SMinusRelationship),
        }

        for manager_id, (manager, rel_class) in manager_to_rel_type.items():
            for component, rel in manager.all():
                # Skip non-polarity relationships
                if not isinstance(rel, PolarityRelationship):
                    continue

                # alias is guaranteed to be non-empty by PolarityRelationship validation
                old_alias = rel.alias  # Direct access, fully typed

                # Apply same logic as Perspective.set_human_friendly_index
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
                    # Update relationship property in place (no disconnect/reconnect needed)
                    manager.update_properties(component, {'alias': new_alias})

    def is_same(self, other: Synthesis) -> bool:
        """
        Check if this synthesis is the same as another synthesis.

        Compares by checking if both S+ and S- components match by UID.
        Two syntheses are considered the same if they contain the exact same
        S+/S- component pair, regardless of which Perspective they belong to.

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
        if self_sp and other_sp and self_sp[0].hash != other_sp[0].hash:
            return False

        # Compare S- components (exactly one each)
        self_sm = self.s_minus.get()
        other_sm = other.s_minus.get()

        if (self_sm is None) != (other_sm is None):
            return False
        if self_sm and other_sm and self_sm[0].hash != other_sm[0].hash:
            return False

        return True

    def __format__(self, format_spec: str) -> str:
        """
        Format this Synthesis using Python's format string protocol.

        Format Specifications:
        ----------------------

        Format: [mode][:newlines]

        Mode (optional):
            (empty) - Uses custom aliases as stored (e.g., "S1+", "S2-")
            "positions" - Uses canonical positions (S+, S-)
            "strip_index" - Strips numeric indexes: "S1+" → "S+", "Foo2-" → "Foo-"

        Newlines (optional):
            Default: 2 newlines between components (if not specified)
            :0 - Comma separation (compact single line)
            :1 - Single newline between components (compact)
            :2 - Double newline between components (spacious, default)

        Examples:
        ---------
        ""              - Default aliases, 2 newlines
        "positions"     - Canonical positions, 2 newlines
        "strip_index"   - Strip indexes, 2 newlines
        ":0"            - Default aliases, comma separated (single line)
        ":1"            - Default aliases, 1 newline (compact)
        "positions:0"   - Canonical positions, comma separated
        "positions:1"   - Canonical positions, 1 newline
        "strip_index:0" - Strip indexes, comma separated
        "strip_index:1" - Strip indexes, 1 newline

        Usage Examples:
        ---------------
        ```python
        # Default - aliases as stored, spacious (2 newlines)
        print(f"{synth}")
        # Output:
        #   S+ = Balance
        #   Explanation: ...
        #
        #   S- = Stagnation
        #   Explanation: ...

        # Compact - aliases as stored, single newline
        print(f"{synth::1}")

        # Comma separated - single line for compact display
        print(f"{synth::0}")
        # Output:
        #   S+ = Balance\nExplanation: ..., S- = Stagnation\nExplanation: ...
        ```

        Returns:
            Formatted string with S+ and S- components
        """
        import re

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

        # Validate newlines (allow 0 for comma separation, treat negative as 0)
        if newlines < 0:
            newlines = 0

        formatted_components = []

        # Format S+
        sp_result = self.s_plus.get()
        if sp_result:
            component, rel = sp_result
            # Synthesis relationships are always PolarityRelationship
            assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for S+, got {type(rel)}"
            alias = rel.alias  # Direct access, fully typed and validated

            # Apply mode formatting
            if mode == "positions":
                # Use canonical position name - we know it's S+ because we got it from s_plus
                alias = POSITION_S_PLUS
            elif mode == "strip_index":
                # Strip numeric index from alias using regex
                # Handles: "S1+" → "S+", "Foo2-" → "Foo-"
                alias = re.sub(r"(\d+)(?!.*\d)", "", alias)
            # else: empty mode - use alias as-is

            formatted_components.append(f"{alias} = {component}")

        # Format S-
        sm_result = self.s_minus.get()
        if sm_result:
            component, rel = sm_result
            # Synthesis relationships are always PolarityRelationship
            assert isinstance(rel, PolarityRelationship), f"Expected PolarityRelationship for S-, got {type(rel)}"
            alias = rel.alias  # Direct access, fully typed and validated

            # Apply mode formatting
            if mode == "positions":
                # Use canonical position name - we know it's S- because we got it from s_minus
                alias = POSITION_S_MINUS
            elif mode == "strip_index":
                # Strip numeric index from alias using regex
                alias = re.sub(r"(\d+)(?!.*\d)", "", alias)
            # else: empty mode - use alias as-is

            formatted_components.append(f"{alias} = {component}")

        # Join with specified separator
        if newlines < 1:
            separator = ", "  # Comma separation for compact single-line format
        else:
            separator = "\n" * newlines  # Newline separation for multi-line format
        return separator.join(formatted_components)

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")
