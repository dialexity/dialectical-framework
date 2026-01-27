"""
Brainstorm node for the dialectical framework.

Brainstorm is a portable discovery artifact that groups Inputs and their Ideas,
providing a vocabulary of components for downstream dialectical analysis.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipTo,
    RelationshipManager,
)
from dialectical_framework.graph.relationships.has_input_relationship import (
    HasInputRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class Brainstorm(IntentMixin, AssessableEntity, label="Brainstorm"):
    """
    A portable discovery artifact grouping Inputs and Ideas.

    Brainstorm serves as the entry point for dialectical analysis, collecting
    Input sources and providing a unified vocabulary of components extracted
    from those inputs via Ideas.

    The intent field (from IntentMixin) captures the overall purpose of
    this brainstorming session (e.g., "Explore remote work dynamics").

    Graph structure:
        Brainstorm
        ├──[HAS_INPUT]──► Input ──[HAS_STATEMENT]──► DialecticalComponent
        │                   │
        │                   └──[DISTILLED_TO]──► Ideas ──[HAS_STATEMENT]──► DialecticalComponent
        │
        └── Vocabulary = all Components via HAS_STATEMENT paths

    Relationships:
    - Brainstorm has one or more Inputs (via HAS_INPUT)
    - Each Input can have Ideas extracted from it
    - Vocabulary includes all components reachable via HAS_STATEMENT

    Example:
        brainstorm = Brainstorm(intent="Explore remote work dynamics")
        brainstorm.save()

        input_node = Input(content_uri="https://article.com")
        input_node.save()
        brainstorm.inputs.connect(input_node)

        ideas = Ideas(intent="Extract productivity claims")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp = DialecticalComponent(statement="Remote work improves focus")
        comp.save()
        ideas.statements.connect(comp)

        # Vocabulary includes all components from inputs and ideas
        vocab = brainstorm.get_vocabulary()
        assert comp in vocab
    """

    # Input sources (required - at least one Input)
    inputs: ClassVar[RelationshipManager[Input]] = RelationshipTo(
        "Input",
        model=HasInputRelationship,
        cardinality=(1, None),  # At least one Input required
    )

    # Reverse relationship for Inputs to find their Brainstorms
    # This is not used directly but allows bidirectional traversal
    # Defined on Input as _brainstorms

    def get_vocabulary(self) -> list[DialecticalComponent]:
        """
        Get all DialecticalComponents accessible from this Brainstorm.

        The vocabulary includes:
        1. Components directly linked to Inputs (via HAS_STATEMENT)
        2. Components linked to Ideas (via Input → Ideas → HAS_STATEMENT)

        Returns:
            List of unique DialecticalComponent nodes in this Brainstorm's vocabulary

        Example:
            vocab = brainstorm.get_vocabulary()
            for comp in vocab:
                print(f"- {comp.statement}")
        """
        components: dict[str, DialecticalComponent] = {}

        # Iterate through all Inputs
        for input_node, _ in self.inputs.all():
            # Get components directly from Input
            for comp, _ in input_node.statements.all():
                if comp.uid not in components:
                    components[comp.uid] = comp

            # Get components from Ideas
            for ideas, _ in input_node.ideas.all():
                for comp, _ in ideas.statements.all():
                    if comp.uid not in components:
                        components[comp.uid] = comp

        return list(components.values())

    def __repr__(self) -> str:
        """String representation of the brainstorm."""
        input_count = self.inputs.count()
        return f"Brainstorm(uid={self.uid}, inputs={input_count}, intent={self.intent})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        input_count = self.inputs.count()
        vocab_count = len(self.get_vocabulary())
        intent_preview = self.intent[:30] + "..." if self.intent and len(self.intent) > 30 else self.intent
        return f"Brainstorm: {intent_preview or 'No intent'} ({input_count} inputs, {vocab_count} components)"
