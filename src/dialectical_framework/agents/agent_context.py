"""
Agent context for the dialectical framework.

Provides async-safe agent name propagation using contextvars.
The framework sets the agent name inside chat methods; concerns read it
for effect logging.

Framework layer usage (inside Analyst/Explorer):
    from dialectical_framework.agents.agent_context import agent_scope

    with agent_scope("analyst"):
        result = await self._conversation.submit(...)

Read usage (inside ExecutionReport, EffectLogger):
    from dialectical_framework.agents.agent_context import get_current_agent

    agent = get_current_agent()  # "analyst" or None
"""

from __future__ import annotations

import contextvars
from typing import Optional


_current_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    'current_agent', default=None
)


def get_current_agent() -> Optional[str]:
    """Get the current agent name from context. Returns None if not set."""
    return _current_agent.get()


class _AgentContextManager:
    def __init__(self, name: str) -> None:
        self._name = name
        self._token: Optional[contextvars.Token] = None

    def __enter__(self) -> str:
        self._token = _current_agent.set(self._name)
        return self._name

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        if self._token is not None:
            _current_agent.reset(self._token)


def agent_scope(name: str) -> _AgentContextManager:
    """Context manager for setting agent name within chat methods."""
    return _AgentContextManager(name)
