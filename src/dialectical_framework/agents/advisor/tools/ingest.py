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
    from dialectical_framework.concerns.source_digest import ensure_digest

    added_hash: str | None = None
    digest_status: str | None = None

    if text:
        add_input = AddInput()
        input_node = await add_input.resolve(content=text)
        # FULL hash, not `short_hash`. This line was the whole bug: the 7-char
        # form went into `input_hashes` below, `find_by_hashes` matched on
        # equality, nothing resolved, and the tool reported success while
        # telling the model to stop ingesting. `find_by_hashes` now matches by
        # prefix so either form works, and full is what a creation site hands out.
        added_hash = input_node.hash

        # `refresh=True`: this call has the user's `intent`, which is exactly
        # what `SourceDigest` refines an existing digest toward, so re-ingesting
        # the same material under a new focus is worth the call. The gap-filling
        # callers (`AnalysisPipeline`, the `add_input` tool) pass no refresh and
        # so never pay twice for what this line already did.
        digest_status = await ensure_digest(
            added_hash, context=intent or "", refresh=True
        )

    effective_hashes = input_hashes
    if added_hash and not effective_hashes:
        effective_hashes = [added_hash]
    elif added_hash and effective_hashes and added_hash not in effective_hashes:
        effective_hashes = [added_hash] + list(effective_hashes)

    pipeline = AnalysisPipeline(text=text, intent=intent, input_hashes=effective_hashes)
    result = await pipeline.resolve()

    if digest_status:
        pipeline.report.artifacts["digest"] = digest_status

    return str(pipeline.report)
