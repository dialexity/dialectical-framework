"""
ingest tool: Bulk discovery from material → standalone perspectives.

Captures input, runs AnalysisPipeline to extract tensions and build
perspectives. Does NOT create a nexus — that's explore's job.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field


@llm.tool
async def ingest(
    text: Annotated[
        str | None,
        Field(description="Accumulated user sharing to analyze; omit to process pre-loaded inputs"),
    ] = None,
    intent: Annotated[
        str | None,
        Field(description="Focus for extraction — what tensions to look for"),
    ] = None,
    input_hashes: Annotated[
        list[str] | None,
        Field(description="Specific input hashes to analyze; omit to process all"),
    ] = None,
) -> str:
    """Process raw material through dialectical analysis to discover tensions. Extracts theses, finds oppositions, and builds full perspectives (T/A/T+/T-/A+/A-). Use when substantial material exists but tensions aren't yet clear to you."""
    from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
    from dialectical_framework.concerns.add_input import AddInput
    from dialectical_framework.concerns.source_digest import SourceDigest

    added_hash: str | None = None

    if text:
        add_input = AddInput()
        input_node = await add_input.resolve(content=text)
        added_hash = input_node.short_hash

        try:
            digest = SourceDigest()
            await digest.resolve(input_hash=added_hash, context=intent or "")
        except (ValueError, RuntimeError):
            pass

    effective_hashes = input_hashes
    if added_hash and not effective_hashes:
        effective_hashes = [added_hash]
    elif added_hash and effective_hashes and added_hash not in effective_hashes:
        effective_hashes = [added_hash] + list(effective_hashes)

    pipeline = AnalysisPipeline(text=text, intent=intent, input_hashes=effective_hashes)
    result = await pipeline.resolve()

    return str(pipeline.report)
