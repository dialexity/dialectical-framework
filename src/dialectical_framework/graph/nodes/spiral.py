"""
Spiral node for the dialectical framework.

This module provides the Spiral class which represents transformational
spirals composed of transformation transitions.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipTo, RelationshipFrom, RelationshipManager
from dialectical_framework.graph.relationships.is_spiral_of_relationship import (
    IsSpiralOfRelationship,
)
from dialectical_framework.graph.relationships.synthesis_of_relationship import (
    SynthesisOfRelationship,
)
from dialectical_framework.graph.mixins.circular_topology_mixin import CircularTopologyMixin

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.nexus import Nexus
    from dialectical_framework.graph.nodes.synthesis import Synthesis


class Spiral(CircularTopologyMixin, AssessableEntity):
    """
    Represents a transformational spiral in the dialectical framework.

    A Spiral is an analytical interpretation - a directed graph of transitions
    that captures dialectical evolution and synthesis pathways. Spirals are
    "drawn on" a wheel to show transformational relationships that lead to synthesis.

    Unlike Cycles which track causal relationships between components, Spirals
    track transformational relationships that represent upward movement in
    dialectical reasoning, where thesis and antithesis are transformed through
    synthesis into higher-order understanding.

    Relationship to Wheel:
    - A wheel can have one primary/canonical spiral (wheel.spiral)
    - Alternative spiral interpretations can also reference the same wheel
    - Spirals can exist independently or be created after the wheel
    """

    # Note: transitions relationship is inherited from CircularTopologyMixin as _transitions
    # Access via .transitions property which returns ordered list

    wheel: ClassVar[RelationshipManager[Wheel]] = RelationshipTo(
        "Wheel",
        model=IsSpiralOfRelationship,
        cardinality=(1, 1)  # Spiral is always drawn on a wheel
    )

    # Meta-synthesis alternatives (S+/S- pairs) derived from this spiral
    synthesis: ClassVar[RelationshipManager[Synthesis]] = RelationshipFrom(
        "Synthesis",
        model=SynthesisOfRelationship,
        cardinality=(0, None)  # Zero or more synthesis alternatives
    )

    def get_nexus(self) -> Nexus | None:
        """
        Get the nexus this spiral belongs to via its Wheel→Cycle→Nexus path.

        Returns:
            Nexus instance or None if not connected

        Example:
            nexus = spiral.get_nexus()
            if nexus:
                print(f"Spiral's source nexus has {nexus.wisdom_units.count()} WUs")
        """
        wheel_result = self.wheel.get()
        if not wheel_result:
            return None
        wheel_obj, _ = wheel_result
        return wheel_obj.get_nexus()

    def __format__(self, format_spec: str) -> str:
        """
        Format this Spiral using Python's format string protocol.

        Spirals have discrete transitions (T1- ↘ A1+, A1- ↘ T2+, ...) where each
        transition's target doesn't match the next transition's source, so we show
        them separated by middle dots (·).

        Format Specifications:
        ----------------------
        "" or "aliases" - Shows discrete transitions with cycle closure: "T1- ↘ A1+ · ... ↘ T1-..." (default)
        "statements"    - Uses component statements instead of aliases
        "explicit"      - Combines both: "T1- (statement) ↘ A1+ (statement) · ..."
        "verbose"       - Shows sequence and rationales: "Spiral: T1- ↘ A1+ · ...\nRationale: ..."

        Examples:
        ---------
        f"{spiral}"              - Default: "T1- ↘ A1+ · A1- ↘ T2+ · T2- ↘ A2+ · A2- ↘ T1+ ↘ T1-..."
        f"{spiral:statements}"   - With statements
        f"{spiral:explicit}"     - Aliases with statements
        f"{spiral:verbose}"      - Verbose: "Spiral: T1- ↘ A1+ · ...\nRationale: ..."

        Returns:
            Formatted string with discrete transitions separated by middle dots
        """
        if format_spec == "verbose":
            # Verbose mode: show "Spiral:" + sequence + rationales
            result = "Spiral: "

            # Add sequence using aliases mode
            sequence = self.__format__("aliases")
            result += sequence
            result = f"{result}\n{self.__format__('explicit')}"

            # Add rationales
            rationales = list(self.rationales.all())
            if rationales:
                # Multiple rationales - number them
                if len(rationales) > 1:
                    explanations = []
                    for idx, (rationale, _) in enumerate(rationales, 1):
                        if rationale.text:
                            explanations.append(f"Rationale {idx}: {rationale.text}")
                    if explanations:
                        result = f"{result}\n" + "\n".join(explanations)
                # Single rationale - no number
                else:
                    rationale, _ = rationales[0]
                    if rationale.text:
                        result = f"{result}\nRationale: {rationale.text}"
            else:
                # No rationales
                result = f"{result}\nRationale: N/A"

            return result

        # Non-verbose modes: build transition sequence
        transitions = self.transitions
        if not transitions:
            return ""

        # Determine mode
        mode = format_spec if format_spec else "aliases"

        # Try to get nexus context for alias resolution
        nexus = self.get_nexus()
        wisdom_units = []
        if nexus:
            wisdom_units = [wu for wu, _ in nexus.wisdom_units.all()]

        # Helper to get label for a component
        def get_label(comp) -> str:
            if mode in ("", "aliases", "explicit"):
                # Need alias - try to get from wheel context
                alias = None
                if wisdom_units:
                    for wu in wisdom_units:
                        try:
                            alias = comp.get_alias(wu)
                            break  # Found it
                        except ValueError:
                            continue  # Not in this WU

                # Use alias or fallback
                if mode == "explicit":
                    return f"{alias or comp.uid[:8]} ({comp.statement})"
                else:
                    return alias or comp.uid[:8]
            elif mode == "statements":
                return comp.statement
            else:
                raise ValueError(
                    f"Invalid format_spec: {format_spec}. "
                    f"Must be '', 'aliases', 'statements', or 'explicit'"
                )

        # Build list of discrete transitions
        transition_strs = []
        first_source_label = None

        for i, trans in enumerate(transitions):
            source_result = trans.source.get()
            target_result = trans.target.get()

            if source_result and target_result:
                source_comp, _ = source_result
                target_comp, _ = target_result

                source_label = get_label(source_comp)
                target_label = get_label(target_comp)

                # Remember first source for closure
                if i == 0:
                    first_source_label = source_label

                transition_strs.append(f"{source_label} ↘ {target_label}")

        if not transition_strs:
            return ""

        # Join with middle dot and add cycle closure
        result = " · ".join(transition_strs)

        # Show it's cyclical by pointing back to first source
        if first_source_label:
            result += f" · {first_source_label}..."

        return result

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def __repr__(self) -> str:
        """Debug representation of the spiral."""
        return f"Spiral(uid={self.uid})"
