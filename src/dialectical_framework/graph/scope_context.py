"""
Scope context for the dialectical framework.

Provides async-safe scope propagation using contextvars, allowing nodes
created within a scope context to automatically inherit the scope ID (sid).

IMPORTANT: The application layer is responsible for SETTING the scope
(typically after authorization checks). The framework only READS the scope.

Application layer usage:
    from dialectical_framework.graph.scope_context import scope

    with scope(case.sid):  # App sets scope after auth check
        # Call framework methods here
        vocab = repo.get_vocabulary()  # Framework reads sid via DI

Framework layer usage:
    @inject
    def get_vocabulary(self, sid: Optional[str] = Provide[DI.sid]):
        # sid is injected, framework never sets it
        ...
"""

from __future__ import annotations

import contextvars
from typing import Optional


# Async-safe context variable for current scope
_current_scope: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_scope', default=None
)


def get_current_sid() -> Optional[str]:
    """
    Get the current scope ID (sid) from context.

    This is the DI-compatible function for injecting sid.
    Returns None if no scope is set.

    Example:
        # In DI container:
        sid = providers.Callable(get_current_sid)

        # In framework code:
        @inject
        def my_method(self, sid: Optional[str] = Provide[DI.sid]):
            if not sid:
                raise ValueError("No scope set")
            ...
    """
    return _current_scope.get()


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


def scope(sid: str) -> _ScopeContextManager:
    """
    Context manager for setting scope (APPLICATION LAYER ONLY).

    The framework should never call this - only the application layer
    sets scope after authorization checks.

    Args:
        sid: The scope ID (typically case.sid)

    Returns:
        Context manager that sets/restores the scope

    Example:
        from dialectical_framework.graph.scope_context import scope

        # App layer sets scope after auth check
        with scope(case.sid):
            # All framework calls here see this sid
            vocab = repo.get_vocabulary()
            comp = DialecticalComponent(statement="...")
            comp.commit()  # Inherits sid from scope
    """
    return _ScopeContextManager(sid)
