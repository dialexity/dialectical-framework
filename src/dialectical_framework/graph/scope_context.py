"""
Scope context for the dialectical framework.

Provides async-safe scope propagation using contextvars, allowing nodes
created within a scope context to automatically inherit the case ID (case_id).

IMPORTANT: The application layer is responsible for SETTING the scope
(typically after authorization checks). The framework only READS the scope.

Application layer usage:
    from dialectical_framework.graph.scope_context import scope

    with scope(case.case_id):  # App sets scope after auth check
        # Call framework methods here
        vocab = repo.get_vocabulary()  # Framework reads case_id via DI

Framework layer usage:
    @inject
    def get_vocabulary(self, case_id: Optional[str] = Provide[DI.case_id]):
        # case_id is injected, framework never sets it
        ...
"""

from __future__ import annotations

import contextvars
from typing import Optional


# Async-safe context variable for current scope
_current_scope: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_scope', default=None
)


def get_current_case_id() -> Optional[str]:
    """
    Get the current case ID (case_id) from context.

    This is the DI-compatible function for injecting case_id.
    Returns None if no scope is set.

    Example:
        # In DI container:
        case_id = providers.Callable(get_current_case_id)

        # In framework code:
        @inject
        def my_method(self, case_id: Optional[str] = Provide[DI.case_id]):
            if not case_id:
                raise ValueError("No scope set")
            ...
    """
    return _current_scope.get()


class _ScopeContextManager:
    """Internal context manager for scope boundaries."""

    def __init__(self, case_id: str) -> None:
        self._case_id = case_id
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> str:
        """Enter scope context, returning the case_id."""
        self._token = _current_scope.set(self._case_id)
        return self._case_id

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit scope context, restoring previous scope."""
        if self._token is not None:
            _current_scope.reset(self._token)


def scope(case_id: str) -> _ScopeContextManager:
    """
    Context manager for setting scope (APPLICATION LAYER ONLY).

    The framework should never call this - only the application layer
    sets scope after authorization checks.

    Args:
        case_id: The case ID (typically case.case_id)

    Returns:
        Context manager that sets/restores the scope

    Example:
        from dialectical_framework.graph.scope_context import scope

        # App layer sets scope after auth check
        with scope(case.case_id):
            # All framework calls here see this case_id
            vocab = repo.get_vocabulary()
            comp = DialecticalComponent(statement="...")
            comp.commit()  # Inherits case_id from scope
    """
    return _ScopeContextManager(case_id)
