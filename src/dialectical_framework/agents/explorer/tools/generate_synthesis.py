"""
generate_synthesis tool: thin LLM-facing wrapper around the GenerateSynthesis skill.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.agents.explorer.skills.generate_synthesis import (
    GenerateSynthesis,
)


@llm.tool
async def generate_synthesis(
    wheel_hash: Annotated[
        str,
        Field(description="Hash of the Wheel to generate synthesis for"),
    ],
) -> str:
    """Generate S+/S- synthesis for a Wheel — the emergent properties arising from circular causality. S+ represents complementary harmony (1+1>2), S- represents reinforcing uniformity (1+1<2). The wheel must have transformations computed first."""
    skill = GenerateSynthesis(wheel_hash=wheel_hash)
    await skill.resolve()
    return str(skill.report)
