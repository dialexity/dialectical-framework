"""
sync tool: Re-read the dialectical graph state.

Returns a structured dump of tensions, pathways, and synthesis for the
current case scope. With `nexus_hash`, zooms into one exploration and
renders it in full depth (the unscoped dump caps wheels per cycle for
compactness; the zoomed render is exempt, same as counsel-mode dumps).
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.dialectical_context import \
    DialecticalContext


@llm.tool
async def sync(
    nexus_hash: Annotated[
        str | None,
        Field(
            description="Zoom into one exploration: render only this nexus, in full depth (no wheel cap). Omit for the full-case overview."
        ),
    ] = None,
) -> str:
    """Re-read the graph state. Without arguments: the full picture across all explorations (compact — wheels capped per cycle). With a nexus_hash: one exploration in full depth. Use the zoom when counsel centers on one exploration and the overview's capped view isn't enough."""
    concern = DialecticalContext(nexus_hash=nexus_hash)
    return await concern.resolve()
