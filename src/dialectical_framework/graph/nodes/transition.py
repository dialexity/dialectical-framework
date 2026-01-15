"""
Transition node for the dialectical framework.

This module provides the Transition class which represents relationships
between dialectical components (causal, convergence, transformation).
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING, Literal

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.branching_relationship import BranchingRelationship

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.spiral import Spiral
    from dialectical_framework.graph.nodes.transformation import Transformation
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.wheel_segment import WheelSegment
    from dialectical_framework.graph.growth.sprout import Sprout


class Transition(AssessableEntity):
    """
    Represents a transition (relationship) between dialectical components.

    Transitions capture different types of relationships between components:
    - CAUSES: Causal transitions organized in Cycles
    - CONSTRUCTIVELY_CONVERGES_TO: Synthesis convergence organized in Spirals
    - TRANSFORMS_TO: Dialectical transformations organized in Transformations

    The semantic type of transition is implicit from its container:
    - Transitions in Cycle → CAUSES
    - Transitions in Spiral → CONSTRUCTIVELY_CONVERGES_TO
    - Transitions in Transformation → TRANSFORMS_TO

    Transitions are nodes (not edges) in the graph because they:
    1. Can be assessed/scored
    2. Have their own rationales
    3. Can have estimations (probability of transition)
    4. Are organized into Cycles, Spirals, and Transformations

    Relationships:
    - source: The representative component from the source wheel segment (1:1)
    - target: The representative component from the target wheel segment (1:1)
    - cycle: The container (Cycle, Spiral, or Transformation) this transition belongs to (0:1)

    Note: Default probability fallback is handled by the scorer (TaroRank.default_transition_probability)
    from settings, not stored on individual transition nodes.
    """

    source: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipFrom(
        "DialecticalComponent",
        "IS_SOURCE_OF",
        cardinality=(1, 1)
    )

    target: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "IS_TARGET_OF",
        cardinality=(1, 1)
    )

    cycle: ClassVar[RelationshipManager[Cycle | Spiral | Transformation]] = RelationshipTo(
        ("Cycle", "Spiral", "Transformation"),
        "BELONGS_TO_CYCLE",
        cardinality=(0, 1)
    )

    derived_statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "HAS_STATEMENT",
        cardinality=(0, None)
    )

    # Branches from this transition (spawns new statements via Sprout)
    branches: ClassVar[RelationshipManager[Sprout]] = RelationshipTo(
        "Sprout",
        model=BranchingRelationship,
        cardinality=(0, None)
    )

    def get_wheel(self) -> Wheel | None:
        """
        Get the wheel this transition belongs to via its cycle/spiral.

        Returns:
            The wheel containing this transition's cycle, or None if not found
        """
        cycle_result = self.cycle.get()
        if not cycle_result:
            return None

        container, _ = cycle_result
        return container.get_wheel()

    def get_source_wheel_segment(self, wheel: Wheel = None) -> WheelSegment | None:
        """
        Get the wheel segment containing the source component.

        Args:
            wheel: Optional wheel to use. If not provided, gets wheel from transition's cycle.

        Returns:
            WheelSegment containing the source component, or None if not found
        """
        if wheel is None:
            wheel = self.get_wheel()
        if not wheel:
            return None

        source_result = self.source.get()
        if not source_result:
            return None

        source_comp, _ = source_result
        wu = wheel.wisdom_unit_at(source_comp)
        if not wu:
            return None

        # Determine which side (T or A) based on component's position
        position = source_comp.get_position(wu)
        if not position:
            return None

        # Positions starting with 'T' are T-side, starting with 'A' are A-side
        side: Literal["T", "A"] = "T" if position.startswith("T") else "A"

        # Import here to avoid circular dependency at module level
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(wu, side)

    def get_target_wheel_segment(self, wheel: Wheel = None) -> WheelSegment | None:
        """
        Get the wheel segment containing the target component.

        Args:
            wheel: Optional wheel to use. If not provided, gets wheel from transition's cycle.

        Returns:
            WheelSegment containing the target component, or None if not found
        """
        if wheel is None:
            wheel = self.get_wheel()
        if not wheel:
            return None

        target_result = self.target.get()
        if not target_result:
            return None

        target_comp, _ = target_result
        wu = wheel.wisdom_unit_at(target_comp)
        if not wu:
            return None

        # Determine which side (T or A) based on component's position
        position = target_comp.get_position(wu)
        if not position:
            return None

        # Positions starting with 'T' are T-side, starting with 'A' are A-side
        side: Literal["T", "A"] = "T" if position.startswith("T") else "A"

        # Import here to avoid circular dependency at module level
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(wu, side)

    @staticmethod
    def _get_component_label(
        comp: DialecticalComponent,
        mode: str,
        wheel: Wheel | None
    ) -> str:
        """
        Get label for a component based on format mode.

        Args:
            comp: The dialectical component
            mode: Format mode ("aliases", "statements", "explicit")
            wheel: Optional wheel for alias resolution

        Returns:
            Formatted label string
        """
        alias = None

        # Try to resolve alias through wheel context
        if wheel and mode in ("", "aliases", "explicit"):
            wisdom_units = [wu for wu, _ in wheel.wisdom_units.all()]
            for wu in wisdom_units:
                try:
                    alias = comp.get_alias(wu)
                    break
                except ValueError:
                    continue

        # Build label based on mode
        if mode == "statements":
            return comp.statement
        elif mode == "explicit":
            if alias:
                return f"{alias} ({comp.statement})"
            else:
                return comp.statement
        else:  # "" or "aliases"
            if alias:
                return alias
            else:
                # Fallback to truncated UID if no alias found
                return comp.uid[:8]

    def _is_segment_transition(self) -> bool:
        """
        Check if this transition has segment semantics (Spiral/Transformation).

        Returns:
            True if transition is in a Spiral or Transformation container
        """
        from dialectical_framework.graph.nodes.spiral import Spiral
        from dialectical_framework.graph.nodes.transformation import Transformation

        cycle_result = self.cycle.get()
        if not cycle_result:
            return False

        container, _ = cycle_result
        return isinstance(container, (Spiral, Transformation))

    def _get_segment_source_labels(
        self,
        source_comp: DialecticalComponent,
        mode: str,
        wheel: Wheel | None
    ) -> str:
        """
        Get source labels for segment-based transitions (Spiral/Transformation).

        For segment transitions, source is represented by minus AND core components
        (e.g., "T1-, T1" not just "T1-").

        Args:
            source_comp: The source component (minus component)
            mode: Format mode
            wheel: Optional wheel for alias resolution

        Returns:
            Formatted source label with segment aliases (e.g., "T1-, T1")
        """
        if not wheel:
            return self._get_component_label(source_comp, mode, wheel)

        # Find the segment containing this source component
        source_segment = self.get_source_wheel_segment(wheel)
        if not source_segment:
            return self._get_component_label(source_comp, mode, wheel)

        wu = source_segment.wisdom_unit

        # Get the minus and core components from the segment
        # Source component should be the minus (T- or A-)
        if source_segment.side == "T":
            minus_result = wu.t_minus.get()
            core_result = wu.t.get()
        else:  # A-side
            minus_result = wu.a_minus.get()
            core_result = wu.a.get()

        if not minus_result or not core_result:
            return self._get_component_label(source_comp, mode, wheel)

        minus_comp, _ = minus_result
        core_comp, _ = core_result

        # Get labels for both components
        minus_label = self._get_component_label(minus_comp, mode, wheel)
        core_label = self._get_component_label(core_comp, mode, wheel)

        return f"{minus_label}, {core_label}"

    def __format__(self, format_spec: str) -> str:
        """
        Format this Transition using Python's format string protocol.

        Format Specifications:
        ----------------------
        "" or "aliases"   - Shows "source_alias → target_alias" (e.g., "T1- → A1+")
        "statements"      - Shows "source_statement → target_statement"
        "explicit"        - Combines both: "T1- (statement) → A1+ (statement)"
        "verbose"         - Shows alias format + rationale text

        For Spiral/Transformation transitions, source shows segment aliases:
        - Cycle: "T1- → A1+" (component-to-component)
        - Spiral/Transformation: "T1-, T1 → A1+" (segment-to-component)

        Examples:
        ---------
        f"{transition}"           - Default: "T1- → A1+" or "T1-, T1 → A1+"
        f"{transition:statements}" - Statements: "Negative aspect → Positive aspect"
        f"{transition:explicit}"  - Explicit: "T1- (statement) → A1+ (statement)"
        f"{transition:verbose}"   - Verbose: "T1-, T1 → A1+\\nRationale: ..."

        Returns:
            Formatted string representing the transition
        """
        # Get source and target components
        source_result = self.source.get()
        target_result = self.target.get()

        if not source_result or not target_result:
            return f"Transition(uid={self.uid})"

        source_comp, _ = source_result
        target_comp, _ = target_result

        # Get wheel context for alias resolution
        wheel = self.get_wheel()

        # Normalize mode
        mode = format_spec if format_spec else "aliases"

        # Check if this is a segment transition (Spiral/Transformation)
        is_segment = self._is_segment_transition()

        # Helper to get source label (segment or component based)
        def get_source_label(label_mode: str) -> str:
            if is_segment and label_mode != "statements":
                return self._get_segment_source_labels(source_comp, label_mode, wheel)
            return self._get_component_label(source_comp, label_mode, wheel)

        if mode == "verbose":
            # Verbose: aliases + rationale
            source_label = get_source_label("aliases")
            target_label = self._get_component_label(target_comp, "aliases", wheel)

            result = f"{source_label} → {target_label}"

            # Add explicit format on new line
            source_explicit = get_source_label("explicit")
            target_explicit = self._get_component_label(target_comp, "explicit", wheel)
            result = f"{result}\n{source_explicit} → {target_explicit}"

            # Add rationales
            rationales = list(self.rationales.all())
            if rationales:
                if len(rationales) > 1:
                    explanations = []
                    for idx, (rationale, _) in enumerate(rationales, 1):
                        if rationale.text:
                            explanations.append(f"Rationale {idx}: {rationale.text}")
                    if explanations:
                        result = f"{result}\n" + "\n".join(explanations)
                else:
                    rationale, _ = rationales[0]
                    if rationale.text:
                        result = f"{result}\nRationale: {rationale.text}"
            else:
                result = f"{result}\nRationale: N/A"

            return result

        elif mode in ("", "aliases", "statements", "explicit"):
            source_label = get_source_label(mode)
            target_label = self._get_component_label(target_comp, mode, wheel)
            return f"{source_label} → {target_label}"

        else:
            raise ValueError(
                f"Invalid format_spec: {format_spec}. "
                f"Must be '', 'aliases', 'statements', 'explicit', or 'verbose'"
            )

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def __repr__(self) -> str:
        """Debug representation of the transition."""
        return f"Transition(uid={self.uid})"
