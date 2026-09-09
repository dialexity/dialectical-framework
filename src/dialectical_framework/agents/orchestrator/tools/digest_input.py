"""
digest_input: Tool for generating/refining the living digest of an Input source.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field

from dialectical_framework.concerns.source_digest import SourceDigest
from dialectical_framework.utils.progress import (progress_hash_key,
                                                  progress_scope)


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
    # The measured 25.4s hole, reachable directly: `SourceDigest` reads a source
    # larger than one prompt in parts, gathers them, and writes nothing until the
    # reduce — and its four `note_progress` calls, the first site in the tree to earn
    # them, were mute whenever this tool was the entry point. The `with` encloses
    # `resolve()`, which is where the parts' `gather` is created.
    #
    # Stage `ingest`, the name the Advisor's `ingest` tool installs, so a host sees
    # one vocabulary for "reading the person's material" whichever door it came
    # through; nested under that tool this defers and never names anything.
    #
    # Keyed by the NODE, not digested: the argument is a hash, already opaque, and
    # keeping it readable is what lets a host line its bar up with the source the
    # person just named — `progress_hash_key`'s whole argument.
    with progress_scope("ingest", key=progress_hash_key(input_hash)):
        concern = SourceDigest()
        await concern.resolve(input_hash=input_hash, context=context)
        return str(concern.report)
