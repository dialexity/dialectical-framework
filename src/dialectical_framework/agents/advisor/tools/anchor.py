"""
anchor tool: Plant a specific tension the LLM already sees.

Two modes:
- thesis + antithesis: full precision, creates polarity and perspective directly
- thesis only: anchors the position, discovers what opposes it
"""

from __future__ import annotations

import hashlib
from typing import Annotated

from mirascope import llm
from pydantic import Field


def _progress_key(thesis: str, antithesis: str | None) -> str:
    """A stable, opaque id for ONE anchor call's progress stream.

    Content-derived rather than a counter so it is stable across a retry of the
    same call, and hashed rather than truncated text so a host that renders the
    key verbatim cannot put the person's own words in a progress label — the
    convention `key=wheel.short_hash` already established elsewhere.
    """
    material = f"{thesis}\n{antithesis or ''}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:10]


@llm.tool
async def anchor(
    thesis: Annotated[
        str,
        Field(description="The thesis position — what the person holds or champions"),
    ],
    antithesis: Annotated[
        str | None,
        Field(
            description="The opposing force; omit to discover what opposes the thesis"
        ),
    ] = None,
    context: Annotated[
        str,
        Field(
            description=(
                "The person's own specifics behind this tension — numbers, "
                "dates, equity splits, named events, concrete instances they "
                "cited, in their terms. Stored as the tension's grounding: the "
                "tetrad itself keeps only a few words per position, so this is "
                "the only place their particulars survive. Facts they stated, "
                "not interpretation, advice, or notes about the person."
            )
        ),
    ] = "",
) -> str:
    """Plant a specific tension into the graph. With both thesis and antithesis: creates the opposition directly and generates the full tetrad. With thesis only: anchors the position and discovers what opposes it. Use when you can see the person's position clearly."""
    from dialectical_framework.utils.progress import progress_scope

    # Measured at ~40s during which the person is told nothing: `call_census` puts
    # this tool at parallelism ~1.15, and nothing writes a graph node until a
    # perspective commits, so there is a single stage — tetrad generation, ~10.2s
    # of the ~38s on its own — that a person waits through with no signal at all.
    #
    # Progress is worth adding REGARDLESS of how much latency is left to remove,
    # which is the honest framing: `parallelism 1.15` reports overlap ACHIEVED, not
    # overlap available (`utils/call_census.py`), so it cannot say the chain is out
    # of opportunities — the gather in `IntroducePolarity.resolve` was found after
    # that reading and is exactly the opportunity such a claim would have closed.
    #
    # Installed HERE, above every branch, because a scope reaches a gathered child
    # only if the child's task is created after the scope is installed
    # (`utils/progress.py`) — `AnalysisPipeline` gathers its expansions, and
    # opening the scope inside a skill would leave those children silent.
    # `total` is left at 0 and grown by whoever discovers the work.
    #
    # `key` distinguishes CONCURRENT anchors: `execute_tools()` gathers a tool
    # round and runs it concurrently, so two `anchor` calls in one round share a
    # sid and publish two interleaved streams with two `final` events. Without a
    # key a host cannot tell them apart and clears its indicator on the first one
    # while the second is still working.
    with progress_scope("anchor", key=_progress_key(thesis, antithesis)):
        return await _anchor(thesis=thesis, antithesis=antithesis, context=context)


async def _anchor(*, thesis: str, antithesis: str | None, context: str) -> str:
    """The tool's body, so the progress scope wraps it without re-indenting it.

    Split out rather than nested purely to keep the diff on the reasoning path
    empty: every line below is unchanged from when it was inline.
    """
    from dialectical_framework.agents.analyst.analyst import AnalysisPipeline
    from dialectical_framework.agents.analyst.skills.anchor_theses import \
        AnchorTheses
    from dialectical_framework.agents.analyst.skills.expand_polarities import \
        ExpandPolarity
    from dialectical_framework.agents.analyst.skills.introduce_polarity import \
        IntroducePolarity

    if antithesis:
        introduce = IntroducePolarity(
            thesis=thesis, antithesis=antithesis, text=context
        )
        result = await introduce.resolve()

        if not result.primary_polarity_hash:
            return str(introduce.report)

        # `context` grounds the tetrad, not just its classification: the poles
        # are capped near seven words and deduped, so without this the case
        # particulars are used once for classification and then lost.
        expand = ExpandPolarity(
            polarity_hash=result.primary_polarity_hash,
            grounding_context=context,
        )
        perspectives = await expand.resolve()

        combined_report = introduce.report.merge(expand.report)
        combined_report.artifacts["perspective_hashes"] = [
            pp.hash for pp in perspectives if pp.hash
        ]
        return str(combined_report)

    # Thesis only: anchor then discover antithesis via pipeline
    anchor_skill = AnchorTheses(statements=[thesis])
    ideas = await anchor_skill.resolve()

    thesis_hashes = anchor_skill.report.artifacts.get("thesis_hashes", [])
    if not thesis_hashes:
        return str(anchor_skill.report)

    # `context` grounds this branch's tetrads too. It used to ride in as
    # `intent` alone, which dropped it twice over: `AnalysisPipeline` never
    # reads `intent` once `thesis_hashes` is supplied (only the surface-theses
    # step does), and nothing forwarded it to `ExpandPolarity`. So the
    # thesis-only branch discarded the person's particulars outright while the
    # both-poles branch above preserved them — the same tool, silently two
    # different memories depending on whether the model named the opposition.
    pipeline = AnalysisPipeline(
        thesis_hashes=thesis_hashes,
        intent=context or None,
        grounding_context=context,
    )
    result = await pipeline.resolve()

    combined_report = anchor_skill.report.merge(pipeline.report)
    combined_report.artifacts["perspective_hashes"] = result.perspective_hashes
    return str(combined_report)
