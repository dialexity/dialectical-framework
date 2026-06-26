"""
anchor tool: Plant a specific tension the LLM already sees.

Two modes:
- thesis + antithesis: full precision, creates polarity and perspective directly
- thesis only: anchors the position, discovers what opposes it
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field


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
        Field(description="Conversational context that grounds this tension"),
    ] = "",
) -> str:
    """Plant a specific tension into the graph. With both thesis and antithesis: creates the opposition directly and generates the full tetrad. With thesis only: anchors the position and discovers what opposes it. Use when you can see the person's position clearly."""
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

        expand = ExpandPolarity(polarity_hash=result.primary_polarity_hash)
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

    pipeline = AnalysisPipeline(thesis_hashes=thesis_hashes, intent=context or None)
    result = await pipeline.resolve()

    combined_report = anchor_skill.report.merge(pipeline.report)
    combined_report.artifacts["perspective_hashes"] = result.perspective_hashes
    return str(combined_report)
