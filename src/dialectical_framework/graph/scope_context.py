"""
Scope context service for the dialectical framework.

Provides async-safe scope propagation using contextvars, allowing nodes
created within a scope context to automatically inherit the scope ID (sid).
"""

from __future__ import annotations

import contextvars
from typing import Optional

from dependency_injector.wiring import Provide, inject

from dialectical_framework.enums.di import DI

# Async-safe context variable for current scope
_current_scope: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_scope', default=None
)


class ScopeContext:
    """
    Service for managing the current scope (sid) in node creation.

    Usage:
        # Option 1: Context manager (recommended for workflows)
        brainstorm = Brainstorm()  # sid is auto-generated UUID
        brainstorm.commit()

        with scope_context.scope(brainstorm.sid):
            input_node = Input(content="...")
            input_node.commit()  # Automatically gets sid from context

        # Option 2: Direct get
        current_sid = scope_context.get_current_scope()

        # Option 3: Explicit override (always wins)
        input_node = Input(content="...", sid=explicit_sid)

    The ScopeContext uses Python's contextvars, which are async-safe and
    work correctly with concurrent workflows.
    """

    def get_current_scope(self) -> Optional[str]:
        """Get the current scope ID from context."""
        return _current_scope.get()

    def set_current_scope(self, sid: Optional[str]) -> contextvars.Token:
        """
        Set the current scope ID.

        Args:
            sid: The scope ID (Brainstorm's UUID sid) to set

        Returns:
            Token that can be used to reset to previous value
        """
        return _current_scope.set(sid)

    def scope(self, sid: str) -> _ScopeContextManager:
        """
        Context manager for scoped node creation.

        Args:
            sid: The scope ID (Brainstorm's UUID sid) for the context

        Returns:
            Context manager that sets/restores the scope

        Example:
            brainstorm = Brainstorm()  # sid is auto-generated UUID
            brainstorm.commit()

            with scope_context.scope(brainstorm.sid):
                # All nodes created here inherit sid
                input_node = Input(content="...")
                input_node.commit()  # input_node.sid == brainstorm.sid
        """
        return _ScopeContextManager(sid)


class _ScopeContextManager:
    """Internal context manager for scope boundaries."""

    def __init__(self, sid: str) -> None:
        self._sid = sid
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> str:
        """Enter scope context, returning the sid."""
        self._token = _current_scope.set(self._sid)
        return self._sid

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit scope context, restoring previous scope."""
        if self._token is not None:
            _current_scope.reset(self._token)


# Helper function for DI access (similar to di_brain pattern)
@inject
def di_scope_context(
    scope_context: ScopeContext = Provide[DI.scope_context]
) -> ScopeContext:
    """
    Get ScopeContext from DI container.

    This function provides DI-based access to ScopeContext, similar to
    how di_brain() works for Brain access.

    Returns:
        ScopeContext instance from DI container
    """
    return scope_context
