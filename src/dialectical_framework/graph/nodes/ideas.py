"""
Ideas node for the dialectical framework.

Ideas represents a collection of extracted concepts/statements from an Input.
It serves as a distillation of raw content into dialectical components.
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
from dialectical_framework.graph.relationships.distilled_to_relationship import (
    DistilledToRelationship,
)
from dialectical_framework.graph.relationships.has_statement_relationship import (
    HasStatementRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.input import Input
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class Ideas(IntentMixin, AssessableEntity):
    """
    A collection of extracted concepts from an Input source.

    Ideas represents the distillation of raw content (from an Input) into
    structured dialectical components (statements). Each Ideas node belongs
    to exactly one Input and can have multiple extracted statements.

    The intent field (from IntentMixin) captures what kind of extraction
    was performed (e.g., "Extract productivity claims", "Find ethical arguments").

    Hierarchy:
        Brainstorm → Input → Ideas → DialecticalComponent

    Relationships:
    - Ideas comes from exactly one Input (via DISTILLED_TO)
    - Ideas can have multiple extracted statements (via HAS_STATEMENT)

    Example:
        input_node = Input(content_uri="https://article.com")
        input_node.save()

        ideas = Ideas(intent="Extract key arguments")
        ideas.save()
        input_node.ideas.connect(ideas)

        comp = DialecticalComponent(statement="Remote work improves focus")
        comp.save()
        ideas.statements.connect(comp)
    """

    # Source Input (required - Ideas comes from exactly one Input)
    # Parent→child: Input distills to Ideas (Input.ideas connects to Ideas)
    input: ClassVar[RelationshipManager[Input]] = RelationshipFrom(
        "Input",
        model=DistilledToRelationship,
        cardinality=(1, 1),  # Exactly one source Input
    )

    # Extracted statements/concepts
    statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more statements
    )

    def __repr__(self) -> str:
        """String representation of the ideas."""
        stmt_count = self.statements.count()
        return f"Ideas(uid={self.uid}, statements={stmt_count}, intent={self.intent})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        stmt_count = self.statements.count()
        intent_preview = self.intent[:30] + "..." if self.intent and len(self.intent) > 30 else self.intent
        return f"Ideas: {intent_preview or 'No intent'} ({stmt_count} statements)"
