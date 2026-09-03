"""
add_input: Tool for capturing source material into the case.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.add_input import AddInput
from dialectical_framework.concerns.source_digest import ensure_digest


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
    # Whoever adds the input, digests it. This tool did not, which left every
    # downstream concern rendering the raw source for anything the Analyst or
    # Explorer captured. Cost is proportional to need: content under
    # `DIGEST_THRESHOLD` is used as its own digest with no LLM call, so a short
    # proactive capture stays as instant as it was, and only a large one — the
    # case that made this matter — pays for a call.
    concern.report.artifacts["digest"] = await ensure_digest(input_node.hash)
    return str(concern.report)
