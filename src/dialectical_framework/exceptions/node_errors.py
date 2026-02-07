"""
Node-related exceptions for the dialectical framework.
"""

from __future__ import annotations


class ImmutableNodeError(Exception):
    """Raised when attempting to modify a committed (immutable) node's structure."""

    pass
