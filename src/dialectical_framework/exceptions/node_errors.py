"""
Node-related exceptions for the dialectical framework.
"""

from __future__ import annotations


class ImmutableNodeError(Exception):
    """Raised when attempting to modify a committed (immutable) node's structure."""


class MissingScopeError(RuntimeError):
    """Raised when an agent turn starts with no scope (sid) set.

    Agent conversations (Analyst/Explorer/Advisor chat) write sid-scoped
    nodes through their tools. Without `with scope(case.sid):` the turn
    would fail SILENTLY: nodes save with sid=None, invisible to every
    repository listing (work dropped while tool reports claim success),
    and commit-time dedup falls back to an UNSCOPED find_by_hash that can
    alias a node onto another Case's node, attaching foreign edges to it.

    Deliberately an agent-level guard, not a BaseNode one: sid-less
    "orphan" nodes are a supported node-layer semantic (portable
    identifiers — see TestOrphanNodes), so programmatic callers may
    create them; conversational turns never legitimately run unscoped.
    """

