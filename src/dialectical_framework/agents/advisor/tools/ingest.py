"""
ingest tool: Bulk discovery from material → standalone perspectives.

Captures input, runs AnalysisPipeline to extract tensions and build
perspectives. Does NOT create a nexus — that's explore's job.
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from mirascope import llm
from pydantic import Field


def _progress_key(text: str | None, input_hashes: list[str] | None) -> str:
    """A stable, opaque id for ONE ingest call's progress stream.

    Same construction and the same two reasons as `anchor._progress_key`:
    content-derived so it survives a retry of the same call, and HASHED so a host
    that renders the key verbatim cannot put the person's pasted material into a
    progress label. That second reason binds harder here than it does for `anchor`
    — the material on this path is whole documents.
    """
    material = f"{text or ''}\n{','.join(input_hashes or [])}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


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
    from dialectical_framework.utils.progress import progress_scope

    # Measured at 85-98s for a 120 KB document, with only 1.3-3.9s of that spent
    # outside a provider call (`tests/e2e/probe_ingest_cost.py`) — so the wait is
    # real work all the way through, and a 1.2 MB source is 33 windows against 4
    # at a sweep cap of 3, i.e. minutes. This was the longest silence in the tree.
    #
    # The scope is installed HERE, above the capture, for the ordering requirement
    # in `utils/progress.py`: a gathered child sees a scope only if its task was
    # created after the scope was installed. Both fan-outs below are gathers — the
    # digest's parts and the extraction sweep's windows — and opening the scope
    # inside either skill would leave the other silent.
    #
    # Everything under it was ALREADY instrumented and already silent: the
    # `expect_progress`/`report_progress` pair in `AnalysisPipeline.resolve` was
    # added for `anchor`, and on this path it was a no-op purely because no scope
    # was installed above it. `total` starts at 0 and is grown by whoever
    # discovers the work, since nobody here knows the window count yet.
    with progress_scope("ingest", key=_progress_key(text, input_hashes)):
        return await _ingest(text=text, intent=intent, input_hashes=input_hashes)


async def _ingest(
    *,
    text: str | None,
    intent: str | None,
    input_hashes: list[str] | None,
) -> str:
    """The tool's body, so the progress scope wraps it without re-indenting it.

    Split out rather than nested for the same reason as `anchor._anchor`: it keeps
    the diff on the reasoning path empty.
    """
    from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
    from dialectical_framework.concerns.add_input import AddInput
    from dialectical_framework.concerns.source_digest import ensure_digest
    from dialectical_framework.utils.progress import (expect_progress,
                                                      report_progress)

    added_hash: str | None = None
    digest_status: str | None = None

    if text:
        # Two steps declared, not one: capture is a graph write the person can
        # already see land, but the digest behind it is a fan-out over every part
        # of the source and is the first long silence on this path.
        expect_progress(2)
        report_progress("Taking in the material")
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
        report_progress("Building a working understanding of it")
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
