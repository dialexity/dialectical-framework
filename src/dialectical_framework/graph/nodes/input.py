"""
Input node representing a source of content for dialectical analysis.

Input is a pointer to external content (website, document, IPFS, etc.)
from which statements are extracted. The actual content resolution
happens at the application layer.
"""

from __future__ import annotations

from typing import ClassVar, TYPE_CHECKING

from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import (
    RelationshipManager,
    RelationshipTo,
)

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.dialectical_component import DialecticalComponent


class Input(BaseNode):
    """
    A source of content for dialectical analysis.

    Input nodes point to external content via the inherited `uri` field.
    Statements extracted from the content are linked via HAS_STATEMENT.

    The `uri` field (inherited from BaseNode) should always be set for Input,
    as it IS the pointer to the source content.

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
            uri="https://bbc.com/article/123",
            handle="bbc-ukraine-article"
        )
        input_node.save()

        # After extracting statements from content:
        input_node.statements.connect(component1)
        input_node.statements.connect(component2)
    """

    # Statements extracted from this input
    statements: ClassVar[RelationshipManager[DialecticalComponent]] = RelationshipTo(
        "DialecticalComponent",
        "HAS_STATEMENT",
        cardinality=(0, None),  # Zero or more statements
    )
