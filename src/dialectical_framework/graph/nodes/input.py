"""
Input node representing a source of content for dialectical analysis.

Input is a pointer to external content (website, document, IPFS, etc.)
or direct content from which statements are extracted. The actual content
resolution happens via InputResolver at the application layer.
"""

from __future__ import annotations

import hashlib
from typing import ClassVar, Optional, TYPE_CHECKING
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom,
    RelationshipManager,
    RelationshipTo,
)
from dialectical_framework.graph.relationships.has_statement_relationship import (
    HasStatementRelationship,
)
from dialectical_framework.graph.relationships.distilled_to_relationship import (
    DistilledToRelationship,
)
from dialectical_framework.graph.relationships.has_input_relationship import (
    HasInputRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent
    from dialectical_framework.graph.nodes.ideas import Ideas
    from dialectical_framework.graph.nodes.brainstorm import Brainstorm


class Input(BaseNode, label="Input"):
    """
    A source of content for dialectical analysis.

    Input nodes store content or pointers to content via the `content` field.
    The InputResolver is responsible for interpreting and resolving content
    to text - this could be direct text, a URI to fetch, multiple pointers,
    or any format the resolver understands.

    Statements extracted from the content are linked via HAS_STATEMENT.
    These statements form the basis for dialectical wheels.

    Attributes:
        content: The content or content pointer(s). Interpretation is flexible
                 and handled by InputResolver:
                 - Plain text: "My content here"
                 - Single URI: "https://example.com/article"
                 - data: URI: "data:text/plain;base64,..."
                 - Multiple pointers: JSON array of URIs
                 - Custom formats: session://..., ipfs://..., etc.

    The `handle` field (inherited) can be used for human-friendly names
    like "bbc-ukraine-article-2024-01".

    Example:
        # Plain text content
        input_node = Input(content="The quick brown fox...")
        input_node.commit()

        # URI pointer
        input_node = Input(
            content="https://bbc.com/article/123",
            handle="bbc-ukraine-article"
        )
        input_node.commit()

        # After extracting statements from content:
        input_node.statements.connect(component1)
        input_node.statements.connect(component2)
    """

    # Content or content pointer(s) - resolved by InputResolver
    content: Optional[str] = None

    # Statements extracted from this input
    statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more statements
    )

    # Ideas distilled from this input
    # Parent→child: Input distills to Ideas
    ideas: ClassVar[RelationshipManager[Ideas]] = RelationshipTo(
        "Ideas",
        model=DistilledToRelationship,
        cardinality=(0, None),  # Zero or more Ideas
    )

    # Brainstorms that include this input (reverse relationship)
    # Child→parent: Brainstorm has this Input
    _brainstorms: ClassVar[RelationshipManager[Brainstorm]] = RelationshipFrom(
        "Brainstorm",
        model=HasInputRelationship,
        cardinality=(0, None),  # Zero or more Brainstorms
    )

    def _collect_structure_hash_parts(self) -> list[str]:
        """
        Collect structure hash parts for this input.

        Parts: content field.

        Returns:
            List with the content
        """
        return [self.content or ""]

    def compute_hash(self) -> str:
        """
        Compute content hash for this Input.

        Input is purely content-addressable: same content = same hash.
        Unlike structural nodes, committed_at is NOT included because:
        - Deduplication is desirable (same URL/content should have same identity)
        - No temporal ordering needed (inputs don't critique each other)
        - Multiple references to the same source should resolve to the same Input

        Returns:
            sha256 hex string of content
        """
        parts = self._collect_structure_hash_parts()
        combined = "\n".join(parts)
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()

    def __repr__(self) -> str:
        """String representation of the input."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Input({hash_str}, content={self.content})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        content_preview = self.content[:50] + "..." if self.content and len(self.content) > 50 else self.content
        return f"Input: {content_preview or 'No content'}"
