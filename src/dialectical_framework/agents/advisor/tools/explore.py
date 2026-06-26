"""
explore tool: Group perspectives into nexus + build pathways + synthesis.

Handles the full exploration lifecycle: nexus creation/expansion,
wheel building, transformation generation, and synthesis.
"""

from __future__ import annotations

from typing import Annotated

from mirascope import llm
from pydantic import Field


@llm.tool
async def explore(
    perspective_hashes: Annotated[
        list[str],
        Field(description="Hashes of perspectives to explore together"),
    ],
    intent: Annotated[
        str,
        Field(
            description="What this exploration is about — the theme connecting these tensions"
        ),
    ],
    nexus_hash: Annotated[
        str | None,
        Field(description="Existing nexus to enrich; omit to create a new one"),
    ] = None,
) -> str:
    """Group tensions and generate pathways. Creates or expands a nexus, builds causal arrangements, generates action-reflection pathways and synthesis. Call when you have perspective hashes ready for exploration."""
    from dialectical_framework.agents.explorer.explorer import \
        ExplorationPipeline
    from dialectical_framework.agents.explorer.skills.generate_synthesis import \
        GenerateSynthesis
    from dialectical_framework.concerns.create_nexus import CreateNexus
    from dialectical_framework.concerns.expand_nexus import ExpandNexus

    if nexus_hash:
        expand = ExpandNexus()
        expand_result = await expand.resolve(
            nexus_hash=nexus_hash,
            perspective_hashes=perspective_hashes,
        )
        nexus_report = expand.report
        effective_nexus_hash = nexus_hash
    else:
        create = CreateNexus()
        create_result = await create.resolve(
            intent=intent,
            perspective_hashes=perspective_hashes,
        )
        nexus_report = create.report
        effective_nexus_hash = create_result.nexus.short_hash

    exploration = ExplorationPipeline(nexus_hash=effective_nexus_hash)
    exp_result = await exploration.resolve()

    synthesis_count = 0
    for wh in exp_result.wheel_hashes:
        try:
            synth = GenerateSynthesis(wheel_hash=wh)
            await synth.resolve()
            synthesis_count += 1
        except (ValueError, RuntimeError):
            pass

    combined_report = nexus_report.merge(exploration.report)
    combined_report.artifacts["nexus_hash"] = effective_nexus_hash
    combined_report.artifacts["synthesis_generated"] = synthesis_count

    return str(combined_report)
