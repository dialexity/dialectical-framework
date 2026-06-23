"""
add_input: Tool for capturing source material into the case.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.add_input import AddInput


@llm.tool
async def add_input(
    content: Annotated[
        str,
        Field(
            description="Source material: user-provided text, URL, or captured conversation fragment"
        ),
    ],
) -> str:
    """Add source material for analysis — user-provided text, URL, or captured conversation fragment. Use proactively when the user describes their situation. Not for storing your analytical outputs."""
    concern = AddInput()
    input_node = await concern.resolve(content=content)
    return str(concern.report)
