"""
Input node representing a source of content for dialectical analysis.

Input is a pointer to external content (website, document, IPFS, etc.)
or direct content from which statements are extracted. The actual content
resolution happens via InputResolver at the application layer.
"""

from __future__ import annotations

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
        input_node.save()

        # URI pointer
        input_node = Input(
            content="https://bbc.com/article/123",
            handle="bbc-ukraine-article"
        )
        input_node.save()

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

    def __repr__(self) -> str:
        """String representation of the input."""
        return f"Input(uid={self.uid}, content={self.content})"

    def __str__(self) -> str:
        """Human-readable string representation."""
        content_preview = self.content[:50] + "..." if self.content and len(self.content) > 50 else self.content
        return f"Input: {content_preview or 'No content'}"
