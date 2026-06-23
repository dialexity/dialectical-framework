"""
Input node representing a source of content for dialectical analysis.

Input is a pointer to external content (website, document, IPFS, etc.)
or direct content from which statements are extracted. The actual content
resolution happens via InputResolver at the application layer.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, ClassVar, Optional, Self, Union

from dependency_injector.wiring import Provide, inject
from gqlalchemy import Memgraph, Neo4j

from dialectical_framework.enums.di import DI
from dialectical_framework.graph.nodes.base_node import BaseNode
from dialectical_framework.graph.relationship_manager import (
    RelationshipFrom, RelationshipManager, RelationshipTo)
from dialectical_framework.graph.relationships.distilled_to_relationship import \
    DistilledToRelationship
from dialectical_framework.graph.relationships.has_input_relationship import \
    HasInputRelationship
from dialectical_framework.graph.relationships.has_statement_relationship import \
    HasStatementRelationship

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.case import Case
    from dialectical_framework.graph.nodes.ideas import Ideas
    from dialectical_framework.graph.nodes.statement import Statement


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

    Example:
        # Plain text content
        input_node = Input(content="The quick brown fox...")
        input_node.commit()

        # URI pointer
        input_node = Input(content="https://bbc.com/article/123")
        input_node.commit()

        # After extracting statements from content:
        input_node.statements.connect(component1)
        input_node.statements.connect(component2)
    """

    # Content or content pointer(s) - resolved by InputResolver
    content: Optional[str] = None

    # Living digest: LLM-generated analytical understanding of the content.
    # Mutable post-commit (NOT part of hash). Populated by SourceDigest concern.
    digest: Optional[str] = None

    # Statements extracted from this input
    statements: ClassVar[RelationshipManager[Statement]] = RelationshipTo(
        "Statement",
        model=HasStatementRelationship,
        cardinality=(0, None),  # Zero or more statements
    )

    # Ideas distilled from this input
    # Input -[:DISTILLED_TO]-> Ideas: provenance link from Input to derived Ideas
    ideas: ClassVar[RelationshipManager[Ideas]] = RelationshipTo(
        "Ideas",
        model=DistilledToRelationship,
        cardinality=(0, None),  # Zero or more Ideas
    )

    # Cases that include this input (reverse relationship)
    # Child→parent: Case has this Input
    _cases: ClassVar[RelationshipManager[Case]] = RelationshipFrom(
        "Case",
        model=HasInputRelationship,
        cardinality=(0, None),  # Zero or more Cases
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
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()

    def _is_uri(self) -> bool:
        """Check if content looks like a URI (not plain text).

        Accepts ANY RFC-ish URI that starts with a valid scheme prefix, e.g.:
          - https://example.com
          - mailto:me@example.com
          - urn:uuid:...
          - dx://...
          - data:... (special-cased)

        Note: This is a *detection* heuristic, not full validation of each scheme.
        """
        if not self.content:
            return False

        s = self.content.strip()
        if not s:
            return False

        # data: is explicitly supported; (optional) require comma to reduce false positives
        if s.startswith("data:"):
            return True

        # RFC 3986 scheme: ALPHA *( ALPHA / DIGIT / "+" / "-" / "." )
        # We only need to know if it *starts* like a URI.
        import re

        return re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", s) is not None

    def _change_content_to_pointer_if_exists(self) -> bool:
        """
        If content matches an existing node, transform to dx:// reference.

        This prevents hash collision between Input and other content-addressable
        nodes. The Input becomes a reference to the canonical node.

        Returns:
            True if content was transformed, False otherwise
        """
        if not self.content or self._is_uri():
            return False

        # Compute what hash would be for this content
        potential_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()

        # Check if a node with this hash exists
        from dialectical_framework.graph.repositories.node_repository import \
            NodeRepository

        repo = NodeRepository()
        existing = repo.find_by_hash(potential_hash)

        if existing is None:
            return False

        # If existing is also an Input, let normal dedup handle it
        if isinstance(existing, Input):
            return False

        # Transform content to dx:// reference
        # Use the existing node's sid for the reference
        node_sid = existing.sid or self.sid
        if not node_sid:
            raise ValueError(
                f"Cannot transform Input to dx:// reference: no sid available. "
                f"Both Input and matching node have sid=None. "
                f"Node hash: {existing.hash[:8]}..."
            )

        self.content = f"dx://{node_sid}/{existing.hash}"
        return True

    @inject
    def commit(self, graph_db: Union[Memgraph, Neo4j] = Provide[DI.graph_db]) -> Self:
        """
        Commit this Input: check for component collision, compute hash, and persist.

        If content is plain text that matches an existing Statement's
        statement, the content is transformed to a dx:// reference to avoid
        hash collision. This makes Input a pointer to the canonical component.

        Returns:
            Self for chaining

        Raises:
            ImmutableNodeError: If already committed
        """
        # Transform plain text to dx:// reference if it matches an existing component
        self._change_content_to_pointer_if_exists()

        # Delegate to parent commit
        return super().commit()

    def __repr__(self) -> str:
        """String representation of the input."""
        hash_str = self.hash[:7] if self.is_committed else "uncommitted"
        return f"Input({hash_str}, content={self.content})"

    def __str__(self) -> str:
        """Human-readable string representation. Shows digest if available."""
        if self.digest:
            return f"Input: {self.digest}"
        content_preview = (
            self.content[:50] + "..."
            if self.content and len(self.content) > 50
            else self.content
        )
        return f"Input: {content_preview or 'No content'}"
