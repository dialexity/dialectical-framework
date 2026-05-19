"""
DialexityInputResolver for resolving dx:// URIs to node content.

dx:// URIs allow Input nodes to reference internal graph nodes as content sources,
enabling derived components from analytical nodes (Rationale, Transition, Synthesis)
to follow the same Input→HAS_STATEMENT pattern as Gen-0 components.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dialectical_framework.exceptions.resolver_errors import (
    AmbiguousHashPrefixError, MalformedDxUriError, NodeNotFoundError,
    ScopeMismatchError, UnsupportedNodeTypeError)
from dialectical_framework.graph.repositories.node_repository import \
    NodeRepository

if TYPE_CHECKING:
    from dialectical_framework.graph.nodes.base_node import BaseNode


class DialexityInputResolver:
    """
    Resolves dx:// URIs to node content.

    dx:// URI Format:
        dx://<sid>/<hash>

    Examples:
        dx://a1b2c3d4-e5f6-7890/abc123def456...

    The sid is always required for security - it prevents accessing nodes
    from disallowed scopes/realms. Hash can be a full hash or a 7+ char prefix.

    Supported node types:
        - Rationale: returns `text` field
        - Statement: returns `text` field
        - Transition: returns `summary` or `instruction` field

    All other node types fail. The application is responsible for distilling
    new Ideas or Components from the resolved content.
    """

    MIN_HASH_PREFIX_LENGTH = 7

    def __init__(self) -> None:
        self._hash_repo = NodeRepository()

    def parse_uri(self, uri: str) -> tuple[str, str]:
        """
        Parse a dx:// URI into its components.

        Args:
            uri: The dx:// URI to parse

        Returns:
            Tuple of (sid, hash_or_prefix)
            - sid: Required scope identifier
            - hash_or_prefix: The hash or hash prefix (7+ chars)

        Raises:
            MalformedDxUriError: If URI format is invalid
        """
        if not uri.startswith("dx://"):
            raise MalformedDxUriError(f"URI must start with 'dx://', got: {uri}")

        # Remove scheme
        path = uri[5:]  # Remove "dx://"

        if not path:
            raise MalformedDxUriError("dx:// URI cannot be empty")

        # Split path segments
        segments = path.split("/")

        # Filter out empty segments (handles trailing slashes)
        segments = [s for s in segments if s]

        if len(segments) != 2:
            raise MalformedDxUriError(
                f"dx:// URI requires exactly sid and hash. "
                f"Format: dx://<sid>/<hash>. "
                f"Got: {uri}"
            )

        sid, hash_or_prefix = segments

        # Validate sid is not empty
        if not sid:
            raise MalformedDxUriError(f"dx:// URI requires a non-empty sid. Got: {uri}")

        # Validate hash length
        if len(hash_or_prefix) < self.MIN_HASH_PREFIX_LENGTH:
            raise MalformedDxUriError(
                f"Hash must be at least {self.MIN_HASH_PREFIX_LENGTH} characters. "
                f"Got {len(hash_or_prefix)} characters in: {uri}"
            )

        return sid, hash_or_prefix

    async def resolve(self, uri: str) -> str:
        """
        Resolve a dx:// URI to text content.

        Args:
            uri: The dx:// URI to resolve

        Returns:
            Text content extracted from the referenced node

        Raises:
            MalformedDxUriError: If URI format is invalid
            NodeNotFoundError: If node cannot be found
            ScopeMismatchError: If sid doesn't match the node
            UnsupportedNodeTypeError: If node type has no content extractor
        """
        sid, hash_or_prefix = self.parse_uri(uri)
        node = self._lookup_node(sid, hash_or_prefix)
        return self._extract_content(node)

    def _lookup_node(
        self,
        sid: str,
        hash_or_prefix: str,
    ) -> BaseNode:
        """
        Find a node by hash/prefix and validate sid.

        Args:
            sid: Required scope identifier
            hash_or_prefix: Full hash or prefix (7+ chars)

        Returns:
            The found node

        Raises:
            NodeNotFoundError: If node cannot be found
            AmbiguousHashPrefixError: If prefix matches multiple nodes
            ScopeMismatchError: If sid doesn't match the node
        """
        # Try hash lookup (supports both full hash and prefix)
        try:
            node = self._hash_repo.find_by_hash(hash_or_prefix)
        except ValueError as e:
            if "Ambiguous" in str(e):
                raise AmbiguousHashPrefixError(str(e)) from e
            raise NodeNotFoundError(str(e)) from e

        if node is None:
            raise NodeNotFoundError(
                f"No node found with hash or prefix: {hash_or_prefix}"
            )

        # Validate sid matches
        if node.sid != sid:
            raise ScopeMismatchError(
                f"sid mismatch: URI specifies '{sid}' but node has '{node.sid}'"
            )

        return node

    def _extract_content(self, node: BaseNode) -> str:
        """
        Extract text content from a node based on its type.

        Supported types:
        - Rationale: returns `text` field
        - Statement: returns `text` field
        - Transition: returns `summary` or `instruction` field

        Args:
            node: The node to extract content from

        Returns:
            Text content

        Raises:
            UnsupportedNodeTypeError: If node type is not supported
        """
        # Import node types here to avoid circular imports at module level
        from dialectical_framework.graph.nodes.rationale import Rationale
        from dialectical_framework.graph.nodes.statement import Statement
        from dialectical_framework.graph.nodes.transition import Transition

        if isinstance(node, Rationale):
            return node.text
        elif isinstance(node, Statement):
            return node.text
        elif isinstance(node, Transition):
            return node.summary or node.instruction or ""
        else:
            raise UnsupportedNodeTypeError(
                f"dx:// cannot reference node type: {type(node).__name__}. "
                f"Supported types: Rationale, Statement, Transition"
            )
