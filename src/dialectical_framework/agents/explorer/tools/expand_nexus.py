"""
expand_nexus tool: thin LLM-facing wrapper around the ExpandNexus concern.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.expand_nexus import ExpandNexus


@llm.tool
async def expand_nexus(
    nexus_hash: Annotated[
        str, Field(description="Hash of the existing Nexus to expand")
    ],
    perspective_hashes: Annotated[
        list[str], Field(description="Hashes of Perspectives to add")
    ],
) -> str:
    """Add Perspectives to an existing Nexus. Skips any already connected. Use when the user wants to include additional perspectives in an existing exploration rather than creating a new one."""
    concern = ExpandNexus()
    await concern.resolve(nexus_hash=nexus_hash, perspective_hashes=perspective_hashes)
    return str(concern.report)
