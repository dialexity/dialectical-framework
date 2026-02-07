"""
Ideas node for the dialectical framework.

Ideas represents a collection of extracted concepts/statements from an Input.
It serves as a distillation of raw content into dialectical components.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.assessable_entity import AssessableEntity
from dialectical_framework.graph.mixins.intent_mixin import IntentMixin
from dialectical_framework.graph.mixins.incremental_build_mixin import IncrementalBuildMixin
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


class Ideas(IncrementalBuildMixin, IntentMixin, AssessableEntity, label="Ideas"):
    """
    A collection of extracted concepts from an Input source.

    Ideas represents the distillation of raw content (from an Input) into
    structured dialectical components (statements). Each Ideas node belongs
    to exactly one Input and can have multiple extracted statements.

    The intent field (from IntentMixin) captures what kind of extraction
    was performed (e.g., "Extract productivity claims", "Find ethical arguments").

    As a container (IncrementalBuildMixin), Ideas follows the incremental build pattern:
    save() → add statements → commit(). Statements must be connected before commit.

    Hierarchy:
        Brainstorm → Input → Ideas → DialecticalComponent

    Relationships:
    - Ideas comes from exactly one Input (via DISTILLED_TO)
    - Ideas can have multiple extracted statements (via HAS_STATEMENT)

    Example:
        input_node = Input(content="https://article.com")
        input_node.commit()

        ideas = Ideas(intent="Extract key arguments")
        ideas.save()  # HEAD state - no hash yet
        input_node.ideas.connect(ideas)

        comp = DialecticalComponent(statement="Remote work improves focus")
        comp.commit()
        ideas.statements.connect(comp)  # Add statements before commit

        ideas.commit()  # Computes hash from input + intent + statements
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

    def _get_commit_dependents(self):
        """
        Get statements for hash computation.

        Yields:
            DialecticalComponent nodes (statements)
        """
        for comp, _ in self.statements.all():
            yield comp

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Ideas node.

        Parts: source Input hash, sorted statement hashes.

        Returns:
            List of strings: [input_hash, stmt_hash1, stmt_hash2, ...]

        Note:
            Source Input and all connected statements must be committed.
        """
        parts = []

        # Get source Input hash
        input_result = self.input.get()
        if input_result:
            input_node, _ = input_result
            if not input_node.is_committed:
                raise ValueError(
                    f"Input must be committed before computing Ideas structure hash"
                )
            parts.append(input_node.hash)

        # Get sorted statement hashes
        statement_hashes = []
        for comp, _ in self.statements.all():
            if not comp.is_committed:
                raise ValueError(
                    "Statement must be committed before computing "
                    "Ideas structure hash"
                )
            statement_hashes.append(comp.hash)

        statement_hashes.sort()
        parts.extend(statement_hashes)

        return parts

    # Ideas uses BaseNode.compute_hash() which includes committed_at.
    # This makes Ideas a structural node - each commit produces unique hash.
    # Dedup doesn't apply to container nodes with relationships.

    def __repr__(self) -> str:
        """String representation of the ideas."""
        stmt_count = self.statements.count()
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Ideas({hash_str}, statements={stmt_count}, intent={self.intent})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        stmt_count = self.statements.count()
        intent_preview = self.intent[:30] + "..." if self.intent and len(self.intent) > 30 else self.intent
        return f"Ideas: {intent_preview or 'No intent'} ({stmt_count} statements)"
