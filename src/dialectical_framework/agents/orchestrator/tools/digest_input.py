"""
digest_input: Tool for generating/refining the living digest of an Input source.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.source_digest import SourceDigest


@llm.tool
async def digest_input(
    input_hash: Annotated[str, Field(description="Hash of the Input node to digest")],
    context: Annotated[
        str,
        Field(
            description="Direction for the digest: user guidance, framework state, or focus instructions"
        ),
    ] = "",
) -> str:
    """Generate or refine the analytical digest of an input source. Use to build initial understanding of new inputs, or to sharpen the digest with user direction or framework learnings."""
    concern = SourceDigest()
    await concern.resolve(input_hash=input_hash, context=context)
    return str(concern.report)
