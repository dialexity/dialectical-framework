"""
sync tool: Re-read the dialectical graph state.

Returns a structured dump of tensions, pathways, and synthesis for the
current case scope. With `nexus_hash`, zooms into one exploration and
renders it in full depth (the unscoped dump caps wheels per cycle for
compactness; the zoomed render is exempt, same as counsel-mode dumps).

A `nexus_hash` that does not resolve comes BACK as text, it does not raise.
`DialecticalContext._resolve_scoped` raises `ValueError` on an unknown hash,
which is right for a concern (its caller may have a Nexus it must not
silently ignore) and wrong at a read-only tool boundary: the model receives
an error string where it expected a dump, and a conversation that loses a
read tool mid-turn stops building. Measured on `ladder-return-r18` — two
`sync:RAISED — Nexus not found` calls, one of which took the whole cell's
graph down with it (rep 5 also lost `ingest`, and the run reported zero
perspectives against tool outcomes that said otherwise). The model had
invented a plausible-looking hash; every other read-side tool degrades to a
message here (`present_exploration` returns its "Nexus not found" as a
report), so this one was the outlier.
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
    try:
        return await concern.resolve()
    except ValueError as e:
        # Only the unresolvable-hash case. The zoom is a convenience over the
        # overview, so the recovery names it: the model can re-read unscoped
        # and keep going instead of losing the read side for the rest of the
        # turn. Anything else propagates — a broken dump must not read as a
        # bad hash.
        if nexus_hash and "not found" in str(e).lower():
            return (
                f"{e}. No exploration with that hash — it may have been "
                "discarded, or the hash may be wrong. Call sync with no "
                "arguments for the full-case overview, which lists the "
                "explorations that do exist."
            )
        raise
