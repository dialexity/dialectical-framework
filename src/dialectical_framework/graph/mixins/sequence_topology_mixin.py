"""
Mixin providing sequence topology methods for cycles, spirals, and transformations.

This mixin can be used by any node class that has a `transitions` relationship
to provide common topology navigation methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

from dialectical_framework.graph.utils.order_transitions import order_transitions

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.transition import Transition
    from dialectical_framework.graph.nodes.wheel import Wheel


class SequenceTopologyMixin(ABC):
    """
    Abstract mixin providing topology methods for nodes with transitions.

    Any node class with a `transitions` RelationshipManager can use this mixin
    to get topology navigation methods.

    Requires:
        - Subclass must have a `transitions` RelationshipManager attribute
        - Subclass must implement `get_wheel()` method
    """

    @property
    def transitions_ordered(self) -> list[Transition]:
        """
        Get transitions in order by following source->target chain.

        This implementation works for any class with a `transitions` RelationshipManager.

        Returns:
            List of Transition nodes in order, or empty list if no transitions

        Raises:
            AttributeError: If the subclass does not have a `transitions` attribute
        """
        if not hasattr(self, 'transitions'):
            raise AttributeError(
                f"{self.__class__.__name__} must have a 'transitions' RelationshipManager "
                f"attribute to use SequenceTopologyMixin"
            )
        all_transitions = [trans for trans, _ in self.transitions.all()]  # type: ignore[attr-defined]
        return order_transitions(all_transitions)

    @abstractmethod
    def get_wheel(self) -> Wheel | None:
        """
        Get the wheel this sequence belongs to.

        Subclasses must implement this to provide wheel context for alias resolution.
        Database connection is handled via dependency injection within implementations.

        Returns:
            Wheel instance or None if not assigned to a wheel
        """
        ...

    @property
    def dialectical_components(self) -> list[DialecticalComponent]:
        """
        Returns list of dialectical components from the ordered transitions.

        Returns:
            List of DialecticalComponent nodes (source components from each transition)
        """
        components = []
        for trans in self.transitions_ordered:
            source_nodes = [src for src, _ in trans.source.all()]
            if source_nodes:
                components.append(source_nodes[0])

        return components

    def __format__(self, format_spec: str) -> str:
        """
        Format this sequence using Python's format string protocol.

        Format Specifications:
        ----------------------
        "" or "aliases" - Chains aliases like "T1 → T2 → T3 → T1..." (default)
        "statements"    - Uses component statements instead of aliases
        "verbose"       - Combines both: "T1 (statement) → T2 (statement) → T3 (statement) → T1..."

        Examples:
        ---------
        f"{cycle}"              - Default aliases: "T1 → A1 → T2 → T1..."
        f"{cycle:aliases}"      - Same as default
        f"{cycle:statements}"   - Statements: "Democracy → Fear → Courage → Democracy..."
        f"{cycle:verbose}"      - Verbose: "T1 (Democracy) → A1 (Fear) → T2 (Courage) → T1..."

        Returns:
            Formatted string representing the sequence, or empty string if no components
        """
        components = self.dialectical_components
        if not components:
            return ""

        # Determine mode
        mode = format_spec if format_spec else "aliases"

        # Try to get wheel context for alias resolution
        wheel = self.get_wheel()

        # Get aliases if needed for this mode
        aliases = []
        if mode in ("", "aliases", "verbose"):
            # Need aliases - try to get from wheel context
            if wheel:
                wisdom_units = [wu for wu, _ in wheel.wisdom_units.all()]
                for i, comp in enumerate(components):
                    alias = None
                    for wu in wisdom_units:
                        alias = comp.get_alias(wu)
                        if alias:
                            break
                    aliases.append(alias if alias else f"C{i+1}")
            else:
                # Fallback to generic labels
                aliases = [f"C{i+1}" for i in range(len(components))]

        # Build labels based on mode
        if mode in ("", "aliases"):
            # Just aliases
            labels = aliases
        elif mode == "statements":
            # Just statements
            labels = [comp.statement for comp in components]
        elif mode == "verbose":
            # Aliases with statements in parentheses
            labels = [
                f"{alias} ({comp.statement})"
                for alias, comp in zip(aliases, components)
            ]
        else:
            raise ValueError(
                f"Invalid format_spec: {format_spec}. "
                f"Must be '', 'aliases', 'statements', or 'verbose'"
            )

        # Build sequence string
        if len(labels) == 1:
            return f"{labels[0]} → {labels[0]}..."

        return " → ".join(labels) + f" → {labels[0]}..."

    def __str__(self) -> str:
        """String representation using default format."""
        return self.__format__("")

    def is_same_structure(self, other: SequenceTopologyMixin, compare: Literal['alias', 'statement'] = 'alias') -> bool:
        """
        Check if sequences represent the same structure regardless of starting point.

        Args:
            other: Another node with SequenceTopologyMixin to compare with
            compare: What to compare - 'alias' (default) or 'statement'
                    - 'alias': Compare by component aliases (requires wheel context)
                    - 'statement': Compare by component statement text

        Returns:
            True if both have same components in same order (allowing rotation)

        Raises:
            ValueError: If compare='alias' but wheel context not available
        """
        if not isinstance(other, SequenceTopologyMixin):
            return False

        self_components = self.dialectical_components
        other_components = other.dialectical_components

        # Same length check
        if len(self_components) != len(other_components):
            return False

        if compare == 'alias':
            # Compare by aliases - requires wheel context
            self_wheel = self.get_wheel()
            other_wheel = other.get_wheel()

            if not self_wheel or not other_wheel:
                raise ValueError(
                    "Cannot compare by alias: wheel context not available. "
                    "Use compare='statement' or ensure cycles are connected to wheels."
                )

            # Extract aliases from wheel context
            self_wisdom_units = [wu for wu, _ in self_wheel.wisdom_units.all()]
            other_wisdom_units = [wu for wu, _ in other_wheel.wisdom_units.all()]

            self_aliases = []
            for comp in self_components:
                alias = None
                for wu in self_wisdom_units:
                    alias = comp.get_alias(wu)
                    if alias:
                        break
                if not alias:
                    raise ValueError(f"Component {comp.uid} has no alias in wheel context")
                self_aliases.append(alias)

            other_aliases = []
            for comp in other_components:
                alias = None
                for wu in other_wisdom_units:
                    alias = comp.get_alias(wu)
                    if alias:
                        break
                if not alias:
                    raise ValueError(f"Component {comp.uid} has no alias in wheel context")
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
