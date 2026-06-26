"""
sync tool: Re-read the full dialectical graph state.

Returns a structured dump of all tensions, pathways, and synthesis
for the current case scope.
"""

from __future__ import annotations

from mirascope import llm

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext


@llm.tool
async def sync() -> str:
    """Re-read the full graph state. Use when you need a fresh full picture after multiple changes — e.g., to survey all perspectives with scores before deciding what to explore together. Not needed after every tool call."""
    concern = DialecticalContext()
    return await concern.resolve()
