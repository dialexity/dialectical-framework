"""
ingest tool: Bulk discovery from material → standalone perspectives.

Captures input, runs AnalysisPipeline to extract tensions and build
perspectives. Does NOT create a nexus — that's explore's job.
"""

from __future__ import annotations

import logging
from typing import Annotated

from mirascope import llm
from pydantic import Field

logger = logging.getLogger(__name__)


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

        try:
            digest = SourceDigest()
            await digest.resolve(input_hash=added_hash, context=intent or "")
        except Exception as e:  # noqa: BLE001
            # Fail-soft, because the digest is enrichment: the perspectives this
            # call is about are built from full content either way, and a
            # provider hiccup on a summary must not cost the analysis. But
            # `except (ValueError, RuntimeError): pass` got both halves wrong.
            #
            # Too narrow: those two cover only `SourceDigest`'s own guards
            # ("Input not found", "no resolvable content"), which are the LEAST
            # likely failures here — the Input was created two lines up. The
            # likely ones are a provider error, response-model validation, or a
            # URL fetch dying inside `resolve_native`, and every one of them
            # aborted the whole tool.
            #
            # Too quiet: `pass` left no trace anywhere. `read_digest` returned
            # nothing and `input_context` fell back to full content, both
            # without explanation, so the absence read as "not written yet"
            # rather than "tried and failed". The note below is short on
            # purpose (the report is JSON the model pays for) and names no
            # retry tool: `ingest` is Advisor-only and the Advisor carries
            # `read_digest` but NOT `digest_input`, so pointing at one would be
            # a dead off-ramp.
            logger.warning("Digest generation failed softly during ingest: %s", e)
            digest_status = (
                f"failed softly ({type(e).__name__}: {e}); no digest stored for "
                f"this input, analysis proceeded on its full content"
            )
        else:
            digest_status = "created"

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
