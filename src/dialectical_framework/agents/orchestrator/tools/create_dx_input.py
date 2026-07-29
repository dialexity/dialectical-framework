"""
create_dx_input: Tool for creating an Input node referencing a Transition via dx:// URI.

Shared orchestrator tool (Analyst + Explorer). This is the round-trip move of
the Navigator: an exploration insight (Transition) becomes a Case Input that
the Analyst can then process (`surface_theses`/`analyze`) into new
perspectives, which flow back into the nexus via `expand_nexus`. The Explorer
carries it so the loop can be STARTED from where the insight appears — the
analysis of the dx:// input still happens in the Analyst thread.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.create_dx_input import CreateDxInput


@llm.tool
async def create_dx_input(
    transition_hash: Annotated[str, Field(description="Hash (or 7+ char prefix) of the Transition node to reference")],
) -> str:
    """Create an Input that references a Transition node via dx:// URI. This feeds the transition's insight back into the analyst pipeline as a new input source that can be processed selectively."""
    concern = CreateDxInput()
    await concern.resolve(transition_hash=transition_hash)
    return str(concern.report)
