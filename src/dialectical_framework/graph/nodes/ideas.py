"""
Ideas node for the dialectical framework.

Ideas represents a collection of extracted concepts/statements from an Input.
It serves as a distillation of raw content into statements.
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
    from dialectical_framework.graph.nodes.statement import Statement


class Ideas(IncrementalBuildMixin, IntentMixin, AssessableEntity, label="Ideas"):
    """
    A collection of extracted concepts from one or more Input sources.

    Ideas represents the distillation of raw content (from Inputs) into
    structured statements. Each Ideas node can have one or more source
    Inputs and multiple extracted statements.

    The intent field (from IntentMixin) captures what kind of extraction
    was performed (e.g., "Extract productivity claims", "Find ethical arguments").

    As a container (IncrementalBuildMixin), Ideas follows the incremental build pattern:
    save() → add statements → commit(). Statements must be connected before commit.

    Hierarchy:
        Case → Input → Ideas → Statement

    Relationships:
    - Ideas comes from one or more Inputs (via DISTILLED_TO)
    - Ideas can have multiple extracted statements (via HAS_STATEMENT)

    Example:
        input_node = Input(content="https://article.com")
        input_node.commit()

        ideas = Ideas(intent="Extract key arguments")
        ideas.save()  # HEAD state - no hash yet
        ideas.inputs.connect(input_node)

        comp = Statement(text="Remote work improves focus")
        comp.commit()
        ideas.statements.connect(comp)  # Add statements before commit

        ideas.commit()  # Computes hash from inputs + intent + statements
    """

    # Source Inputs (optional - explicit provenance when needed)
    # Ideas→Input: Ideas distilled from specific Input(s)
    # When empty: Ideas uses all Inputs available in Case at creation time (inferred via timestamp)
    # When specified: Ideas derived from these specific Inputs (e.g., Rationale-spawned Input)
    inputs: ClassVar[RelationshipManager[Input]] = RelationshipTo(
        "Input",
        model=DistilledToRelationship,
        cardinality=(0, None),  # Zero or more source Inputs
    )

    # Extracted statements/concepts
    statements: ClassVar[RelationshipManager[Statement]] = RelationshipTo(
        "Statement",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more statements
    )

    def _get_commit_dependents(self):
        """
        Get statements for hash computation.

        Yields:
            Statement nodes
        """
        for comp, _ in self.statements.all():
            yield comp

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this Ideas node.

        Parts: sorted statement hashes only.
        Inputs are NOT included - provenance is inferred via timestamps.

        Returns:
            List of strings: [stmt_hash1, stmt_hash2, ...]

        Note:
            Connected statements must be committed.
        """
        statement_hashes = []
        for comp, _ in self.statements.all():
            if not comp.is_committed:
                raise ValueError(
                    "Statement must be committed before computing Ideas structure hash"
                )
            statement_hashes.append(comp.hash)

        statement_hashes.sort()
        return statement_hashes

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
