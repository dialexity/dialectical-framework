"""
create_nexus tool: thin LLM-facing wrapper around the CreateNexus concern.
"""

from __future__ import annotations

from typing import Annotated, Optional

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.create_nexus import CreateNexus


@llm.tool
async def create_nexus(
    intent: Annotated[
        str, Field(description="Exploration purpose — what to understand or navigate")
    ],
    perspective_hashes: Annotated[
        list[str], Field(description="Hashes of Perspectives to include")
    ],
    title: Annotated[
        Optional[str],
        Field(
            description="Short title for UI display (1-3 words, derived from intent)"
        ),
    ] = None,
    preset: Annotated[
        str,
        Field(
            description="Estimation strategy: 'preset:auto', 'preset:balanced', 'preset:realistic', 'preset:desirable', 'preset:feasible'"
        ),
    ] = "preset:auto",
) -> str:
    """Create a Nexus — an exploration container that groups Perspectives for structural combination into Cycles and Wheels. The intent describes what to explore or navigate."""
    concern = CreateNexus()
    await concern.resolve(
        intent=intent, perspective_hashes=perspective_hashes, preset=preset, title=title
    )
    return str(concern.report)
