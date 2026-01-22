"""
Input node representing a source of content for dialectical analysis.

Input is a pointer to external content (website, document, IPFS, etc.)
from which statements are extracted. The actual content resolution
happens at the application layer.
"""

from __future__ import annotations

from typing import ClassVar, Optional, TYPE_CHECKING

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import (
    RelationshipManager,
    RelationshipTo,
)
from dialectical_framework.graph.relationships.has_statement_relationship import (
    HasStatementRelationship,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class Input(BaseNode):
    """
    A source of content for dialectical analysis.

    Input nodes point to external content via the `content_uri` field.
    Statements extracted from the content are linked via HAS_STATEMENT.
    These statements form the basis for dialectical wheels.

    Attributes:
        content_uri: URI of the source content from which statements are derived.
                     This is the external context upon which the dialectical
                     analysis is based.

    URI schemes:
        - https://example.com/article - Web content
        - ipfs://Qm... - IPFS content
        - data:text/plain;base64,... - Inline data
        - file:///path/to/doc - Local file
        - s3://bucket/key - Cloud storage

    The `handle` field (inherited) can be used for human-friendly names
    like "bbc-ukraine-article-2024-01".

    Example:
        input_node = Input(
            content_uri="https://bbc.com/article/123",
            handle="bbc-ukraine-article"
        )
        input_node.save()

        # After extracting statements from content:
        input_node.statements.connect(component1)
        input_node.statements.connect(component2)
    """

    # URI of the source content from which statements are derived
    content_uri: Optional[str] = None

    # Statements extracted from this input
    statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more statements
    )

    def __repr__(self) -> str:
        """String representation of the input."""
        return f"Input(uid={self.uid}, content_uri={self.content_uri})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        uri_preview = self.content_uri[:50] + "..." if self.content_uri and len(self.content_uri) > 50 else self.content_uri
        return f"Input: {uri_preview or 'No URI'}"
