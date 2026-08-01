"""
Shared helper for merging app-provided tools into an agent's built-in set.

All three conversational agents (Analyst, Explorer, Advisor) expose an
`app_tools` constructor parameter — the app-side seam for domain
resources (chart lookups, methodology references, knowledge-base fetches).
The merge rules are identical across agents, so they live here.
"""

from __future__ import annotations

from typing import Optional


def merge_app_tools(builtin: list, app_tools: Optional[list]) -> list:
    """Append app-provided @llm.tool functions to an agent's built-in set.

    The agent's system prompt has no docs for app tools and skips unknown
    names — apps describe them in the app preamble, where domain vocabulary
    lives; the tool schemas (name, params, docstring) reach the LLM through
    the tool protocol itself.

    Raises:
        ValueError: If an app tool shadows a built-in tool name — the app
            tool would silently hijack framework machinery.
    """
    if not app_tools:
        return builtin
    builtin_names = {t.__name__ for t in builtin}
    collisions = [t.__name__ for t in app_tools if t.__name__ in builtin_names]
    if collisions:
        raise ValueError(f"app_tools shadow built-in tools: {collisions}")
    return builtin + list(app_tools)
