"""
Mixin providing sequence topology methods for cycles, spirals, and transformations.

This mixin can be used by any node class that has a `transitions` relationship
to provide common topology navigation methods.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

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

    def as_str(self) -> str:
        """
        Returns a string representation of the transition sequence.

        Automatically resolves aliases from the Wheel this sequence belongs to.
        If not assigned to a wheel, falls back to statement preview.

        Returns:
            String like "T → T+ → A- → T..." or empty string if no components

        Examples:
            # Automatic alias resolution from wheel
            cycle.as_str()  # Uses wheel context, returns "T → T+ → A- → T..."

            # If not assigned to wheel
            cycle.as_str()  # Falls back to statement preview
        """
        components = self.dialectical_components
        if not components:
            return ""

        # Try to get wheel context for alias resolution
        wheel = self.get_wheel()

        if wheel:
            # Extract aliases from Wheel's WisdomUnits
            labels = []
            # Get all WisdomUnits from the wheel
            wisdom_units = [wu for wu, _ in wheel.wisdom_units.all()]

            for i, comp in enumerate(components):
                # Find which WisdomUnit this component belongs to
                alias = None
                for wu in wisdom_units:
                    alias = comp.get_alias(wu)
                    if alias:
                        break
                labels.append(alias if alias else f"C{i+1}")
        else:
            # Fallback to statement preview (increased to 20 chars for readability)
            labels = [
                comp.statement[:20] + "..." if len(comp.statement) > 20
                else comp.statement
                for i, comp in enumerate(components)
            ]

        if len(labels) == 1:
            return f"{labels[0]} → {labels[0]}..."

        return " → ".join(labels) + f" → {labels[0]}..."

    def is_same_structure(self, other: SequenceTopologyMixin) -> bool:
        """
        Check if sequences represent the same structure regardless of starting point.

        Args:
            other: Another node with SequenceTopologyMixin to compare with

        Returns:
            True if both have same components in same order (allowing rotation)
        """
        if not isinstance(other, SequenceTopologyMixin):
            return False

        self_components = self.dialectical_components
        other_components = other.dialectical_components

        # Same length check
        if len(self_components) != len(other_components):
            return False

        # Extract component identifiers (use statements for comparison)
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
