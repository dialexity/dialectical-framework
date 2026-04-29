"""
Transition node for the dialectical framework.

This module provides the Transition class which represents relationships
between dialectical components (causal, convergence, transformation).
"""

from __future__ import annotations

import time
import uuid
from typing import ClassVar, TYPE_CHECKING, Literal, Optional, Any, Union, Self

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.relationship_manager import RelationshipFrom, RelationshipTo, RelationshipManager
from dialectical_framework.graph.relationships.is_source_of_relationship import (
    IsSourceOfRelationship,
)
from dialectical_framework.graph.relationships.is_target_of_relationship import (
    IsTargetOfRelationship,
)
from dialectical_framework.graph.relationships.belongs_to_cycle_relationship import (
    BelongsToCycleRelationship,
)
from dialectical_framework.graph.relationships.has_statement_relationship import (
    HasStatementRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.cycle import Cycle
    from dialectical_framework.graph.nodes.statement import Statement
    from dialectical_framework.graph.nodes.wheel import Wheel
    from dialectical_framework.graph.nodes.perspective import Perspective
    from dialectical_framework.graph.wheel_segment import WheelSegment


class Transition(AssessableEntity, label="Transition"):
    """
    Represents a transition (relationship) between dialectical components.

    Transitions are nodes (not edges) in the graph because they:
    1. Can be assessed/scored
    2. Have their own rationales
    3. Can have estimations (probability of transition)

    Relationships:
    - source: The source component (1:1)
    - target: The target component (1:1)
    - cycle: Container (Cycle or Wheel) for causal transitions (0:1)
    - Transformation positions (ac, re, ac_plus, etc.) use typed relationships

    Note: Default probability fallback is handled by the scorer (TaroRank.default_transition_probability)
    from settings, not stored on individual transition nodes.

    Nonce Field:
        Transitions include a `nonce` (number used once) in their hash computation.
        This is necessary because:

        1. Transition hash = source_hash + target_hash + nonce
        2. Without nonce, all A→B transitions would have identical hashes
        3. Container hash can't be included (circular dependency: container hash
           is computed FROM transition hashes via IncrementalBuildMixin)
        4. Each Transition belongs to exactly one container (1:1 cardinality),
           so they can't be shared - each needs a unique hash

        The nonce has no semantic meaning; it exists solely to ensure hash uniqueness
        across transitions with identical source→target pairs in different containers.
    """

    # Nonce for hash uniqueness - see class docstring for explanation
    nonce: str

    # Instructive label describing the transformation path
    # e.g. "Establish boundaries to enable autonomy"
    instruction: Optional[str] = None

    # User-facing cosmetic override for instruction.
    # Does NOT affect hash computation — mutable post-commit.
    # When set, UI/reports/prompts render this instead of `instruction`.
    display_instruction: Optional[str] = None

    @property
    def prompt_instruction(self) -> str | None:
        """Instruction for LLM prompts: includes both display and canonical text when they differ."""
        if self.display_instruction and self.instruction and self.display_instruction != self.instruction:
            return f"{self.display_instruction} (derived from: {self.instruction})"
        return self.instruction

    def __init__(self, **data: Any) -> None:
        # Auto-generate nonce if not provided
        if "nonce" not in data:
            data["nonce"] = str(uuid.uuid4())
        super().__init__(**data)

    # Hash inputs - set these before save() to include in hash
    # These are used for hash computation; actual relationships are created post-save
    _source_hash: Optional[str] = None
    _target_hash: Optional[str] = None
    # Transient refs for auto-connecting after save (not persisted)
    _source_ref: Optional[Statement] = None
    _target_ref: Optional[Statement] = None

    source: ClassVar[RelationshipManager[Statement]] = RelationshipFrom(
        "Statement",
        model=IsSourceOfRelationship,
        cardinality=(1, 1)
    )

    target: ClassVar[RelationshipManager[Statement]] = RelationshipTo(
        "Statement",
        model=IsTargetOfRelationship,
        cardinality=(1, 1)
    )

    # Container for this transition (Cycle or Wheel)
    # Note: Transformation transitions use typed relationships (ac, re, ac_plus, etc.) instead
    cycle: ClassVar[RelationshipManager[Cycle | Wheel]] = RelationshipTo(
        ("Cycle", "Wheel"),
        model=BelongsToCycleRelationship,
        cardinality=(0, 1)  # Optional - Transformation transitions use typed relationships
    )

    # Vocabulary-grade DCs derived from the instruction (lazy, added by concerns)
    statements: ClassVar[RelationshipManager[Statement]] = RelationshipTo(
        "Statement",
        model=HasStatementRelationship,
        cardinality=(0, None),
    )


    def set_source(self, component: Statement) -> Transition:
        """
        Set the source component for this transition (before save).

        This stores the reference for hash computation and auto-connection after save.
        The component must already be saved (have hash).

        Args:
            component: The saved source component

        Returns:
            Self for chaining
        """
        if not component.is_committed:
            raise ValueError("Source component must be saved before setting on transition")
        self._source_hash = component.hash
        self._source_ref = component
        return self

    def set_target(self, component: Statement) -> Transition:
        """
        Set the target component for this transition (before save).

        This stores the reference for hash computation and auto-connection after save.
        The component must already be saved (have hash).

        Args:
            component: The saved target component

        Returns:
            Self for chaining
        """
        if not component.is_committed:
            raise ValueError("Target component must be saved before setting on transition")
        self._target_hash = component.hash
        self._target_ref = component
        return self

    def _get_perspectives(self) -> list[Perspective]:
        """
        Get Perspectives for alias resolution via the container chain.

        Follows: Transition → Wheel → Cycle → perspectives
              or Transition → Cycle → perspectives

        Returns:
            List of Perspectives, or empty list if not found
        """
        cycle_result = self.cycle.get()
        if not cycle_result:
            return []

        container, _ = cycle_result

        # For Wheel: get from cycle.perspectives
        from dialectical_framework.graph.nodes.wheel import Wheel
        if isinstance(container, Wheel):
            cycle_res = container.cycle.get()
            if cycle_res:
                cycle_obj, _ = cycle_res
                return cycle_obj.perspectives
            return []

        # For Cycle: get perspectives directly
        from dialectical_framework.graph.nodes.cycle import Cycle
        if isinstance(container, Cycle):
            return container.perspectives

        return []

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Transition.

        Parts: source hash, target hash, nonce.
        The nonce ensures each Transition instance is unique even with
        the same source→target pair.

        Returns:
            List of strings: [source_hash, target_hash, nonce]

        Raises:
            ValueError: If source or target is not set/committed
        """
        parts = []

        # Get source hash - prefer stored hash, fall back to relationship
        source_hash = self._source_hash
        if not source_hash:
            source_result = self.source.get()
            if source_result:
                comp, _ = source_result
                if not comp.is_committed:
                    raise ValueError(
                        "Source component must be saved before computing Transition hash"
                    )
                source_hash = comp.hash
        if source_hash:
            parts.append(source_hash)

        # Get target hash - prefer stored hash, fall back to relationship
        target_hash = self._target_hash
        if not target_hash:
            target_result = self.target.get()
            if target_result:
                comp, _ = target_result
                if not comp.is_committed:
                    raise ValueError(
                        "Target component must be saved before computing Transition hash"
                    )
                target_hash = comp.hash
        if target_hash:
            parts.append(target_hash)

        # Require source + target for a meaningful hash
        if len(parts) < 2:
            raise ValueError(
                "Transition requires source and target to be set before save. "
                "Use set_source() and set_target()."
            )

        # Include nonce to ensure each Transition instance is unique
        parts.append(self.nonce)

        return parts

    @inject
    def commit(
        self,
        graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]
    ) -> Self:
        """
        Commit this transition: save (if needed), create relationships, compute hash.

        If source/target were set via set_source()/set_target(), relationships
        are created BEFORE computing the hash (since they are structural).
        The hash includes source_hash and target_hash stored from set_source()/set_target().

        Returns:
            Self for chaining
        """
        if self.is_committed:
            from dialectical_framework.graph.nodes.base_node import ImmutableNodeError
            raise ImmutableNodeError(
                f"Node already committed with hash {self.hash[:7]}..."
            )

        # Ensure node is saved (has _id) before connecting relationships
        if self._id is None:
            result = graph_db.save_node(self)
            if result is not None and result._id is not None:
                self._id = result._id

        # Connect structural relationships BEFORE computing hash (while node is still mutable)
        # The stored _source_hash/_target_hash will be used for hash computation
        if self._source_ref:
            self.source.connect(self._source_ref)
            self._source_ref = None  # Clear transient ref
        if self._target_ref:
            self.target.connect(self._target_ref)
            self._target_ref = None  # Clear transient ref

        # Set committed_at BEFORE computing hash (it's part of the hash)
        self.committed_at = time.time()
        self.hash = self.compute_hash()

        # Update in DB with hash
        graph_db.save_node(self)

        return self

    def _find_pp_for_component(self, component: Statement) -> Perspective | None:
        """
        Find which Perspective contains this component.

        Searches through all Perspectives via _get_perspectives() to find the one
        containing the given component.

        Args:
            component: The dialectical component to find

        Returns:
            The Perspective containing this component, or None if not found
        """
        perspectives = self._get_perspectives()
        if not perspectives:
            return None

        for pp in perspectives:
            try:
                component.get_alias(pp)
                return pp
            except ValueError:
                continue

        return None

    def get_source_wheel_segment(self) -> WheelSegment | None:
        """
        Get the wheel segment containing the source component.

        Returns:
            WheelSegment containing the source component, or None if not found
        """
        source_result = self.source.get()
        if not source_result:
            return None

        source_comp, _ = source_result
        pp = self._find_pp_for_component(source_comp)
        if not pp:
            return None

        # Determine which side (T or A) based on component's position
        position = source_comp.get_position(pp)
        if not position:
            return None

        # Positions starting with 'T' are T-side, starting with 'A' are A-side
        side: Literal["T", "A"] = "T" if position.startswith("T") else "A"

        # Import here to avoid circular dependency at module level
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(pp, side)

    def get_target_wheel_segment(self) -> WheelSegment | None:
        """
        Get the wheel segment containing the target component.

        Returns:
            WheelSegment containing the target component, or None if not found
        """
        target_result = self.target.get()
        if not target_result:
            return None

        target_comp, _ = target_result
        pp = self._find_pp_for_component(target_comp)
        if not pp:
            return None

        # Determine which side (T or A) based on component's position
        position = target_comp.get_position(pp)
        if not position:
            return None

        # Positions starting with 'T' are T-side, starting with 'A' are A-side
        side: Literal["T", "A"] = "T" if position.startswith("T") else "A"

        # Import here to avoid circular dependency at module level
        from dialectical_framework.graph.wheel_segment import WheelSegment
        return WheelSegment(pp, side)

    @staticmethod
    def _get_component_label(
        comp: Statement,
        mode: str,
        perspectives: list[Perspective] | None
    ) -> str:
        """
        Get label for a component based on format mode.

        Args:
            comp: The dialectical component
            mode: Format mode ("aliases", "statements", "explicit")
            perspectives: Optional list of Perspectives for alias resolution

        Returns:
            Formatted label string
        """
        alias = None

        # Try to resolve alias through Perspective context
        if perspectives and mode in ("", "aliases", "explicit"):
            for pp in perspectives:
                try:
                    alias = comp.get_alias(pp)
                    break
                except ValueError:
                    continue

        # Build label based on mode
        display = comp.display_text or comp.text
        if mode == "statements":
            return display
        elif mode == "explicit":
            if alias:
                return f"{alias} ({display})"
            else:
                return display
        else:  # "" or "aliases"
            if alias:
                return alias
            else:
                # Fallback to truncated identity if no alias found
                return comp.hash[:8]

    def _is_segment_transition(self) -> bool:
        """
        Check if this transition has segment semantics (Transformation).

        Returns:
            True if transition is in a Transformation container
        """
        from dialectical_framework.graph.nodes.transformation import Transformation

        cycle_result = self.cycle.get()
        if not cycle_result:
            return False

        container, _ = cycle_result
        return isinstance(container, Transformation)

    def _get_segment_source_labels(
        self,
        source_comp: Statement,
        mode: str,
        perspectives: list[Perspective] | None
    ) -> str:
        """
        Get source labels for segment-based transitions (Transformation).

        For segment transitions, source is represented by minus AND core components
        (e.g., "T1-, T1" not just "T1-").

        Args:
            source_comp: The source component (minus component)
            mode: Format mode
            perspectives: Optional list of Perspectives for alias resolution

        Returns:
            Formatted source label with segment aliases (e.g., "T1-, T1")
        """
        # Find the segment containing this source component
        source_segment = self.get_source_wheel_segment()
        if not source_segment:
            return self._get_component_label(source_comp, mode, perspectives)

        pp = source_segment.perspective

        # Get the minus and core components from the segment
        # Source component should be the minus (T- or A-)
        if source_segment.side == "T":
            minus_result = pp.t_minus.get()
            core_result = pp.t.get()
        else:  # A-side
            minus_result = pp.a_minus.get()
            core_result = pp.a.get()

        if not minus_result or not core_result:
            return self._get_component_label(source_comp, mode, perspectives)

        minus_comp, _ = minus_result
        core_comp, _ = core_result

        # Get labels for both components
        minus_label = self._get_component_label(minus_comp, mode, perspectives)
        core_label = self._get_component_label(core_comp, mode, perspectives)

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

        For Transformation transitions, source shows segment aliases:
        - Cycle: "T1- → A1+" (component-to-component)
        - Transformation: "T1-, T1 → A1+" (segment-to-component)

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
            return f"Transition(id={self.hash})"

        source_comp, _ = source_result
        target_comp, _ = target_result

        # Get Perspectives for alias resolution (replaces nexus)
        perspectives = self._get_perspectives()

        # Normalize mode
        mode = format_spec if format_spec else "aliases"

        # Check if this is a segment transition (Transformation)
        is_segment = self._is_segment_transition()

        # Helper to get source label (segment or component based)
        def get_source_label(label_mode: str) -> str:
            if is_segment and label_mode != "statements":
                return self._get_segment_source_labels(source_comp, label_mode, perspectives)
            return self._get_component_label(source_comp, label_mode, perspectives)

        if mode == "verbose":
            # Verbose: aliases + rationale
            source_label = get_source_label("aliases")
            target_label = self._get_component_label(target_comp, "aliases", perspectives)

            result = f"{source_label} → {target_label}"

            # Add explicit format on new line
            source_explicit = get_source_label("explicit")
            target_explicit = self._get_component_label(target_comp, "explicit", perspectives)
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
            target_label = self._get_component_label(target_comp, mode, perspectives)
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
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Transition({hash_str})"
