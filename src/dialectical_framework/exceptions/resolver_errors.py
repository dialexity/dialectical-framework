"""
Resolver-related exceptions for the dialectical framework.

These exceptions are raised by InputResolver implementations when
resolving content URIs (especially dx:// URIs).
"""

from __future__ import annotations


class MalformedDxUriError(ValueError):
    """
    Raised when a dx:// URI has an invalid format.

    Valid formats:
    - dx://<sid>/<hash>           (sid + hash)
    - dx://<sid>/<branch>/<hash>  (sid + branch + hash)

    Examples of invalid URIs:
    - dx://abc123      (hash only - sid required)
    - dx://            (empty)
    - dx:///hash       (empty sid)
    """

    pass


class NodeNotFoundError(LookupError):
    """
    Raised when a node referenced by a dx:// URI cannot be found in the database.

    This can occur when:
    - The hash doesn't match any node
    - The hash prefix is too short (< 7 characters)
    - The node was deleted
    """

    pass


class ScopeMismatchError(ValueError):
    """
    Raised when the sid in a dx:// URI doesn't match the found node's sid.

    The sid in the URI acts as a security check to ensure the resolver
    only accesses nodes from the expected scope/realm.
    """

    pass


class UnsupportedNodeTypeError(TypeError):
    """
    Raised when trying to extract content from a node type that has no
    content extractor defined.

    Supported node types:
    - Rationale: text field
    - Transition: source -> target instruction
    - Synthesis: S+ and S- statements
    - DialecticalComponent: statement field
    - Input: content field (recursive)
    - Ideas: joined statement components
    """

    pass


class AmbiguousHashPrefixError(LookupError):
    """
    Raised when a hash prefix matches multiple nodes.

    Solution: Use a longer prefix to uniquely identify the node.
    """

    pass
