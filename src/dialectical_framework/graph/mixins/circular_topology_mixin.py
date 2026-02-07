"""
Mixin providing sequence topology methods for cycles, spirals, and transformations.

This mixin provides the `_transitions` relationship and common topology navigation methods
for any node class representing a circular structure (Cycle, Spiral, Wheel, Transformation).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal, ClassVar

from dialectical_framework.graph.relationship_manager import RelationshipManager, RelationshipFrom
from dialectical_framework.graph.relationships.belongs_to_cycle_relationship import (
    BelongsToCycleRelationship,
)
from dialectical_framework.utils.order_transitions import order_transitions

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.nexus import Nexus


class CircularTopologyMixin(ABC):
    """
    Abstract mixin providing topology methods and transitions relationship for circular structures.

    This mixin provides:
        - `_transitions` RelationshipManager (from Transition nodes)
        - `transitions` property returning ordered transitions
        - `dialectical_components` property for accessing components in order
        - `is_same_structure()` method for structural comparison

    Subclasses can override `_transitions` to change cardinality (e.g., Transformation uses (2,2)).

    Requires:
        - Subclass must implement `get_nexus()` method for alias resolution
    """

    # Transitions that form this circular structure
    # Subclasses can override to change cardinality (e.g., Transformation uses (2, 2))
    _transitions: ClassVar[RelationshipManager[Transition]] = RelationshipFrom(
        "Transition",
        model=BelongsToCycleRelationship,
        cardinality=(2, None)  # Default: at least two transitions to form a cycle
    )

    @property
    def transitions(self) -> list[Transition]:
        """
        Get transitions in order by following source->target chain.

        Returns:
            List of Transition nodes in order, or empty list if no transitions
        """
        all_transitions = [trans for trans, _ in self._transitions.all()]

        # Order by following source→target chain
        return order_transitions(all_transitions)

    @abstractmethod
    def get_nexus(self) -> Nexus | None:
        """
        Get the nexus this sequence belongs to.

        Subclasses must implement this to provide nexus context for alias resolution.
        The Nexus contains the WisdomUnits which hold component aliases.

        Returns:
            Nexus instance or None if not assigned to a nexus
        """
        ...

    @property
    def dialectical_components(self) -> list[DialecticalComponent]:
        """
        Returns list of dialectical components from the ordered transitions.

        Includes both source and target from each transition, but avoids duplicates
        where a transition's target matches the next transition's source (continuous chain).

        For Cycles (continuous): T1 → A1 → T2 → A2 returns [T1, A1, T2, A2]
        For Spirals (discrete): T1- → A1+, A1- → T2+ returns [T1-, A1+, A1-, T2+, T2-, A2+]

        Returns:
            List of DialecticalComponent nodes from the sequence
        """
        components = []
        transitions = self.transitions

        if not transitions:
            return []

        for i, trans in enumerate(transitions):
            source_result = trans.source.get()
            target_result = trans.target.get()

            if not source_result or not target_result:
                continue

            source_comp, _ = source_result
            target_comp, _ = target_result

            # Always add source
            components.append(source_comp)

            # Check if target matches next transition's source
            is_last = i == len(transitions) - 1
            if is_last:
                # Last transition: check if target is already in components (avoid duplicates)
                existing_ids = {comp._id for comp in components}
                if target_comp._id not in existing_ids:
                    components.append(target_comp)
                # Otherwise skip duplicate (common in closed cycles)
            else:
                # Check if target matches next source
                next_trans = transitions[i + 1]
                next_source_result = next_trans.source.get()

                if next_source_result:
                    next_source_comp, _ = next_source_result
                    if target_comp._id != next_source_comp._id:
                        # Discrete transition (target doesn't match next source)
                        components.append(target_comp)
                    # Otherwise skip target (continuous chain, will be added as next source)
                else:
                    # Can't check next source, add target to be safe
                    components.append(target_comp)

        return components

    def __format__(self, format_spec: str) -> str:
        """
        Format this sequence using Python's format string protocol.

        Format Specifications:
        ----------------------
        "" or "aliases" - Chains aliases like "T1 → T2 → T3 → T1..." (default)
        "statements"    - Uses component statements instead of aliases
        "explicit"      - Combines both: "T1 (statement) → T2 (statement) → T3 (statement) → T1..."

        Examples:
        ---------
        f"{cycle}"              - Default aliases: "T1 → A1 → T2 → T1..."
        f"{cycle:aliases}"      - Same as default
        f"{cycle:statements}"   - Statements: "Democracy → Fear → Courage → Democracy..."
        f"{cycle:explicit}"     - Explicit: "T1 (Democracy) → A1 (Fear) → T2 (Courage) → T1..."

        Returns:
            Formatted string representing the sequence, or empty string if no components
        """
        components = self.dialectical_components
        if not components:
            return ""

        # Determine mode
        mode = format_spec if format_spec else "aliases"

        # Try to get nexus context for alias resolution
        nexus = self.get_nexus()

        # Get aliases if needed for this mode
        aliases = []
        if mode in ("", "aliases", "explicit"):
            # Need aliases - try to get from nexus context
            if nexus:
                wisdom_units = [wu for wu, _ in nexus.wisdom_units.all()]
                for i, comp in enumerate(components):
                    alias = None
                    for wu in wisdom_units:
                        try:
                            alias = comp.get_alias(wu)
                            break  # Found it
                        except ValueError:
                            continue  # Not in this WU
                    aliases.append(alias if alias else f"C{i+1}")
            else:
                # No nexus context - fallback to statements for readability
                aliases = [comp.statement for comp in components]

        # Build labels based on mode
        if mode in ("", "aliases"):
            # Just aliases (or statements if no nexus context)
            labels = aliases
        elif mode == "statements":
            # Just statements
            labels = [comp.statement for comp in components]
        elif mode == "explicit":
            # Aliases with statements in parentheses
            if nexus:
                labels = [
                    f"{alias} ({comp.statement})"
                    for alias, comp in zip(aliases, components)
                ]
            else:
                # No nexus, aliases are already statements, so just use them
                labels = aliases
        else:
            raise ValueError(
                f"Invalid format_spec: {format_spec}. "
                f"Must be '', 'aliases', 'statements', or 'explicit'"
            )

        # Build sequence string
        if len(labels) == 1:
            return f"{labels[0]} → {labels[0]}..."

        return " → ".join(labels) + f" → {labels[0]}..."

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def is_same_structure(self, other: CircularTopologyMixin, compare: Literal['alias', 'statement'] = 'alias') -> bool:
        """
        Check if sequences represent the same structure regardless of starting point.

        Args:
            other: Another node with SequenceTopologyMixin to compare with
            compare: What to compare - 'alias' (default) or 'statement'
                    - 'alias': Compare by component aliases (requires nexus context)
                    - 'statement': Compare by component statement text

        Returns:
            True if both have same components in same order (allowing rotation)

        Raises:
            ValueError: If compare='alias' but nexus context not available
        """
        if not isinstance(other, CircularTopologyMixin):
            return False

        self_components = self.dialectical_components
        other_components = other.dialectical_components

        # Same length check
        if len(self_components) != len(other_components):
            return False

        if compare == 'alias':
            # Compare by aliases - requires nexus context
            self_nexus = self.get_nexus()
            other_nexus = other.get_nexus()

            if not self_nexus or not other_nexus:
                raise ValueError(
                    "Cannot compare by alias: nexus context not available. "
                    "Use compare='statement' or ensure cycles are connected to a nexus."
                )

            # Extract aliases from nexus context
            self_wisdom_units = [wu for wu, _ in self_nexus.wisdom_units.all()]
            other_wisdom_units = [wu for wu, _ in other_nexus.wisdom_units.all()]

            self_aliases = []
            for comp in self_components:
                alias = None
                for wu in self_wisdom_units:
                    try:
                        alias = comp.get_alias(wu)
                        break  # Found it
                    except ValueError:
                        continue  # Not in this WU
                if not alias:
                    raise ValueError(f"Component {comp.hash} has no alias in nexus context")
                self_aliases.append(alias)

            other_aliases = []
            for comp in other_components:
                alias = None
                for wu in other_wisdom_units:
                    try:
                        alias = comp.get_alias(wu)
                        break  # Found it
                    except ValueError:
                        continue  # Not in this WU
                if not alias:
                    raise ValueError(f"Component {comp.hash} has no alias in nexus context")
                other_aliases.append(alias)

            # Convert to sets for same elements check
            if set(self_aliases) != set(other_aliases):
                return False

            # Check rotations only if sets are equal
            if len(self_aliases) <= 1:
                return True

            return any(
                self_aliases == other_aliases[i:] + other_aliases[:i]
                for i in range(len(other_aliases))
            )

        elif compare == 'statement':
            # Compare by statements (legacy behavior)
            self_statements = [comp.statement for comp in self_components]
            other_statements = [comp.statement for comp in other_components]

            # Convert to sets for same elements check
            if set(self_statements) != set(other_statements):
                return False

            # Check rotations only if sets are equal
            if len(self_statements) <= 1:
                return True

            return any(
                self_statements == other_statements[i:] + other_statements[:i]
                for i in range(len(other_statements))
            )

        else:
            raise ValueError(f"Invalid compare parameter: {compare}. Must be 'alias' or 'statement'")
